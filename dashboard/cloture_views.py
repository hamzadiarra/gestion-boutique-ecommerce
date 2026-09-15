from django.utils.translation import gettext
import csv
from pathlib import Path

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .cloture_forms import ClotureForm, ClotureFiltreForm
from .cloture_services import cloture_a_mouvements_posterieurs, transition_cloture, indicateurs_clotures, snapshot_a_date
from .depense_views import _expense_csv_safe
from .finance_views import finance_access
from .models import ClotureFinanciere, JournalActivite, log_activity


def _filtered(request):
    form = ClotureFiltreForm(request.GET)
    closures = ClotureFinanciere.objects.select_related("compte", "cree_par", "validee_par")
    if not form.is_valid():
        return closures.none(), form
    data = form.cleaned_data
    for key in ("compte", "statut"):
        if data[key]:
            closures = closures.filter(**{key: data[key]})
    if data["type_compte"]:
        closures = closures.filter(compte__type_compte=data["type_compte"])
    if data["date_debut"]:
        closures = closures.filter(date_cloture__gte=data["date_debut"])
    if data["date_fin"]:
        closures = closures.filter(date_cloture__lte=data["date_fin"])
    if data["ecart"]:
        lookup = {"conforme": "ecart", "positif": "ecart__gt", "negatif": "ecart__lt"}[data["ecart"]]
        closures = closures.filter(**{lookup: 0})
    return closures.order_by("-date_cloture", "-pk"), form


@finance_access
@require_GET
def liste(request):
    closures, form = _filtered(request)
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "dashboard/clotures/liste.html", {
        "page_obj": Paginator(closures, 25).get_page(request.GET.get("page")),
        "filtre_form": form, "query_params": params.urlencode(), **indicateurs_clotures(),
    })


@finance_access
@require_http_methods(["GET", "POST"])
def formulaire(request, cloture_id=None):
    with transaction.atomic():
        closure = get_object_or_404(ClotureFinanciere.objects.select_for_update(), pk=cloture_id) if cloture_id else ClotureFinanciere(cree_par=request.user)
        if closure.statut != "brouillon":
            return HttpResponseForbidden(gettext("Une clôture validée ou annulée est figée."))
        form = ClotureForm(request.POST if request.method == "POST" else None, request.FILES or None, instance=closure)
        if request.method == "POST" and form.is_valid():
            try:
                with transaction.atomic():
                    closure = form.save()
                    verb = "modifiée en brouillon" if cloture_id else "créée en brouillon"
                    log_activity(request.user, "autre", f"Clôture {closure.reference} {verb} : {closure.compte.nom}, écart {closure.ecart} {closure.devise}.", request)
                return redirect("comptable_cloture_detail", cloture_id=closure.pk)
            except ValidationError as exc:
                form.add_error(None, "; ".join(exc.messages))
    return render(request, "dashboard/clotures/formulaire.html", {"form": form, "cloture": closure})


@finance_access
@require_GET
def detail(request, cloture_id):
    closure = get_object_or_404(ClotureFinanciere.objects.select_related("compte", "cree_par", "validee_par"), pk=cloture_id)
    return render(request, "dashboard/clotures/detail.html", {
        "cloture": closure, "retroactif": cloture_a_mouvements_posterieurs(closure),
        "snapshot_actuel": snapshot_a_date(closure.compte, closure.date_cloture) if closure.statut == "brouillon" else None,
        "activites": JournalActivite.objects.filter(details__startswith=f"Clôture {closure.reference} ").select_related("utilisateur")[:50],
    })


@finance_access
@require_POST
def transition(request, cloture_id, target):
    get_object_or_404(ClotureFinanciere, pk=cloture_id)
    try:
        transition_cloture(cloture_id, target, request.user, request)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return HttpResponse("; ".join(exc.messages), status=409)
    messages.success(request, gettext("Clôture mise à jour. Aucun mouvement financier créé."))
    return redirect("comptable_cloture_detail", cloture_id=cloture_id)


@finance_access
@require_GET
def justificatif(request, cloture_id):
    closure = get_object_or_404(ClotureFinanciere, pk=cloture_id)
    if not closure.justificatif:
        raise Http404(gettext("Aucun justificatif."))
    try:
        stream = closure.justificatif.open("rb")
    except (OSError, ValueError) as exc:
        raise Http404(gettext("Justificatif introuvable.")) from exc
    response = FileResponse(stream, as_attachment=True, filename=f"{closure.reference}-justificatif{Path(closure.justificatif.name).suffix}", content_type="application/octet-stream")
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response


@finance_access
@require_GET
def export(request):
    closures, _ = _filtered(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="clotures-financieres.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(["Référence", "Date", "Compte", "Type", "Devise", "Solde théorique", "Solde constaté", "Écart", "Statut", "Créé par", "Validé par", "Date validation"])
    for c in closures.iterator(chunk_size=500):
        writer.writerow([_expense_csv_safe(str(v)) for v in (
            c.reference, c.date_cloture.isoformat(), c.compte.nom, c.compte.get_type_compte_display(), c.devise,
            c.solde_theorique, c.solde_constate, c.ecart, c.get_statut_display(), c.cree_par.username,
            c.validee_par.username if c.validee_par_id else "", c.date_validation.isoformat() if c.date_validation else "",
        )])
    return response
