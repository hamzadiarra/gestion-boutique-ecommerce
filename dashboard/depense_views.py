from django.utils.translation import gettext
import csv
import time
from decimal import Decimal
from pathlib import Path

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, OperationalError, connection, transaction
from django.db.models import Q, Sum
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts.decorators import comptable_required
from .comptable_views import _csv_safe
from .depense_forms import CategorieDepenseForm, DepenseFiltreForm, DepenseForm
from .models import BoutiqueSettings, CategorieDepense, Depense, JournalActivite, log_activity


def _filtered_depenses(request):
    form = DepenseFiltreForm(request.GET)
    expenses = Depense.objects.select_related("categorie", "cree_par", "validee_par")
    if not form.is_valid():
        return expenses.none(), form
    data = form.cleaned_data
    if data["q"]:
        query = data["q"]
        expenses = expenses.filter(Q(reference__icontains=query) | Q(libelle__icontains=query) | Q(beneficiaire__icontains=query) | Q(description__icontains=query) | Q(categorie__nom__icontains=query))
    for key in ("categorie", "moyen_paiement", "statut", "cree_par"):
        if data[key]:
            expenses = expenses.filter(**{key: data[key]})
    if data["date_debut"]:
        expenses = expenses.filter(date_depense__gte=data["date_debut"])
    if data["date_fin"]:
        expenses = expenses.filter(date_depense__lte=data["date_fin"])
    return expenses.order_by("-date_depense", "-pk"), form


@never_cache
@comptable_required
@require_GET
def comptable_depenses(request):
    expenses, form = _filtered_depenses(request)
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "dashboard/depenses/liste.html", {
        "page_obj": Paginator(expenses, 20).get_page(request.GET.get("page")),
        "filtre_form": form, "query_params": params.urlencode(),
        "total_selection": expenses.filter(statut="validee").aggregate(total=Sum("montant"))["total"] or Decimal("0"),
        "boutique": BoutiqueSettings.get_solo(), **Depense.indicateurs(),
    })


@never_cache
@comptable_required
@require_http_methods(["GET", "POST"])
def comptable_depense_nouvelle(request):
    form = DepenseForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            expense = form.save(commit=False)
            expense.cree_par = request.user
            expense.save()
            log_activity(request.user, "autre", f"Dépense {expense.reference} créée en brouillon : {expense.libelle} ({expense.montant}).", request)
        messages.success(request, gettext("Brouillon enregistré. Validez-le pour l'inclure dans les charges."))
        return redirect("comptable_depense_detail", depense_id=expense.pk)
    return render(request, "dashboard/depenses/formulaire.html", {"form": form, "boutique": BoutiqueSettings.get_solo()})


@never_cache
@comptable_required
@require_http_methods(["GET", "POST"])
def comptable_depense_modifier(request, depense_id):
    with transaction.atomic():
        expense = get_object_or_404(Depense.objects.select_for_update(), pk=depense_id)
        if expense.statut != "brouillon":
            return HttpResponseForbidden(gettext("Seule une dépense brouillon est modifiable."))
        form = DepenseForm(request.POST if request.method == "POST" else None, request.FILES or None, instance=expense)
        if request.method == "POST" and form.is_valid():
            expense = form.save()
            log_activity(request.user, "autre", f"Dépense {expense.reference} modifiée en brouillon : {expense.libelle} ({expense.montant}).", request)
            messages.success(request, gettext("Brouillon mis à jour."))
            return redirect("comptable_depense_detail", depense_id=expense.pk)
    return render(request, "dashboard/depenses/formulaire.html", {"form": form, "depense": expense, "boutique": BoutiqueSettings.get_solo()})


@never_cache
@comptable_required
@require_GET
def comptable_depense_detail(request, depense_id):
    expense = get_object_or_404(Depense.objects.select_related("categorie", "cree_par", "validee_par"), pk=depense_id)
    return render(request, "dashboard/depenses/detail.html", {
        "depense": expense, "boutique": BoutiqueSettings.get_solo(),
        "activites": JournalActivite.objects.filter(details__startswith=f"Dépense {expense.reference} ").select_related("utilisateur")[:50],
    })


def _transition_depense(request, depense_id, expected, target):
    # A conditional UPDATE is also a write lock on SQLite, where SELECT FOR
    # UPDATE alone cannot serialize two validations. Log only the winning write.
    for attempt in range(5):
        try:
            with transaction.atomic():
                changes = {"statut": target, "updated_at": timezone.now()}
                if target == "validee":
                    changes.update(date_validation=timezone.now(), validee_par=request.user)
                changed = Depense.objects.filter(pk=depense_id, statut=expected).update(**changes)
                expense = get_object_or_404(Depense.objects.select_for_update(), pk=depense_id)
                if changed:
                    from .finance_services import enregistrer_depense
                    enregistrer_depense(expense, request.user, annulation=target == "annulee")
                    verb = "validée" if target == "validee" else "annulée"
                    log_activity(request.user, "autre", f"Dépense {expense.reference} {verb} : {expense.montant} {BoutiqueSettings.get_solo().devise}.", request, "info" if target == "validee" else "warning")
                elif expense.statut != target:
                    return HttpResponse(gettext("Cette transition n'est pas autorisée dans l'état actuel de la dépense."), status=409)
            messages.success(request, gettext("Dépense mise à jour.") if changed else gettext("Cette action a déjà été effectuée."))
            return redirect("comptable_depense_detail", depense_id=depense_id)
        except OperationalError as exc:
            if connection.vendor != "sqlite" or "locked" not in str(exc).lower():
                raise
            if attempt == 4:
                return HttpResponse(gettext("Une autre opération est en cours. Veuillez réessayer."), status=409)
            time.sleep(0.04 * (attempt + 1))


@never_cache
@comptable_required
@require_POST
def comptable_depense_valider(request, depense_id):
    return _transition_depense(request, depense_id, "brouillon", "validee")


@never_cache
@comptable_required
@require_POST
def comptable_depense_annuler(request, depense_id):
    return _transition_depense(request, depense_id, "validee", "annulee")


@never_cache
@comptable_required
@require_GET
def comptable_depense_justificatif(request, depense_id):
    expense = get_object_or_404(Depense, pk=depense_id)
    if not expense.justificatif:
        raise Http404(gettext("Aucun justificatif pour cette dépense."))
    try:
        stream = expense.justificatif.open("rb")
    except (OSError, ValueError) as exc:
        raise Http404(gettext("Justificatif introuvable.")) from exc
    response = FileResponse(stream, as_attachment=True, filename=f"{expense.reference}-justificatif{Path(expense.justificatif.name).suffix}", content_type="application/octet-stream")
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response


@never_cache
@comptable_required
@require_http_methods(["GET", "POST"])
def comptable_depense_categories(request):
    form = CategorieDepenseForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                category = form.save()
                log_activity(request.user, "autre", f"Catégorie de dépense #{category.pk} créée : {category.nom}.", request)
        except (IntegrityError, ValidationError):
            form.add_error("nom", gettext("Une catégorie portant ce nom existe déjà."))
        else:
            messages.success(request, gettext("Catégorie créée."))
            return redirect("comptable_depense_categories")
    return render(request, "dashboard/depenses/categories.html", {
        "form": form, "page_obj": Paginator(CategorieDepense.objects.all(), 20).get_page(request.GET.get("page")),
    })


@never_cache
@comptable_required
@require_POST
def comptable_depense_categorie_toggle(request, categorie_id):
    with transaction.atomic():
        category = get_object_or_404(CategorieDepense.objects.select_for_update(), pk=categorie_id)
        category.actif = not category.actif
        category.save(update_fields=["actif", "updated_at"])
        label = "activée" if category.actif else "désactivée"
        log_activity(request.user, "autre", f"Catégorie de dépense #{category.pk} {label} : {category.nom}.", request)
    messages.success(request, gettext("Catégorie mise à jour. L'historique est conservé."))
    return redirect("comptable_depense_categories")


def _expense_csv_safe(value):
    if isinstance(value, str) and (value.startswith(("\t", "\r", "\n")) or value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@"))):
        return "'" + value
    return _csv_safe(value)


@never_cache
@comptable_required
@require_GET
def comptable_depenses_export_csv(request):
    expenses, form = _filtered_depenses(request)
    if not form.is_valid():
        return HttpResponse(gettext("Filtres invalides. Corrigez les filtres avant d'exporter."), status=400)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="depenses.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(["Référence", "Date", "Catégorie", "Libellé", "Bénéficiaire", "Moyen paiement", "Statut", "Montant", "Créé par", "Validé par", "Date validation"])
    for expense in expenses.iterator(chunk_size=500):
        values = [expense.reference, expense.date_depense.isoformat(), expense.categorie.nom,
                  expense.libelle, expense.beneficiaire, expense.get_moyen_paiement_display(),
                  expense.get_statut_display(), expense.montant, expense.cree_par.username,
                  expense.validee_par.username if expense.validee_par else "",
                  timezone.localtime(expense.date_validation).isoformat() if expense.date_validation else ""]
        writer.writerow([_expense_csv_safe(value) for value in values])
    return response
