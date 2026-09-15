from django.utils.translation import gettext
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import connection, models
from django.db.models import Q, Sum, Count, F
from django.utils import timezone

from .models import CompteFinancier, MouvementFinancier, ClotureFinanciere, log_activity
from .finance_services import atomic_finance


def fin_exclusive(day):
    # Local midnight of the next day handles DST and fractional seconds correctly.
    return timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min))


def mouvements_a_date(compte, day):
    return MouvementFinancier.objects.filter(compte=compte, date_mouvement__lt=fin_exclusive(day))


def snapshot_a_date(compte, day):
    totals = mouvements_a_date(compte, day).aggregate(
        total_entrees=Sum("montant", filter=Q(sens="entree"), default=Decimal("0")),
        total_sorties=Sum("montant", filter=Q(sens="sortie"), default=Decimal("0")),
        nombre_mouvements=Count("pk"),
    )
    # SQLite SUM can return a Decimal with binary-aggregation residue. Quantize
    # at the ledger's cent precision, without ever converting money to float.
    for field in ("total_entrees", "total_sorties"):
        totals[field] = totals[field].quantize(Decimal("0.01"))
    return {**totals, "solde_initial_snapshot": compte.solde_initial, "devise": compte.devise,
            "solde_theorique": compte.solde_initial + totals["total_entrees"] - totals["total_sorties"]}


def solde_theorique_a_date(compte, date_cloture):
    return snapshot_a_date(compte, date_cloture)["solde_theorique"]


def cloture_a_mouvements_posterieurs(cloture):
    if not cloture.date_validation:
        return False
    if mouvements_a_date(cloture.compte, cloture.date_cloture).filter(created_at__gt=cloture.date_validation).exists():
        return True
    # Also detect assignment of an older unassigned movement, or opening changes.
    current = snapshot_a_date(cloture.compte, cloture.date_cloture)
    return any(current[field] != getattr(cloture, field) for field in (
        "total_entrees", "total_sorties", "nombre_mouvements", "solde_initial_snapshot", "devise"))


@atomic_finance
def transition_cloture(cloture_id, target, actor, request=None):
    if target not in ("validee", "annulee"):
        raise ValidationError(gettext("Transition inconnue."))
    raw = models.QuerySet(model=ClotureFinanciere, using=connection.alias)
    # First SQL write serializes SQLite; row locks cover databases with FOR UPDATE.
    raw.filter(pk=cloture_id).update(updated_at=F("updated_at"))
    closure = ClotureFinanciere.objects.select_for_update().get(pk=cloture_id)
    if closure.statut == target:
        return closure
    expected = "brouillon" if target == "validee" else "validee"
    if closure.statut != expected:
        raise ValidationError(gettext("Cette transition n'est pas autorisée."))
    changes = {"statut": target, "updated_at": timezone.now()}
    if target == "validee":
        account = CompteFinancier.objects.select_for_update().get(pk=closure.compte_id)
        closure.clean()
        if ClotureFinanciere.objects.filter(compte=account, date_cloture=closure.date_cloture, statut="validee").exclude(pk=closure.pk).exists():
            raise ValidationError(gettext("Une clôture validée existe déjà pour ce compte et cette date."))
        changes.update(snapshot_a_date(account, closure.date_cloture))
        changes["ecart"] = closure.solde_constate - changes["solde_theorique"]
        if changes["ecart"] != 0 and not closure.commentaire.strip():
            raise ValidationError(gettext("Justifiez l'écart dans le commentaire avant de valider."))
        changes.update(validee_par=actor, date_validation=timezone.now())
    raw.filter(pk=closure.pk, statut=expected).update(**changes)
    closure.refresh_from_db()
    verb = "validée" if target == "validee" else "annulée"
    log_activity(actor, "autre", f"Clôture {closure.reference} {verb} : {closure.compte.nom}, écart {closure.ecart} {closure.devise}.", request, "info" if target == "validee" else "warning")
    return closure


def indicateurs_clotures():
    today = timezone.localdate()
    active = ClotureFinanciere.objects.filter(statut="validee")
    today_closed = active.filter(date_cloture=today)
    totals = active.values("devise").annotate(
        positifs=Sum("ecart", filter=Q(ecart__gt=0), default=Decimal("0")),
        negatifs=Sum("ecart", filter=Q(ecart__lt=0), default=Decimal("0")),
        ecart_jour=Sum("ecart", filter=Q(date_cloture=today), default=Decimal("0")),
    ).order_by("devise")
    return {
        "clotures_aujourdhui": ClotureFinanciere.objects.filter(date_cloture=today).exclude(statut="annulee").count(),
        "clotures_validees": active.count(),
        "clotures_avec_ecart": active.exclude(ecart=0).count(),
        "clotures_avec_ecart_jour": today_closed.exclude(ecart=0).count(),
        "ecarts_par_devise": totals,
        "comptes_non_clotures": CompteFinancier.objects.filter(actif=True).exclude(pk__in=today_closed.values("compte_id")),
    }
