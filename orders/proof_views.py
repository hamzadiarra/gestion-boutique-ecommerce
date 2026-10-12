from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib import messages
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.core.paginator import Paginator
from .delivery_views import private_delivery
from .delivery_permissions import role
from .models import Livraison
from .proof_models import PreuveLivraison, DemandeDerogation, RetourLivraison, AccesPreuve
from .pricing_models import TarifLivreur
from .proof_forms import SignatureForm, DerogationForm, RetourForm, TarifForm, DecisionTarifForm
from .proof_services import confirmer_signature, demander_derogation, decider_derogation, retour_client, est_admin
from .pricing_services import proposer_tarif, decider_tarif, creer_devis, normaliser_zone


def form_error(form):
    return HttpResponse(form.errors.as_text(), status=400, content_type="text/plain; charset=utf-8")


@private_delivery
@require_POST
def signature(request, livraison_id):
    get_object_or_404(Livraison, pk=livraison_id)
    form = SignatureForm(request.POST)
    if not form.is_valid():
        return form_error(form)
    confirmer_signature(livraison_id, request.user, **form.cleaned_data)
    return redirect("livraison_detail", livraison_id=livraison_id)


@private_delivery
@require_GET
def preuve(request, livraison_id):
    delivery = get_object_or_404(Livraison.objects.select_related("commande"), pk=livraison_id)
    if not request.user.is_active or not (est_admin(request.user) or delivery.commande.utilisateur_id == request.user.pk):
        raise PermissionDenied()
    item = get_object_or_404(PreuveLivraison, livraison=delivery)
    if item.expire_at <= timezone.now() or item.purged_at or not item.signature:
        return HttpResponse("Signature absente ou durée de conservation expirée.", status=410)
    AccesPreuve.objects.create(preuve=item, utilisateur=request.user)
    response = HttpResponse(bytes(item.signature), content_type="image/png")
    response["Content-Disposition"] = 'inline; filename="preuve-reception.png"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response


@private_delivery
@require_POST
def derogation(request, livraison_id):
    get_object_or_404(Livraison, pk=livraison_id)
    form = DerogationForm(request.POST)
    if not form.is_valid():
        return form_error(form)
    demander_derogation(livraison_id, request.user, **form.cleaned_data)
    return redirect("livraison_detail", livraison_id=livraison_id)


@private_delivery
@require_POST
def decision_derogation(request, demande_id):
    if not est_admin(request.user):
        raise PermissionDenied()
    get_object_or_404(DemandeDerogation, pk=demande_id)
    decision = request.POST.get("decision")
    if decision not in {"accordee", "refusee"}:
        return HttpResponse("Décision invalide", status=400)
    decider_derogation(demande_id, request.user, decision == "accordee", request.POST.get("motif", ""))
    return redirect("livraison_supervision")


@private_delivery
@require_POST
def retour(request, livraison_id):
    get_object_or_404(Livraison, pk=livraison_id)
    form = RetourForm(request.POST)
    if not form.is_valid():
        return form_error(form)
    retour_client(livraison_id, request.user, **form.cleaned_data)
    return redirect("livraison_detail", livraison_id=livraison_id)


def _tarifs_page(request, form=None, decision_id=None, decision_form=None, status=200):
    admin = est_admin(request.user)
    qs = TarifLivreur.objects.select_related("livreur").prefetch_related("historique__acteur")
    if not admin:
        qs = qs.filter(livreur=request.user)
    counts = {row["statut"]: row["total"] for row in qs.values("statut").annotate(total=Count("pk"))}
    filters = [("", "Tous")] + list(TarifLivreur._meta.get_field("statut").choices)
    plural_labels = {"propose": "Proposés", "approuve": "Approuvés", "refuse": "Refusés", "desactive": "Désactivés"}
    selected = request.GET.get("statut", "")
    if selected not in dict(filters):
        selected = ""
    if selected:
        qs = qs.filter(statut=selected)
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    if decision_id and not any(item.pk == decision_id for item in page):
        # Always show the errored offer rather than losing feedback on pagination/filter changes.
        page = Paginator(qs.model.objects.filter(pk=decision_id).select_related("livreur").prefetch_related("historique__acteur"), 20).get_page(1)
    for item in page:
        item.decision_form = decision_form if item.pk == decision_id else DecisionTarifForm(auto_id=f"decision_{item.pk}_%s")
    return render(request, "orders/delivery/tarifs.html", {
        "page_obj": page, "form": form if form is not None else TarifForm(), "admin_tarifs": admin,
        "filtre_actif": selected,
        "tarif_filtres": [{"value": value, "label": plural_labels.get(value, label),
            "count": counts.get(value, 0) if value else sum(counts.values())} for value, label in filters],
    }, status=status)


@private_delivery
@require_http_methods(["GET", "POST"])
def tarifs(request):
    admin = est_admin(request.user)
    if not request.user.is_active or not (admin or role(request.user) == "livreur"):
        raise PermissionDenied()
    if request.method == "POST":
        if admin:
            raise PermissionDenied()
        form = TarifForm(request.POST)
        if form.is_valid():
            try:
                proposer_tarif(request.user, **form.cleaned_data)
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, "Votre proposition a été envoyée à l’administration.")
                return redirect("livraison_tarifs")
        return _tarifs_page(request, form=form, status=400)
    return _tarifs_page(request)


@private_delivery
@require_POST
def decision_tarif(request, tarif_id):
    if not est_admin(request.user):
        raise PermissionDenied()
    get_object_or_404(TarifLivreur, pk=tarif_id)
    form = DecisionTarifForm(request.POST, auto_id=f"decision_{tarif_id}_%s")
    if not form.is_valid():
        return _tarifs_page(request, decision_id=tarif_id, decision_form=form, status=400)
    try:
        item = decider_tarif(tarif_id, request.user, **form.cleaned_data)
    except ValidationError as exc:
        form.add_error(None, exc)
        return _tarifs_page(request, decision_id=tarif_id, decision_form=form, status=409)
    messages.success(request, f"Offre #{item.pk} : {item.get_statut_display().lower()}. Décision enregistrée.")
    return redirect("livraison_tarifs")


@private_delivery
@require_GET
def offres(request):
    mode, ville = request.GET.get("mode", "standard"), request.GET.get("ville", "")
    if mode not in {"standard", "express"} or not ville.strip() or len(ville) > 100:
        return JsonResponse({"error": "Ville et mode valides requis."}, status=400)
    from django.db.models import Q
    qs = TarifLivreur.objects.filter(statut="approuve", mode=mode, livreur__is_active=True,
        livreur__profile__role="livreur").filter(Q(zone="") | Q(zone=normaliser_zone(ville))).select_related("livreur")
    return JsonResponse({"offres": [{"id": t.pk, "label": f"Offre #{t.pk} · {t.montant} FCFA", "montant": str(t.montant),
        "devis": creer_devis(t.pk, request.user, mode, ville)} for t in qs.order_by("montant", "pk")[:100]]})


@private_delivery
@require_GET
def supervision(request):
    if not est_admin(request.user):
        raise PermissionDenied()
    qs = Livraison.objects.select_related("commande", "livreur", "preuve").prefetch_related("retours")
    statut = request.GET.get("statut", "")
    if statut in dict(Livraison.STATUTS):
        qs = qs.filter(statut=statut)
    return render(request, "orders/delivery/supervision.html", {
        "page_obj": Paginator(qs, 20).get_page(request.GET.get("page")),
        "statuts": Livraison.STATUTS, "statut": statut,
        "compteurs": Livraison.objects.values("statut").annotate(total=Count("pk")),
        "derogations": DemandeDerogation.objects.filter(decision="attente").select_related("livraison", "livreur")[:100],
        "propositions": TarifLivreur.objects.filter(statut="propose").count(),
    })
