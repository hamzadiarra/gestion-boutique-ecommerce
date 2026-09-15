from django.utils.translation import gettext
import csv
import uuid
from functools import wraps

from django.contrib import messages
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts.decorators import comptable_required
from .depense_views import _expense_csv_safe
from .finance_forms import CompteForm, TransfertForm, AjustementForm, MouvementFiltreForm
from .finance_services import ajuster, transferer, regulariser, liquidites
from .models import CompteFinancier, MouvementFinancier, log_activity


def finance_access(view):
    @never_cache
    @comptable_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except (IntegrityError, OperationalError):
            return HttpResponse(gettext("Conflit concurrent. Rechargez la page puis réessayez ; aucune opération partielle n'est conservée."), status=409)
    return wrapped


@finance_access
@require_GET
def comptes(request):
    return render(request, "dashboard/finance/comptes.html", {"comptes": CompteFinancier.avec_soldes(), **liquidites()})


@finance_access
@require_http_methods(["GET", "POST"])
def compte_form(request, compte_id=None):
    with transaction.atomic():
        account = get_object_or_404(CompteFinancier.objects.select_for_update(), pk=compte_id) if compte_id else CompteFinancier(cree_par=request.user)
        previous_default = account.est_par_defaut
        form = CompteForm(request.POST if request.method == "POST" else None, instance=account)
        if request.method == "POST" and form.is_valid():
            try:
                with transaction.atomic():
                    account = form.save()
                    verb = "modifié" if compte_id else "créé"
                    log_activity(request.user, "autre", f"Compte {account.pk} {account.nom} {verb}. Actif={account.actif}, défaut={account.est_par_defaut} (avant={previous_default}).", request)
                return redirect("comptable_compte_detail", compte_id=account.pk)
            except ValidationError as exc:
                form.add_error(None, "; ".join(exc.messages))
    return render(request, "dashboard/finance/formulaire.html", {"form": form, "titre": "Modifier le compte" if compte_id else "Nouveau compte", "compte": account})


@finance_access
@require_POST
def compte_toggle(request, compte_id):
    with transaction.atomic():
        account = get_object_or_404(CompteFinancier.objects.select_for_update(), pk=compte_id)
        account.actif = not account.actif
        try:
            account.save()
        except ValidationError as exc:
            return HttpResponse("; ".join(exc.messages), status=409)
        log_activity(request.user, "autre", f"Compte {account.pk} {account.nom} : actif={account.actif}, défaut={account.est_par_defaut}.", request)
    return redirect("comptable_compte_detail", compte_id=compte_id)


def _filtered(request):
    form = MouvementFiltreForm(request.GET)
    movements = MouvementFinancier.objects.select_related("compte", "cree_par", "vente", "paiement", "depense", "transfert")
    if not form.is_valid():
        return movements.none(), form
    data = form.cleaned_data
    for key in ("compte", "sens", "type_mouvement"):
        if data[key]:
            movements = movements.filter(**{key: data[key]})
    if data["type_compte"]:
        movements = movements.filter(type_compte_attendu=data["type_compte"])
    if data["date_debut"]:
        movements = movements.filter(date_mouvement__date__gte=data["date_debut"])
    if data["date_fin"]:
        movements = movements.filter(date_mouvement__date__lte=data["date_fin"])
    if data["q"]:
        q = data["q"]
        movements = movements.filter(Q(reference__icontains=q) | Q(libelle__icontains=q) | Q(description__icontains=q) | Q(compte__nom__icontains=q) | Q(depense__reference__icontains=q) | Q(transfert__reference__icontains=q) | Q(paiement__reference__icontains=q))
    return movements.order_by("-date_mouvement", "-pk"), form


@finance_access
@require_GET
def journal(request, compte_id=None):
    movements, form = _filtered(request)
    account = get_object_or_404(CompteFinancier.avec_soldes(), pk=compte_id) if compte_id else None
    if account:
        movements = movements.filter(compte=account)
    params = request.GET.copy()
    params.pop("page", None)
    if account:
        params["compte"] = account.pk
    return render(request, "dashboard/finance/journal.html", {
        "compte": account, "filtre_form": form, "query_params": params.urlencode(),
        "page_obj": Paginator(movements, 25).get_page(request.GET.get("page")),
    })


@finance_access
@require_GET
def export(request):
    movements, _ = _filtered(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="journal-financier.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(["Référence", "Date", "Compte", "Type compte", "Sens", "Type mouvement", "Source", "Libellé", "Montant", "Créé par"])
    for m in movements.iterator(chunk_size=500):
        writer.writerow([_expense_csv_safe(str(v)) for v in [m.reference, m.date_mouvement.isoformat(),
            m.compte.nom if m.compte_id else "À régulariser", m.get_type_compte_attendu_display(), m.get_sens_display(),
            m.get_type_mouvement_display(), m.source, m.libelle, m.montant, m.cree_par.username if m.cree_par_id else "Système"]])
    return response


@finance_access
@require_http_methods(["GET", "POST"])
def operation(request, kind):
    form_class = TransfertForm if kind == "transfert" else AjustementForm
    token = signing.dumps({"user": request.user.pk, "kind": kind, "key": str(uuid.uuid4())}, salt="finance-operation")
    initial = {"jeton": token}
    if request.method == "GET" and kind == "ajustement" and request.GET.get("cloture", "").isdigit():
        from .models import ClotureFinanciere
        closure = get_object_or_404(ClotureFinanciere, pk=request.GET["cloture"], statut="validee", compte__actif=True)
        if closure.ecart:
            initial.update(compte=closure.compte_id, sens="entree" if closure.ecart > 0 else "sortie",
                           montant=abs(closure.ecart), motif=f"Écart constaté clôture {closure.reference}")
    form = form_class(request.POST if request.method == "POST" else None, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            payload = signing.loads(data["jeton"], salt="finance-operation", max_age=86400)
            if payload["user"] != request.user.pk or payload["kind"] != kind:
                raise signing.BadSignature()
            key = uuid.UUID(payload["key"])
            if kind == "transfert":
                result = transferer(data["compte_source"].pk, data["compte_destination"].pk, data["montant"], data["date"], data["motif"], request.user, key, request)
                account = result.compte_source
            else:
                result = ajuster(data["compte"].pk, data["sens"], data["montant"], data["date"], data["motif"], request.user, key, request)
                account = result.compte
            messages.success(request, gettext("Opération {reference} enregistrée.").format(reference=result.reference))
            if account.solde_theorique < 0:
                messages.warning(request, gettext("Attention : le solde théorique du compte est négatif."))
            return redirect("comptable_compte_detail", compte_id=account.pk)
        except signing.BadSignature:
            form.add_error("jeton", "Formulaire expiré ou invalide : rechargez la page.")
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
    return render(request, "dashboard/finance/formulaire.html", {"form": form, "titre": "Nouveau transfert" if kind == "transfert" else "Nouvel ajustement"})


@finance_access
@require_GET
def regularisations(request):
    movements = MouvementFinancier.objects.filter(compte__isnull=True).select_related("depense", "paiement")
    page = Paginator(movements, 25).get_page(request.GET.get("page"))
    accounts = list(CompteFinancier.objects.filter(actif=True))
    for movement in page:
        movement.comptes_compatibles = [a for a in accounts if a.type_compte == movement.type_compte_attendu and a.devise == movement.devise]
    return render(request, "dashboard/finance/regularisations.html", {"page_obj": page})


@finance_access
@require_POST
def affecter(request, mouvement_id):
    get_object_or_404(MouvementFinancier, pk=mouvement_id)
    try:
        account_id = int(request.POST.get("compte", ""))
    except (ValueError, TypeError):
        return HttpResponse(gettext("Compte obligatoire."), status=400)
    get_object_or_404(CompteFinancier, pk=account_id)
    try:
        regulariser(mouvement_id, account_id, request.user, request)
    except ValidationError as exc:
        return HttpResponse("; ".join(str(gettext(message)) for message in exc.messages), status=409)
    return redirect("comptable_regularisations")
