from django.shortcuts import render
from django.db.models import Count, Sum

from accounts.decorators import comptable_required
from .models import Vente
from .services import revenue_periods
from orders.models import Order
from payments.models import Payment


@comptable_required
def comptable_dashboard(request):
    """Dashboard principal du comptable — gestion des revenus."""

    ventes_qs = Vente.objects.all()
    paiements_qs = Payment.objects.filter(statut="paye")
    revenus = revenue_periods(ventes_qs, paiements_qs)
    aujourd_hui = revenus["today"]

    # ====================
    # REVENUS PAR MÉTHODE DE PAIEMENT (ventes directes)
    # ====================
    par_methode = ventes_qs.values("methode_paiement").annotate(
        total=Sum("montant_total"),
        nb=Count("id")
    ).order_by("-total")

    # ====================
    # REVENUS PAR VENDEUR (top 10)
    # ====================
    top_vendeurs = ventes_qs.values(
        "vendeur__username", "vendeur__first_name", "vendeur__last_name"
    ).annotate(
        total=Sum("montant_total"),
        nb=Count("id")
    ).order_by("-total")[:10]

    # ====================
    # DERNIÈRES TRANSACTIONS
    # ====================
    dernieres_ventes = ventes_qs.select_related("vendeur", "produit")[:15]
    derniers_paiements = paiements_qs.select_related("commande__utilisateur").order_by("-date_creation")[:10]

    # ====================
    # COMMANDES NON PAYÉES (en attente de paiement)
    # ====================
    commandes_impayees = Order.objects.filter(
        statut__in=["en_attente", "confirmee"]
    ).exclude(
        payment__statut="paye"
    ).count()

    context = {
        # Totaux combinés
        "total_jour": revenus["total_jour"],
        "total_mois": revenus["total_mois"],
        "total_annee": revenus["total_annee"],
        "total_global": revenus["total_global"],
        "nb_transactions_jour": revenus["nb_transactions_jour"],
        "nb_transactions_mois": revenus["nb_transactions_mois"],
        "nb_transactions_total": revenus["nb_transactions_total"],

        # Ventes directes
        "rev_ventes_jour": revenus["ventes_day"]["total"] or 0,
        "rev_ventes_mois": revenus["ventes_month"]["total"] or 0,
        "rev_ventes_total": revenus["ventes_total"]["total"] or 0,
        "nb_ventes_total": revenus["ventes_total"]["nb"] or 0,

        # Paiements en ligne
        "rev_paiements_jour": revenus["paiements_day"]["total"] or 0,
        "rev_paiements_mois": revenus["paiements_month"]["total"] or 0,
        "rev_paiements_total": revenus["paiements_total"]["total"] or 0,
        "nb_paiements_total": revenus["paiements_total"]["nb"] or 0,
        "par_methode": list(par_methode),
        "top_vendeurs": top_vendeurs,

        # Transactions récentes
        "dernieres_ventes": dernieres_ventes,
        "derniers_paiements": derniers_paiements,

        # Alertes
        "commandes_impayees": commandes_impayees,

        "aujourd_hui": aujourd_hui,
    }

    return render(request, "dashboard/comptable_dashboard.html", context)
