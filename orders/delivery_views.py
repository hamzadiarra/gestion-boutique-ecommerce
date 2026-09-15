import uuid
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, OperationalError
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from accounts.decorators import livreur_required
from .models import Livraison, Order
from .delivery_forms import AffectationForm, ActionLivraisonForm, MessageLivraisonForm, FiltreLivraisonForm
from .delivery_permissions import peut_gerer_livraison, peut_ecrire_livraison, exiger_acces
from .delivery_services import (affecter_livreur, changer_statut_livraison, envoyer_message_livraison,
    initialiser_livraison, marquer_lu, avec_non_lus, actions_autorisees)


def private_delivery(view):
    @never_cache
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except ValidationError as exc:
            return HttpResponse("; ".join(exc.messages), status=409, content_type="text/plain; charset=utf-8")
        except (IntegrityError, OperationalError):
            return HttpResponse(gettext("Une opération concurrente est en cours. Réessayez sans changer le formulaire."), status=409, content_type="text/plain; charset=utf-8")
    return wrapped


def _delivery(request, livraison_id):
    delivery = get_object_or_404(Livraison.objects.select_related("commande__utilisateur", "livreur"), pk=livraison_id)
    exiger_acces(request.user, delivery)
    return delivery


def _liste(request, driver=False):
    deliveries = Livraison.objects.select_related("commande__utilisateur", "livreur")
    if driver:
        deliveries = deliveries.filter(livreur=request.user)
    elif not peut_gerer_livraison(request.user):
        raise PermissionDenied()
    form = FiltreLivraisonForm(request.GET)
    if form.is_valid():
        data = form.cleaned_data
        for key in ("statut", "livreur"):
            if data[key]:
                deliveries = deliveries.filter(**{key: data[key]})
        if data["date"]:
            deliveries = deliveries.filter(created_at__date=data["date"])
        if data["q"]:
            q = data["q"]
            match = Q(reference__icontains=q) | Q(commande__utilisateur__username__icontains=q) | Q(commande__utilisateur__first_name__icontains=q) | Q(commande__utilisateur__last_name__icontains=q)
            if q.isdigit():
                match |= Q(commande_id=int(q))
            deliveries = deliveries.filter(match)
        section = data["section"]
        if section == "a_accepter":
            deliveries = deliveries.filter(statut="affectee")
        elif section == "a_affecter":
            deliveries = deliveries.filter(statut="a_affecter")
        elif section == "en_cours":
            deliveries = deliveries.filter(statut__in=["acceptee", "en_preparation", "prete", "en_route", "arrive"])
        elif section == "terminees":
            deliveries = deliveries.filter(statut__in=["livree", "annulee"])
        elif section == "echecs":
            deliveries = deliveries.filter(statut="echec")
        elif section == "livrees_jour":
            deliveries = deliveries.filter(statut="livree", date_livraison__date=timezone.localdate())
    else:
        deliveries = deliveries.none()
    deliveries = avec_non_lus(deliveries, request.user).order_by("-created_at", "-pk")
    return render(request, "orders/delivery/liste.html", {"page_obj": Paginator(deliveries, 20).get_page(request.GET.get("page")), "filtre_form": form, "espace_livreur": driver})


@private_delivery
@livreur_required
@require_GET
def livreur_dashboard(request):
    return _liste(request, driver=True)


@private_delivery
@require_GET
def boutique_livraisons(request):
    return _liste(request)


@private_delivery
@require_GET
def detail(request, livraison_id):
    delivery = _delivery(request, livraison_id)
    discussion = Paginator(delivery.messages.select_related("auteur").order_by("created_at", "pk"), 50)
    messages_page = discussion.get_page(request.GET.get("discussion_page", discussion.num_pages))
    items = list(messages_page.object_list)
    if items:
        marquer_lu(delivery.pk, request.user, max(m.pk for m in items))
    token = signing.dumps({"user": request.user.pk, "livraison": delivery.pk, "key": str(uuid.uuid4())}, salt="delivery-message")
    return render(request, "orders/delivery/detail.html", {
        "livraison": delivery, "commande": delivery.commande,
        "gerer": peut_gerer_livraison(request.user, delivery), "ecrire": peut_ecrire_livraison(request.user, delivery),
        "actions": [(a, dict(Livraison.STATUTS)[a]) for a in actions_autorisees(request.user, delivery)],
        "affectation_form": AffectationForm(), "action_form": ActionLivraisonForm(),
        "message_form": MessageLivraisonForm(initial={"jeton": token}), "messages_page": messages_page,
        "discussion": items, "historique": delivery.historique.select_related("utilisateur", "ancien_livreur", "nouveau_livreur"),
    })


@private_delivery
@require_GET
def order_delivery(request, order_id):
    delivery = get_object_or_404(Livraison.objects.select_related("commande"), commande_id=order_id)
    exiger_acces(request.user, delivery)
    return redirect("livraison_detail", livraison_id=delivery.pk)


@private_delivery
@require_POST
def initialiser(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
    delivery = initialiser_livraison(order, request.user)
    return redirect("livraison_detail", livraison_id=delivery.pk)


@private_delivery
@require_POST
def affecter(request, livraison_id):
    _delivery(request, livraison_id)
    if not peut_gerer_livraison(request.user):
        raise PermissionDenied()
    form = AffectationForm(request.POST)
    if not form.is_valid():
        return HttpResponse(form.errors.as_text(), status=400, content_type="text/plain; charset=utf-8")
    affecter_livreur(livraison_id, form.cleaned_data["livreur"].pk, request.user, form.cleaned_data["commentaire"], request)
    return redirect("livraison_detail", livraison_id=livraison_id)


@private_delivery
@require_POST
def action(request, livraison_id):
    _delivery(request, livraison_id)
    form = ActionLivraisonForm(request.POST)
    if not form.is_valid():
        return HttpResponse(form.errors.as_text(), status=400, content_type="text/plain; charset=utf-8")
    data = form.cleaned_data
    changer_statut_livraison(livraison_id, data["action"], request.user, data["motif_echec"], data["commentaire"], request)
    return redirect("livraison_detail", livraison_id=livraison_id)


@private_delivery
@require_POST
def message(request, livraison_id):
    _delivery(request, livraison_id)
    form = MessageLivraisonForm(request.POST)
    if not form.is_valid():
        return HttpResponse(form.errors.as_text(), status=400, content_type="text/plain; charset=utf-8")
    try:
        payload = signing.loads(form.cleaned_data["jeton"], salt="delivery-message", max_age=86400)
        if payload["user"] != request.user.pk or payload["livraison"] != livraison_id:
            raise signing.BadSignature()
        key = uuid.UUID(payload["key"])
    except (signing.BadSignature, ValueError, KeyError):
        return HttpResponse(gettext("Formulaire expiré ou invalide : rechargez la discussion."), status=400)
    envoyer_message_livraison(livraison_id, request.user, form.cleaned_data["message"], key)
    return redirect("livraison_detail", livraison_id=livraison_id)
