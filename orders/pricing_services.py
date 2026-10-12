from decimal import Decimal, InvalidOperation
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models
from .delivery_permissions import role
from .delivery_services import operation_atomique
from .proof_services import est_admin
from .pricing_models import TarifLivreur, HistoriqueTarif


def normaliser_zone(value):
    return " ".join(value.strip().casefold().split())


@operation_atomique
def proposer_tarif(actor, mode, montant, zone=""):
    if not actor.is_authenticated or not actor.is_active or role(actor) != "livreur":
        raise PermissionDenied()
    try:
        amount = Decimal(str(montant))
        if not amount.is_finite() or amount < 0 or amount > Decimal("99999999.99") or amount != amount.quantize(Decimal("0.01")):
            raise ValueError()
    except (InvalidOperation, ValueError):
        raise ValidationError("Montant invalide : nombre positif avec deux décimales maximum.")
    item = TarifLivreur.objects.create(livreur=actor, mode=mode, montant=amount, zone=normaliser_zone(zone))
    HistoriqueTarif.objects.create(tarif=item, acteur=actor, statut="propose", motif="Proposition du livreur")
    return item


@operation_atomique
def decider_tarif(tarif_id, actor, statut, motif):
    if not est_admin(actor):
        raise PermissionDenied()
    # Acquire the SQLite write lock too; PostgreSQL uses the row lock below.
    models.QuerySet(model=TarifLivreur).filter(pk=tarif_id).update(statut=models.F("statut"))
    item = TarifLivreur.objects.select_for_update().get(pk=tarif_id)
    if statut not in {"approuve", "refuse", "desactive"} or not 5 <= len(motif.strip()) <= 1000:
        raise ValidationError("Décision ou motif invalide.")
    allowed = {"propose": {"approuve", "refuse"}, "approuve": {"desactive"}}
    if statut not in allowed.get(item.statut, set()):
        raise ValidationError("Ce tarif a déjà été traité. Proposez une nouvelle version.")
    models.QuerySet(model=TarifLivreur).filter(pk=item.pk).update(statut=statut)
    HistoriqueTarif.objects.create(tarif=item, acteur=actor, statut=statut, motif=motif.strip())
    item.refresh_from_db()
    return item


def _offre(tarif_id, mode, ville, lock=False):
    qs = TarifLivreur.objects.select_related("livreur")
    if lock:
        qs = qs.select_for_update()
    item = qs.filter(pk=tarif_id, statut="approuve", mode=mode,
                     livreur__is_active=True, livreur__profile__role="livreur").first()
    if not item or (item.zone and item.zone != normaliser_zone(ville)):
        raise ValidationError("Cette offre n'est plus disponible pour cette livraison. Choisissez un nouveau devis.")
    return item


def creer_devis(tarif_id, user, mode, ville):
    item = _offre(tarif_id, mode, ville)
    return signing.dumps({"tarif": item.pk, "user": user.pk, "mode": mode,
        "ville": normaliser_zone(ville), "montant": str(item.montant)}, salt="delivery-price-v1")


def verifier_devis(token, user, mode, ville, lock=False):
    try:
        payload = signing.loads(token, salt="delivery-price-v1", max_age=1800)
        if payload["user"] != user.pk or payload["mode"] != mode or payload["ville"] != normaliser_zone(ville):
            raise ValueError()
        item = _offre(payload["tarif"], mode, ville, lock=lock)
        if Decimal(payload["montant"]) != item.montant:
            raise ValueError()
        return item, item.montant
    except (signing.BadSignature, ValueError, KeyError, TypeError, InvalidOperation):
        raise ValidationError("Devis invalide ou expiré. Faites recalculer les frais avant de confirmer.")
