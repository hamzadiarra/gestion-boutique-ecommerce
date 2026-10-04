from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from orders.services import BusinessRuleError
from payments.models import Payment
from .models import Vente


@transaction.atomic
def create_direct_sale(vendeur, produit, quantite, methode_paiement, reference_client="", notes=""):
    if quantite <= 0:
        raise BusinessRuleError("La quantité doit être un nombre positif.")

    methodes_valides = {code for code, _label in Vente._meta.get_field("methode_paiement").choices}
    if methode_paiement not in methodes_valides:
        raise BusinessRuleError("Méthode de paiement invalide.")

    if quantite > produit.stock:
        raise BusinessRuleError(
            f"Stock insuffisant pour « {produit.nom} » - disponible : {produit.stock}, demandé : {quantite}."
        )

    prix_unitaire = produit.prix_effectif
    montant_total = prix_unitaire * quantite

    vente = Vente.objects.create(
        vendeur=vendeur,
        produit=produit,
        quantite=quantite,
        prix_unitaire=prix_unitaire,
        montant_total=montant_total,
        methode_paiement=methode_paiement,
        reference_client=reference_client or None,
        notes=notes or None,
    )

    produit.stock -= quantite
    produit.quantite_vendue += quantite
    produit.save(update_fields=["stock", "quantite_vendue"])
    return vente


def seller_stats(vendeur):
    today = timezone.now().date()
    start_month = today.replace(day=1)
    sales = Vente.objects.filter(vendeur=vendeur)

    day_sales = sales.filter(date_vente__date=today)
    month_sales = sales.filter(date_vente__date__gte=start_month)

    return {
        "total_ventes_jour": day_sales.aggregate(total=Sum("montant_total"))["total"] or 0,
        "total_ventes_mois": month_sales.aggregate(total=Sum("montant_total"))["total"] or 0,
        "total_ventes_global": sales.aggregate(total=Sum("montant_total"))["total"] or 0,
        "nb_ventes_jour": day_sales.count(),
        "nb_ventes_mois": month_sales.count(),
        "nb_ventes_total": sales.count(),
    }


def revenue_periods(ventes_qs=None, paiements_qs=None):
    today = timezone.now().date()
    start_month = today.replace(day=1)
    start_year = today.replace(month=1, day=1)
    ventes_qs = ventes_qs or Vente.objects.all()
    paiements_qs = paiements_qs or Payment.objects.filter(statut="paye")

    def aggregate(qs, field):
        return qs.aggregate(total=Sum(field), nb=Count("id"))

    ventes_day = aggregate(ventes_qs.filter(date_vente__date=today), "montant_total")
    ventes_month = aggregate(ventes_qs.filter(date_vente__date__gte=start_month), "montant_total")
    ventes_year = aggregate(ventes_qs.filter(date_vente__date__gte=start_year), "montant_total")
    ventes_total = aggregate(ventes_qs, "montant_total")

    paiements_day = aggregate(paiements_qs.filter(date_creation__date=today), "montant")
    paiements_month = aggregate(paiements_qs.filter(date_creation__date__gte=start_month), "montant")
    paiements_year = aggregate(paiements_qs.filter(date_creation__date__gte=start_year), "montant")
    paiements_total = aggregate(paiements_qs, "montant")

    def money(value):
        return value or 0

    return {
        "today": today,
        "ventes_day": ventes_day,
        "ventes_month": ventes_month,
        "ventes_year": ventes_year,
        "ventes_total": ventes_total,
        "paiements_day": paiements_day,
        "paiements_month": paiements_month,
        "paiements_year": paiements_year,
        "paiements_total": paiements_total,
        "total_jour": money(ventes_day["total"]) + money(paiements_day["total"]),
        "total_mois": money(ventes_month["total"]) + money(paiements_month["total"]),
        "total_annee": money(ventes_year["total"]) + money(paiements_year["total"]),
        "total_global": money(ventes_total["total"]) + money(paiements_total["total"]),
        "nb_transactions_jour": (ventes_day["nb"] or 0) + (paiements_day["nb"] or 0),
        "nb_transactions_mois": (ventes_month["nb"] or 0) + (paiements_month["nb"] or 0),
        "nb_transactions_total": (ventes_total["nb"] or 0) + (paiements_total["nb"] or 0),
    }
