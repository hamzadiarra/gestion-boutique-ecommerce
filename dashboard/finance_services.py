from django.utils.translation import gettext
"""Explicit, atomic financial workflows; no historical import on startup."""
import time
import uuid
from datetime import datetime, time as daytime
from decimal import Decimal
from functools import wraps

from django.core.exceptions import ValidationError
from django.db import OperationalError, connection, models, transaction
from django.db.models import Sum
from django.utils import timezone

from .models import BoutiqueSettings, CompteFinancier, MouvementFinancier, TransfertFinancier, log_activity


def atomic_finance(function):
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


def _currency():
    value = (BoutiqueSettings.objects.values_list("devise", flat=True).first() or "FCFA").strip().upper()
    return "FCFA" if value == "XOF" else value


def _automatic(source, field, kind, method, amount, when, actor=None, original=None, reason=""):
    # Zero-value legacy/free orders have no cash variation. Never invent a cent.
    amount = Decimal(amount)
    if amount == 0:
        return None
    if not amount.is_finite() or amount < 0:
        raise ValidationError(gettext("Montant financier invalide."))
    existing = MouvementFinancier.objects.filter(**{field: source}, type_mouvement=kind).first()
    if existing:
        return existing
    # Les paiements online et par carte sont réglés sur le compte bancaire.
    expected = {"carte": "banque", "online": "banque"}.get(method, method)
    currency = original.devise if original else _currency()
    if original:
        expected = original.type_compte_attendu
        account = CompteFinancier.objects.select_for_update().filter(pk=original.compte_id, actif=True).first()
    elif kind == "annulation":
        account = None
        reason = "Historique sans sortie financière : reprise historique requise avant affectation."
    else:
        account = CompteFinancier.objects.select_for_update().filter(type_compte=expected, devise=currency, actif=True, est_par_defaut=True).first()
    if reason:
        account = None
    return MouvementFinancier.objects.create(
        **{field: source}, compte=account, type_compte_attendu=expected, devise=currency,
        type_mouvement=kind, sens="sortie" if kind == "depense" else "entree",
        montant=amount, date_mouvement=when, cree_par=actor,
        libelle=f"{kind.capitalize()} {getattr(source, 'reference', None) or source.pk}",
        raison_regularisation="" if account else reason or "Aucun compte actif compatible ; compte par défaut absent ou compte d'origine indisponible.",
    )


@atomic_finance
def enregistrer_vente(vente):
    return _automatic(vente, "vente", "vente", vente.methode_paiement, vente.montant_total, vente.date_vente, vente.vendeur)


@atomic_finance
def enregistrer_paiement(payment):
    if payment.statut != "paye":
        return None
    return _automatic(payment, "paiement", "paiement", payment.methode, payment.montant,
                      payment.date_paiement or payment.date_creation,
                      reason="Date de paiement manquante : correction métier requise avant affectation." if not payment.date_paiement else "")


@atomic_finance
def enregistrer_depense(expense, actor, annulation=False):
    if expense.statut != ("annulee" if annulation else "validee"):
        return None
    original = MouvementFinancier.objects.filter(depense=expense, type_mouvement="depense").first() if annulation else None
    when = timezone.now() if annulation else timezone.make_aware(datetime.combine(expense.date_depense, daytime.min))
    return _automatic(expense, "depense", "annulation" if annulation else "depense", expense.moyen_paiement,
                      original.montant if original else expense.montant, when, actor, original)


@atomic_finance
def transferer(source_id, destination_id, montant, date_transfert, motif, actor, cle_operation=None, request=None):
    key = cle_operation or uuid.uuid4()
    existing = TransfertFinancier.objects.filter(cle_operation=key).first()
    if existing:
        return existing
    accounts = {a.pk: a for a in CompteFinancier.objects.select_for_update().filter(pk__in=[source_id, destination_id]).order_by("pk")}
    if source_id not in accounts or destination_id not in accounts:
        raise ValidationError(gettext("Compte introuvable."))
    source, destination = accounts[source_id], accounts[destination_id]
    transfer = TransfertFinancier.objects.create(compte_source=source, compte_destination=destination,
        montant=montant, date_transfert=date_transfert, motif=motif.strip(), cree_par=actor, cle_operation=key)
    for account, direction in ((source, "sortie"), (destination, "entree")):
        MouvementFinancier.objects.create(compte=account, sens=direction, type_mouvement="transfert",
            montant=montant, date_mouvement=date_transfert, libelle=f"{transfer.reference} : {motif}"[:255],
            transfert=transfer, cree_par=actor, type_compte_attendu=account.type_compte, devise=account.devise)
    log_activity(actor, "autre", f"Transfert {transfer.reference} : {montant} {source.devise}, {source.nom} vers {destination.nom}.", request)
    return transfer


@atomic_finance
def ajuster(compte_id, sens, montant, date_mouvement, motif, actor, cle_operation=None, request=None):
    key = cle_operation or uuid.uuid4()
    existing = MouvementFinancier.objects.filter(cle_operation=key).first()
    if existing:
        return existing
    account = CompteFinancier.objects.select_for_update().get(pk=compte_id)
    if not account.actif or not motif.strip():
        raise ValidationError(gettext("Compte actif et motif obligatoires."))
    movement = MouvementFinancier.objects.create(compte=account, sens=sens, montant=montant,
        type_mouvement="ajustement", date_mouvement=date_mouvement, libelle=motif.strip(), description=motif.strip(),
        cree_par=actor, cle_operation=key, type_compte_attendu=account.type_compte, devise=account.devise)
    log_activity(actor, "autre", f"Ajustement {movement.reference} : {sens} {montant} {account.devise}. Motif : {motif}", request, "warning")
    return movement


@atomic_finance
def regulariser(mouvement_id, compte_id, actor, request=None):
    # First write serializes SQLite regularizations as well as row locks on PostgreSQL.
    raw = models.QuerySet(model=MouvementFinancier, using=connection.alias)
    raw.filter(pk=mouvement_id, compte__isnull=True).update(raison_regularisation=models.F("raison_regularisation"))
    movement = MouvementFinancier.objects.select_for_update().get(pk=mouvement_id)
    if movement.compte_id:
        if movement.compte_id != compte_id:
            raise ValidationError(gettext("Ce mouvement est déjà affecté à un autre compte."))
        return movement
    account = CompteFinancier.objects.select_for_update().get(pk=compte_id)
    if not account.actif or account.type_compte != movement.type_compte_attendu or account.devise != movement.devise:
        raise ValidationError(gettext("Sélectionnez un compte actif de même type et devise."))
    if movement.paiement_id and not movement.paiement.date_paiement:
        raise ValidationError(gettext("Date de paiement absente : correction métier préalable nécessaire."))
    related = [movement]
    if movement.depense_id:
        related = list(MouvementFinancier.objects.select_for_update().filter(depense_id=movement.depense_id).order_by("pk"))
        if movement.type_mouvement == "annulation" and not any(m.type_mouvement == "depense" for m in related):
            raise ValidationError(gettext("Sortie historique absente : utilisez la future reprise historique, pas une entrée isolée."))
        if any(m.compte_id and m.compte_id != account.pk for m in related):
            raise ValidationError(gettext("La contrepassation doit rester sur le compte de la sortie initiale."))
    raw.filter(pk__in=[m.pk for m in related], compte__isnull=True).update(compte=account, raison_regularisation="")
    log_activity(actor, "autre", f"Régularisation {movement.reference} vers {account.nom}. Contrepassation éventuelle affectée au même compte.", request)
    movement.compte = account
    return movement


def liquidites():
    # Aggregate each table separately to avoid multiplying initial balances by joins.
    initial = CompteFinancier.objects.values("devise", "type_compte").annotate(total=Sum("solde_initial")).order_by("devise", "type_compte")
    flows = MouvementFinancier.objects.filter(compte__isnull=False).values("devise", "type_compte_attendu", "sens").annotate(total=Sum("montant")).order_by()
    groups = {(r["devise"], r["type_compte"]): r["total"] for r in initial}
    for row in flows:
        key = (row["devise"], row["type_compte_attendu"])
        groups[key] = groups.get(key, Decimal("0")) + row["total"] * (1 if row["sens"] == "entree" else -1)
    totals = {}
    for (currency, kind), amount in groups.items():
        totals[currency] = totals.get(currency, Decimal("0")) + amount
    return {"liquidites_par_devise": totals, "liquidites_par_type": [
        {"devise": currency, "type": dict(CompteFinancier._meta.get_field("type_compte").choices)[kind], "total": amount}
        for (currency, kind), amount in groups.items()],
        "mouvements_a_regulariser": MouvementFinancier.objects.filter(compte__isnull=True).count()}
