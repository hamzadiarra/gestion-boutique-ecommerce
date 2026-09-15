from django.utils.translation import gettext
import time
import uuid
from functools import wraps

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, models, transaction, OperationalError
from django.db.models import Q, F, Count, OuterRef, Subquery, Value, Max
from django.db.models.functions import Coalesce, Greatest
from django.urls import reverse
from django.utils import timezone

from notifications.models import Notification
from .models import Order, Livraison, HistoriqueLivraison, MessageLivraison, LectureLivraison
from .delivery_models import TERMINAUX, MOTIFS
from .delivery_permissions import peut_gerer_livraison, peut_ecrire_livraison, exiger_acces, role

SUIVANTS = {"affectee": ["acceptee"], "acceptee": ["en_preparation", "prete"],
            "en_preparation": ["prete"], "prete": ["en_route"], "en_route": ["arrive"], "arrive": ["livree"]}
BOUTIQUE_ACTIONS = {"en_preparation", "prete", "annulee"}
DATE_ACTION = {"acceptee": "date_acceptation", "prete": "date_prete", "en_route": "date_depart", "arrive": "date_arrivee", "livree": "date_livraison"}


def operation_atomique(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        for attempt in range(6):
            try:
                with transaction.atomic():
                    return function(*args, **kwargs)
            except OperationalError as exc:
                if connection.in_atomic_block or connection.vendor != "sqlite" or "locked" not in str(exc).lower() or attempt == 5:
                    raise
                time.sleep(.04 * (attempt + 1))
    return wrapped


def _verrouiller(livraison_id):
    # Commercial order first everywhere, including cancellation and reassignment.
    order_id = Livraison.objects.filter(pk=livraison_id).values_list("commande_id", flat=True).get()
    Order.objects.filter(pk=order_id).update(statut=F("statut"))
    Order.objects.select_for_update().get(pk=order_id)
    return Livraison.objects.select_for_update().select_related("commande", "livreur").get(pk=livraison_id)


def boutique_users():
    return User.objects.filter(is_active=True).filter(Q(is_superuser=True) | Q(profile__role__in=["admin", "vendeur"])).distinct()


def participants(livraison):
    ids = set(boutique_users().values_list("pk", flat=True))
    ids.add(livraison.commande.utilisateur_id)
    if livraison.livreur_id:
        ids.add(livraison.livreur_id)
    return User.objects.filter(pk__in=ids, is_active=True).select_related("profile")


def _notifier(livraison, recipients, titre, actor=None):
    for user in recipients:
        if actor and user.pk == actor.pk:
            continue
        from .delivery_permissions import peut_acceder_livraison
        if not peut_acceder_livraison(user, livraison):
            continue
        # No address, telephone or message body in notifications/offline payloads.
        Notification.objects.create(utilisateur=user, titre=titre, type_notification="livraison",
            message=f"{livraison.reference} · commande #{livraison.commande_id}",
            lien=reverse("livraison_detail", args=[livraison.pk]))


def _historique(livraison, old, actor, commentaire="", ancien_livreur=None):
    HistoriqueLivraison.objects.create(livraison=livraison, ancien_statut=old, nouveau_statut=livraison.statut,
        utilisateur=actor, ancien_livreur_id=ancien_livreur, nouveau_livreur_id=livraison.livreur_id, commentaire=commentaire)


def _write(livraison, **changes):
    models.QuerySet(model=Livraison, using=connection.alias).filter(pk=livraison.pk).update(**changes, updated_at=timezone.now())
    livraison.refresh_from_db()


@operation_atomique
def initialiser_livraison(commande, actor, checkout=False):
    if not checkout and not peut_gerer_livraison(actor):
        raise PermissionDenied()
    if checkout and commande.utilisateur_id != actor.pk:
        raise PermissionDenied()
    Order.objects.filter(pk=commande.pk).update(statut=F("statut"))
    commande = Order.objects.select_for_update().get(pk=commande.pk)
    existing = Livraison.objects.filter(commande=commande).first()
    if existing:
        return existing
    if not commande.est_livrable or commande.statut not in {"en_attente", "confirmee", "expediee"}:
        raise ValidationError(gettext("Cette commande n'est pas éligible à une livraison."))
    delivery = Livraison.objects.create(commande=commande)
    _historique(delivery, "", actor, "Livraison initialisée, en attente de confirmation commerciale et d'affectation.")
    return delivery


@operation_atomique
def affecter_livreur(livraison_id, livreur_id, actor, commentaire="", request=None):
    delivery = _verrouiller(livraison_id)
    if not peut_gerer_livraison(actor, delivery):
        raise PermissionDenied()
    if delivery.terminee or delivery.commande.statut not in {"confirmee", "expediee"}:
        raise ValidationError(gettext("Affectation réservée aux commandes confirmées et livraisons non terminées."))
    driver = User.objects.select_for_update().filter(pk=livreur_id, is_active=True, profile__role="livreur").first()
    if not driver:
        raise ValidationError(gettext("Choisissez un utilisateur actif ayant le rôle livreur."))
    if delivery.livreur_id == driver.pk:
        return delivery
    old_driver, old = delivery.livreur_id, delivery.statut
    _write(delivery, livreur=driver, statut="affectee", date_affectation=timezone.now(),
        date_acceptation=None, date_prete=None, date_depart=None, date_arrivee=None, date_livraison=None)
    _historique(delivery, old, actor, commentaire.strip(), old_driver)
    from dashboard.models import log_activity
    log_activity(actor, "autre", f"Livraison {delivery.reference} : affectation {old_driver or 'aucun'} vers {driver.username}. {commentaire}", request)
    _notifier(delivery, [driver], "Nouvelle livraison affectée", actor)
    _notifier(delivery, User.objects.filter(pk=delivery.commande.utilisateur_id), "Livreur affecté à votre commande", actor)
    return delivery


reaffecter_livreur = affecter_livreur


def actions_autorisees(user, delivery):
    if delivery.terminee or delivery.commande.statut not in {"confirmee", "expediee"}:
        return []
    if peut_gerer_livraison(user, delivery):
        return [s for s in SUIVANTS.get(delivery.statut, []) if s in BOUTIQUE_ACTIONS] + ["annulee"]
    if role(user) == "livreur" and user.is_active and delivery.livreur_id == user.pk:
        actions = [s for s in SUIVANTS.get(delivery.statut, []) if s not in BOUTIQUE_ACTIONS]
        if delivery.statut in {"acceptee", "en_preparation", "prete", "en_route", "arrive"}:
            actions.append("echec")
        return actions
    return []


@operation_atomique
def changer_statut_livraison(livraison_id, target, actor, motif="", commentaire="", request=None):
    delivery = _verrouiller(livraison_id)
    exiger_acces(actor, delivery)
    # Check actor responsibility before accepting a repeated event.
    permitted_actor = peut_gerer_livraison(actor) if target in BOUTIQUE_ACTIONS else role(actor) == "livreur" and delivery.livreur_id == actor.pk
    if not permitted_actor:
        raise PermissionDenied()
    if delivery.statut == target:
        return delivery
    if target not in actions_autorisees(actor, delivery):
        raise ValidationError(gettext("Transition non autorisée dans cet état."))
    changes = {"statut": target}
    if target == "echec":
        if motif not in dict(MOTIFS) or (motif == "autre" and not commentaire.strip()):
            raise ValidationError(gettext("Précisez le motif de l'échec (et un commentaire pour Autre)."))
        changes.update(motif_echec=motif, commentaire_echec=commentaire.strip())
    if target in DATE_ACTION:
        changes[DATE_ACTION[target]] = timezone.now()
    old = delivery.statut
    _write(delivery, **changes)
    _historique(delivery, old, actor, commentaire.strip(), delivery.livreur_id)
    order = delivery.commande
    desired = {"en_route": "expediee", "livree": "livree"}.get(target)
    if desired and order.statut != desired:
        order.statut = desired
        date_field = "date_expedition" if desired == "expediee" else "date_livraison"
        setattr(order, date_field, getattr(delivery, DATE_ACTION[target]))
        order._delivery_notification_managed = True
        order.save(update_fields=["statut", date_field])
    titres = {"acceptee": "Livraison acceptée", "en_preparation": "Commande en préparation", "prete": "Livraison prête",
              "en_route": "Votre commande est en route", "arrive": "Votre livreur est arrivé", "livree": "Commande livrée",
              "echec": "Échec de livraison", "annulee": "Livraison annulée"}
    recipients = participants(delivery) if target in {"acceptee", "livree", "echec", "annulee"} else User.objects.filter(pk=delivery.livreur_id if target == "prete" else order.utilisateur_id)
    _notifier(delivery, recipients, titres[target], actor)
    if target == "annulee":
        from dashboard.models import log_activity
        log_activity(actor, "autre", f"Livraison {delivery.reference} annulée. {commentaire}", request, "warning")
    return delivery


@operation_atomique
def annuler_pour_commande(commande, actor=None):
    delivery = Livraison.objects.select_for_update().filter(commande=commande).first()
    if not delivery or delivery.terminee:
        return
    old = delivery.statut
    _write(delivery, statut="annulee")
    _historique(delivery, old, actor, "Annulation de la commande commerciale.", delivery.livreur_id)
    _notifier(delivery, participants(delivery), "Livraison annulée avec la commande", actor)
    if actor:
        from dashboard.models import log_activity
        log_activity(actor, "autre", f"Livraison {delivery.reference} annulée avec la commande.", niveau="warning")


@operation_atomique
def envoyer_message_livraison(livraison_id, actor, message, cle_envoi=None):
    delivery = _verrouiller(livraison_id)
    exiger_acces(actor, delivery)
    key = cle_envoi or uuid.uuid4()
    existing = MessageLivraison.objects.filter(cle_envoi=key).first()
    if existing:
        if existing.auteur_id != actor.pk or existing.livraison_id != delivery.pk:
            raise PermissionDenied()
        return existing
    if not peut_ecrire_livraison(actor, delivery):
        raise ValidationError(gettext("La discussion est en lecture seule après un statut terminal."))
    item = MessageLivraison.objects.create(livraison=delivery, auteur=actor, message=message, cle_envoi=key)
    _notifier(delivery, participants(delivery), "Nouveau message de livraison", actor)
    return item


@operation_atomique
def marquer_lu(livraison_id, actor, dernier_id):
    delivery = _verrouiller(livraison_id)
    exiger_acces(actor, delivery)
    maximum = delivery.messages.aggregate(maximum=Max("pk"))["maximum"] or 0
    dernier_id = min(maximum, max(0, dernier_id))
    state, _ = LectureLivraison.objects.get_or_create(livraison=delivery, utilisateur=actor)
    LectureLivraison.objects.filter(pk=state.pk).update(dernier_message_id=Greatest(F("dernier_message_id"), Value(dernier_id)))


def avec_non_lus(queryset, user):
    read = LectureLivraison.objects.filter(livraison_id=OuterRef("livraison_id"), utilisateur=user).values("dernier_message_id")[:1]
    unread = MessageLivraison.objects.filter(livraison_id=OuterRef("pk")).exclude(auteur=user).annotate(last_read=Coalesce(Subquery(read), Value(0), output_field=models.BigIntegerField())).filter(pk__gt=F("last_read")).values("livraison_id").annotate(total=Count("pk")).values("total")[:1]
    return queryset.annotate(non_lus=Coalesce(Subquery(unread), Value(0)))
