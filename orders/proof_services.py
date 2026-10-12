import base64
import binascii
import hashlib
import io
import os
from datetime import timedelta
from PIL import Image, ImageChops, UnidentifiedImageError
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models
from django.utils import timezone
from .delivery_permissions import role
from .delivery_services import operation_atomique, _verrouiller, _write, _historique, _notifier, participants
from .proof_models import PreuveLivraison, DemandeDerogation, RetourLivraison


def est_admin(user):
    return user.is_authenticated and user.is_active and (user.is_superuser or role(user) == "admin")


def retention_days():
    return max(1, int(getattr(settings, "DELIVERY_PROOF_RETENTION_DAYS", os.getenv("DELIVERY_PROOF_RETENTION_DAYS", "365"))))


def signature_png(value):
    if not isinstance(value, str) or not value.startswith("data:image/png;base64,") or len(value) > 180000:
        raise ValidationError("Signature PNG requise, 128 Kio maximum.")
    try:
        raw = base64.b64decode(value.split(",", 1)[1], validate=True)
        if not raw or len(raw) > 131072:
            raise ValueError()
        with Image.open(io.BytesIO(raw)) as im:
            if im.format != "PNG" or not (160 <= im.width <= 1200 and 80 <= im.height <= 600) or getattr(im, "n_frames", 1) != 1:
                raise ValueError()
            im.load()
            rgba = im.convert("RGBA")
            clean = Image.new("RGB", im.size, "white")
            clean.paste(rgba, mask=rgba.getchannel("A"))
            gray = clean.convert("L")
            dark = sum(gray.histogram()[:200])
            box = ImageChops.difference(clean, Image.new("RGB", clean.size, "white")).getbbox()
            if dark < 30 or not box or box[2]-box[0] < 20 or box[3]-box[1] < 8:
                raise ValueError()
            out = io.BytesIO()
            clean.save(out, format="PNG", optimize=True)
            data = out.getvalue()
            if len(data) > 131072:
                raise ValueError()
            return data
    except (ValueError, OSError, binascii.Error, UnidentifiedImageError, Image.DecompressionBombError):
        raise ValidationError("Signature vide, illisible, trop grande ou format non autorisé.")


def _nom(value):
    value = value.strip()
    if not 2 <= len(value) <= 150:
        raise ValidationError("Le nom du réceptionnaire doit contenir entre 2 et 150 caractères.")
    return value


def _livreur(delivery, actor):
    if not actor.is_active or role(actor) != "livreur" or delivery.livreur_id != actor.pk:
        raise PermissionDenied()


def _pret(delivery):
    if delivery.statut != "attente_signature" or delivery.commande.statut != "expediee":
        raise ValidationError("La livraison doit être en attente de signature.")
    if PreuveLivraison.objects.filter(livraison=delivery).exists():
        raise ValidationError("Cette livraison possède déjà une preuve.")


def _terminer(delivery, actor):
    old = delivery.statut
    now = timezone.now()
    _write(delivery, statut="livree", date_livraison=now)
    order = delivery.commande
    order.statut = "livree"
    order.date_livraison = now
    order._delivery_notification_managed = True
    order.save(update_fields=["statut", "date_livraison"])
    _historique(delivery, old, actor, "Remise confirmée avec preuve privée.", delivery.livreur_id)
    _notifier(delivery, participants(delivery), "Commande livrée : confirmez la réception ou signalez un problème", actor)


@operation_atomique
def confirmer_signature(livraison_id, actor, receptionnaire, signature, information_acceptee=False):
    delivery = _verrouiller(livraison_id)
    _livreur(delivery, actor)
    _pret(delivery)
    if not information_acceptee:
        raise ValidationError("Présentez la notice de preuve de réception au destinataire.")
    data = signature_png(signature)
    proof = PreuveLivraison.objects.create(livraison=delivery, livreur=actor,
        receptionnaire=_nom(receptionnaire), signature=data,
        empreinte=hashlib.sha256(data).hexdigest(), expire_at=timezone.now()+timedelta(days=retention_days()))
    _terminer(delivery, actor)
    return proof


@operation_atomique
def demander_derogation(livraison_id, actor, receptionnaire, motif):
    delivery = _verrouiller(livraison_id)
    _livreur(delivery, actor)
    _pret(delivery)
    if not 10 <= len(motif.strip()) <= 1000:
        raise ValidationError("Expliquez l'impossibilité de signer (10 à 1000 caractères).")
    if DemandeDerogation.objects.filter(livraison=delivery, decision="attente").exists():
        raise ValidationError("Une demande est déjà en attente.")
    item = DemandeDerogation.objects.create(livraison=delivery, livreur=actor,
        receptionnaire=_nom(receptionnaire), motif=motif.strip())
    _historique(delivery, delivery.statut, actor, "Dérogation demandée : examen administratif requis.")
    return item


@operation_atomique
def decider_derogation(demande_id, actor, accepter, motif):
    if not est_admin(actor):
        raise PermissionDenied()
    delivery_id = DemandeDerogation.objects.values_list("livraison_id", flat=True).get(pk=demande_id)
    delivery = _verrouiller(delivery_id)
    item = DemandeDerogation.objects.select_for_update().get(pk=demande_id)
    if item.decision != "attente" or not 10 <= len(motif.strip()) <= 1000:
        raise ValidationError("Décision déjà prise ou motif administratif insuffisant.")
    if accepter:
        _pret(delivery)
        if delivery.livreur_id != item.livreur_id:
            raise ValidationError("Le livreur a changé ; une nouvelle demande est nécessaire.")
        PreuveLivraison.objects.create(livraison=delivery, livreur=item.livreur,
            receptionnaire=item.receptionnaire, exceptionnelle=True, autorisee_par=actor,
            motif=item.motif, expire_at=timezone.now()+timedelta(days=retention_days()))
        _terminer(delivery, actor)
    models.QuerySet(model=DemandeDerogation).filter(pk=item.pk).update(
        decision="accordee" if accepter else "refusee", administrateur=actor,
        motif_decision=motif.strip(), decided_at=timezone.now())
    _historique(delivery, delivery.statut, actor, "Dérogation accordée." if accepter else "Dérogation refusée.")
    return item


@operation_atomique
def retour_client(livraison_id, actor, type, note=None, commentaire=""):
    delivery = _verrouiller(livraison_id)
    if not actor.is_active or delivery.commande.utilisateur_id != actor.pk:
        raise PermissionDenied()
    if type not in {"confirmation", "probleme"}:
        raise ValidationError("Choix de retour invalide.")
    if type == "confirmation" and delivery.statut != "livree":
        raise ValidationError("La remise doit être enregistrée avant la confirmation client.")
    if type == "probleme" and delivery.statut not in {"en_route", "arrive", "attente_signature", "livree", "echec"}:
        raise ValidationError("Ce statut ne permet pas cette réclamation.")
    if type == "probleme" and len(commentaire.strip()) < 10:
        raise ValidationError("Décrivez le problème (10 caractères minimum).")
    if RetourLivraison.objects.filter(livraison=delivery, type=type).exists():
        raise ValidationError("Ce retour a déjà été enregistré.")
    item = RetourLivraison.objects.create(livraison=delivery, client=actor, type=type,
        note=note, commentaire=commentaire.strip())
    old = delivery.statut
    if type == "probleme":
        _write(delivery, statut="contestee")
    _historique(delivery, old, actor, "Réception confirmée par le client." if type == "confirmation" else "Livraison contestée par le client.")
    _notifier(delivery, participants(delivery), "Nouveau retour client sur la livraison", actor)
    return item
