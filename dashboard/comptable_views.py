from django.shortcuts import render
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta
import json

from accounts.decorators import comptable_required
from .models import Vente
from orders.models import Order
from payments.models import Payment


@comptable_required
def comptable_dashboard(request):
    """Dashboard principal du comptable — gestion des revenus."""

    aujourd_hui = timezone.now().date()
    debut_mois = aujourd_hui.replace(day=1)
    debut_annee = aujourd_hui.replace(month=1, day=1)
    hier = aujourd_hui - timedelta(days=1)

    # ====================
    # REVENUS VENTES DIRECTES (Vendeurs)
    # ====================
    ventes_qs = Vente.objects.all()

    rev_ventes_jour = ventes_qs.filter(date_vente__date=aujourd_hui).aggregate(
        total=Sum("montant_total"), nb=Count("id")
    )
    rev_ventes_mois = ventes_qs.filter(date_vente__date__gte=debut_mois).aggregate(
        total=Sum("montant_total"), nb=Count("id")
    )
    rev_ventes_annee = ventes_qs.filter(date_vente__date__gte=debut_annee).aggregate(
        total=Sum("montant_total"), nb=Count("id")
    )
    rev_ventes_total = ventes_qs.aggregate(
        total=Sum("montant_total"), nb=Count("id")
    )

    # ====================
    # REVENUS COMMANDES EN LIGNE (Paiements)
    # ====================
    paiements_qs = Payment.objects.filter(statut="paye")

    rev_paiements_jour = paiements_qs.filter(date_creation__date=aujourd_hui).aggregate(
        total=Sum("montant"), nb=Count("id")
    )
    rev_paiements_mois = paiements_qs.filter(date_creation__date__gte=debut_mois).aggregate(
        total=Sum("montant"), nb=Count("id")
    )
    rev_paiements_annee = paiements_qs.filter(date_creation__date__gte=debut_annee).aggregate(
        total=Sum("montant"), nb=Count("id")
    )
    rev_paiements_total = paiements_qs.aggregate(
        total=Sum("montant"), nb=Count("id")
    )

    # ====================
    # TOTAUX COMBINÉS
    # ====================
    def combine(v, p):
        return (v or 0) + (p or 0)

    total_jour = combine(rev_ventes_jour["total"], rev_paiements_jour["total"])
    total_mois = combine(rev_ventes_mois["total"], rev_paiements_mois["total"])
    total_annee = combine(rev_ventes_annee["total"], rev_paiements_annee["total"])
    total_global = combine(rev_ventes_total["total"], rev_paiements_total["total"])

    nb_transactions_jour = (rev_ventes_jour["nb"] or 0) + (rev_paiements_jour["nb"] or 0)
    nb_transactions_mois = (rev_ventes_mois["nb"] or 0) + (rev_paiements_mois["nb"] or 0)
    nb_transactions_total = (rev_ventes_total["nb"] or 0) + (rev_paiements_total["nb"] or 0)

    # ====================
    # REVENUS PAR MÉTHODE DE PAIEMENT (ventes directes)
    # ====================
    par_methode = ventes_qs.values("methode_paiement").annotate(
        total=Sum("montant_total"),
        nb=Count("id")
    ).order_by("-total")

    methodes_labels = []
    methodes_totaux = []
    for m in par_methode:
        labels_map = {
            "especes": "Espèces",
            "orange_money": "Orange Money",
            "wave": "Wave",
            "carte": "Carte bancaire",
        }
        methodes_labels.append(labels_map.get(m["methode_paiement"], m["methode_paiement"]))
        methodes_totaux.append(float(m["total"] or 0))

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
    # REVENUS DES 7 DERNIERS JOURS (graphique)
    # ====================
    jours_labels = []
    jours_ventes = []
    jours_paiements = []

    for i in range(6, -1, -1):
        jour = aujourd_hui - timedelta(days=i)
        jours_labels.append(jour.strftime("%d/%m"))

        v = ventes_qs.filter(date_vente__date=jour).aggregate(
            total=Sum("montant_total")
        )["total"] or 0

        p = paiements_qs.filter(date_creation__date=jour).aggregate(
            total=Sum("montant")
        )["total"] or 0

        jours_ventes.append(float(v))
        jours_paiements.append(float(p))

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
        "total_jour": total_jour,
        "total_mois": total_mois,
        "total_annee": total_annee,
        "total_global": total_global,
        "nb_transactions_jour": nb_transactions_jour,
        "nb_transactions_mois": nb_transactions_mois,
        "nb_transactions_total": nb_transactions_total,

        # Ventes directes
        "rev_ventes_jour": rev_ventes_jour["total"] or 0,
        "rev_ventes_mois": rev_ventes_mois["total"] or 0,
        "rev_ventes_total": rev_ventes_total["total"] or 0,
        "nb_ventes_total": rev_ventes_total["nb"] or 0,

        # Paiements en ligne
        "rev_paiements_jour": rev_paiements_jour["total"] or 0,
        "rev_paiements_mois": rev_paiements_mois["total"] or 0,
        "rev_paiements_total": rev_paiements_total["total"] or 0,
        "nb_paiements_total": rev_paiements_total["nb"] or 0,
        # Graphiques
        "par_methode": list(par_methode),
        "methodes_labels": methodes_labels,
        "methodes_totaux": methodes_totaux,
        "top_vendeurs": top_vendeurs,
        "jours_labels": jours_labels,
        "jours_ventes": jours_ventes,
        "jours_paiements": jours_paiements,
        "jours_labels_json": json.dumps(jours_labels),
        "jours_ventes_json": json.dumps(jours_ventes),
        "jours_paiements_json": json.dumps(jours_paiements),

        # Transactions récentes
        "dernieres_ventes": dernieres_ventes,
        "derniers_paiements": derniers_paiements,

        # Alertes
        "commandes_impayees": commandes_impayees,

        "aujourd_hui": aujourd_hui,
    }

    return render(request, "dashboard/comptable_dashboard.html", context)


@comptable_required
def comptable_calculs(request):
    """Page de calculs financiers interactifs pour le comptable."""

    aujourd_hui = timezone.now().date()
    debut_mois = aujourd_hui.replace(day=1)

    # Données réelles pour pré-remplir les calculs
    from decimal import Decimal

    ventes_qs = Vente.objects.all()
    paiements_qs = Payment.objects.filter(statut="paye")

    # Chiffres du mois en cours
    ca_mois_ventes = ventes_qs.filter(date_vente__date__gte=debut_mois).aggregate(
        total=Sum("montant_total")
    )["total"] or Decimal("0")

    ca_mois_paiements = paiements_qs.filter(date_creation__date__gte=debut_mois).aggregate(
        total=Sum("montant")
    )["total"] or Decimal("0")

    ca_mois = ca_mois_ventes + ca_mois_paiements

    # Nombre de ventes ce mois
    nb_ventes_mois = ventes_qs.filter(date_vente__date__gte=debut_mois).count()
    nb_paiements_mois = paiements_qs.filter(date_creation__date__gte=debut_mois).count()
    nb_transactions_mois = nb_ventes_mois + nb_paiements_mois

    # Panier moyen
    panier_moyen = float(ca_mois) / nb_transactions_mois if nb_transactions_mois > 0 else 0

    # Résultats de calcul si formulaire soumis
    resultat = None
    type_calcul = None

    def parse_float(val, default=0.0):
        try:
            if val is None or str(val).strip() == "":
                return float(default)
            return float(val)
        except (ValueError, TypeError):
            return float(default)

    if request.method == "POST":
        type_calcul = request.POST.get("type_calcul")

        try:
            if type_calcul == "tva":
                montant_ht = parse_float(request.POST.get("montant_ht"), 0)
                taux_tva = parse_float(request.POST.get("taux_tva"), 18)
                tva = montant_ht * taux_tva / 100
                montant_ttc = montant_ht + tva
                resultat = {
                    "type": "TVA",
                    "emoji": "🧾",
                    "lignes": [
                        {"label": "Montant HT", "valeur": f"{montant_ht:,.2f} FCFA", "color": "text-primary"},
                        {"label": f"TVA ({taux_tva}%)", "valeur": f"{tva:,.2f} FCFA", "color": "text-warning"},
                        {"label": "Montant TTC", "valeur": f"{montant_ttc:,.2f} FCFA", "color": "text-success fw-bold fs-5"},
                    ]
                }

            elif type_calcul == "marge":
                prix_achat = parse_float(request.POST.get("prix_achat"), 0)
                prix_vente = parse_float(request.POST.get("prix_vente"), 0)
                benefice = prix_vente - prix_achat
                taux_marge = (benefice / prix_vente * 100) if prix_vente > 0 else 0
                taux_markup = (benefice / prix_achat * 100) if prix_achat > 0 else 0
                resultat = {
                    "type": "Marge Bénéficiaire",
                    "emoji": "📊",
                    "lignes": [
                        {"label": "Prix d'achat", "valeur": f"{prix_achat:,.2f} FCFA", "color": "text-danger"},
                        {"label": "Prix de vente", "valeur": f"{prix_vente:,.2f} FCFA", "color": "text-primary"},
                        {"label": "Bénéfice brut", "valeur": f"{benefice:,.2f} FCFA", "color": "text-success"},
                        {"label": "Taux de marge", "valeur": f"{taux_marge:.2f}%", "color": "text-success fw-bold fs-5"},
                        {"label": "Taux de markup", "valeur": f"{taux_markup:.2f}%", "color": "text-info"},
                    ]
                }

            elif type_calcul == "benefice_net":
                chiffre_affaires = parse_float(request.POST.get("chiffre_affaires"), float(ca_mois))
                charges_fixes = parse_float(request.POST.get("charges_fixes"), 0)
                charges_variables = parse_float(request.POST.get("charges_variables"), 0)
                taux_tva2 = parse_float(request.POST.get("taux_tva2"), 18)
                total_charges = charges_fixes + charges_variables
                tva_collectee = chiffre_affaires * taux_tva2 / 100
                benefice_brut = chiffre_affaires - total_charges
                impot = max(0, benefice_brut * 0.25)  # 25% impôt estimé
                benefice_net = benefice_brut - impot
                rentabilite = (benefice_net / chiffre_affaires * 100) if chiffre_affaires > 0 else 0
                resultat = {
                    "type": "Bénéfice Net",
                    "emoji": "💰",
                    "lignes": [
                        {"label": "Chiffre d'affaires", "valeur": f"{chiffre_affaires:,.2f} FCFA", "color": "text-primary"},
                        {"label": "Charges fixes", "valeur": f"-{charges_fixes:,.2f} FCFA", "color": "text-danger"},
                        {"label": "Charges variables", "valeur": f"-{charges_variables:,.2f} FCFA", "color": "text-danger"},
                        {"label": "TVA collectée", "valeur": f"{tva_collectee:,.2f} FCFA", "color": "text-warning"},
                        {"label": "Bénéfice brut", "valeur": f"{benefice_brut:,.2f} FCFA", "color": "text-info"},
                        {"label": "Impôt estimé (25%)", "valeur": f"-{impot:,.2f} FCFA", "color": "text-danger"},
                        {"label": "Bénéfice Net", "valeur": f"{benefice_net:,.2f} FCFA", "color": f"{'text-success' if benefice_net >= 0 else 'text-danger'} fw-bold fs-5"},
                        {"label": "Taux de rentabilité", "valeur": f"{rentabilite:.2f}%", "color": "text-info"},
                    ]
                }

            elif type_calcul == "seuil":
                charges_fixes2 = parse_float(request.POST.get("charges_fixes2"), 0)
                taux_marge2 = parse_float(request.POST.get("taux_marge2"), 0)
                seuil = (charges_fixes2 / (taux_marge2 / 100)) if taux_marge2 > 0 else 0
                marge_securite = float(ca_mois) - seuil
                resultat = {
                    "type": "Seuil de Rentabilité",
                    "emoji": "🎯",
                    "lignes": [
                        {"label": "Charges fixes", "valeur": f"{charges_fixes2:,.2f} FCFA", "color": "text-danger"},
                        {"label": "Taux de marge", "valeur": f"{taux_marge2:.2f}%", "color": "text-info"},
                        {"label": "Seuil de rentabilité", "valeur": f"{seuil:,.2f} FCFA", "color": "text-warning fw-bold fs-5"},
                        {"label": "CA du mois", "valeur": f"{float(ca_mois):,.2f} FCFA", "color": "text-primary"},
                        {"label": "Marge de sécurité", "valeur": f"{marge_securite:,.2f} FCFA", "color": f"{'text-success' if marge_securite >= 0 else 'text-danger'} fw-bold"},
                    ]
                }

            elif type_calcul == "projection":
                ca_actuel = parse_float(request.POST.get("ca_actuel"), float(ca_mois))
                taux_croissance = parse_float(request.POST.get("taux_croissance"), 0)
                try:
                    nb_periodes = int(request.POST.get("nb_periodes", 12))
                except (ValueError, TypeError):
                    nb_periodes = 12
                projections = []
                val = ca_actuel
                for i in range(1, min(nb_periodes + 1, 13)):
                    val = val * (1 + taux_croissance / 100)
                    projections.append({"periode": i, "valeur": round(val, 2)})
                total_projete = sum(p["valeur"] for p in projections)
                max_proj = max((p["valeur"] for p in projections), default=1)
                resultat = {
                    "type": "Projection de Revenus",
                    "emoji": "📈",
                    "lignes": [
                        {"label": "CA de départ", "valeur": f"{ca_actuel:,.2f} FCFA", "color": "text-primary"},
                        {"label": "Taux de croissance", "valeur": f"{taux_croissance:.1f}% / période", "color": "text-info"},
                        {"label": f"Total projeté sur {nb_periodes} périodes", "valeur": f"{total_projete:,.2f} FCFA", "color": "text-success fw-bold fs-5"},
                    ],
                    "projections": projections,
                    "max_projection": max_proj,
                    "taux_croissance": taux_croissance,
                }

        except Exception as e:
            resultat = {"erreur": f"Erreur de calcul : {str(e)}"}

    context = {
        "aujourd_hui": aujourd_hui,
        "ca_mois": ca_mois,
        "nb_transactions_mois": nb_transactions_mois,
        "panier_moyen": panier_moyen,
        "resultat": resultat,
        "type_calcul": type_calcul,
        "taux_tva_defaut": 18,
    }
    return render(request, "dashboard/comptable_calculs.html", context)

