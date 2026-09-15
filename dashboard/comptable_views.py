from django.utils.translation import gettext
import csv
from decimal import Decimal
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.shortcuts import render
from django.core.paginator import Paginator
from django.db.models import Sum, Count, Q
from django.db.models.functions import Coalesce, TruncDate, TruncMonth
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.cache import never_cache
from datetime import date, timedelta
import json

from accounts.decorators import comptable_required
from .models import Vente, Depense, BoutiqueSettings
from orders.models import Order
from payments.models import Payment
from products.models import Product


def _paid_payments_in_period(payments, start=None, end=None):
    """Filter paid payments by settlement date, with legacy-date fallback."""
    filters = Q(date_paiement__isnull=False)
    if start is not None:
        filters &= Q(date_paiement__date__gte=start)
    if end is not None:
        filters &= Q(date_paiement__date__lte=end)

    legacy_filters = Q(date_paiement__isnull=True)
    if start is not None:
        legacy_filters &= Q(date_creation__date__gte=start)
    if end is not None:
        legacy_filters &= Q(date_creation__date__lte=end)

    return payments.filter(filters | legacy_filters)


def _csv_safe(value):
    """Prevent spreadsheet formula execution while preserving CSV usability."""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


@never_cache
@comptable_required
def comptable_dashboard(request):
    """Dashboard financier basé uniquement sur les encaissements réels."""
    aujourd_hui = timezone.localdate()
    debut_7_jours = aujourd_hui - timedelta(days=6)
    debut_mois = aujourd_hui.replace(day=1)
    debut_annee = aujourd_hui.replace(month=1, day=1)
    ventes = Vente.objects.all()
    paiements_payes = Payment.objects.filter(statut="paye")

    def snapshot(start, end=aujourd_hui):
        ventes_periode = ventes.filter(date_vente__date__gte=start, date_vente__date__lte=end)
        paiements_periode = _paid_payments_in_period(paiements_payes, start, end)
        vente_data = ventes_periode.aggregate(total=Sum("montant_total"), nb=Count("id"))
        paiement_data = paiements_periode.aggregate(total=Sum("montant"), nb=Count("id"))
        total = (vente_data["total"] or 0) + (paiement_data["total"] or 0)
        count = (vente_data["nb"] or 0) + (paiement_data["nb"] or 0)
        return {
            "total": total,
            "count": count,
            "ventes": vente_data["total"] or 0,
            "paiements": paiement_data["total"] or 0,
            "nb_ventes": vente_data["nb"] or 0,
            "nb_paiements": paiement_data["nb"] or 0,
        }

    aujourd_hui_data = snapshot(aujourd_hui)
    sept_jours_data = snapshot(debut_7_jours)
    mois_data = snapshot(debut_mois)
    annee_data = snapshot(debut_annee)
    global_data = {
        "ventes": ventes.aggregate(total=Sum("montant_total"))["total"] or 0,
        "paiements": paiements_payes.aggregate(total=Sum("montant"))["total"] or 0,
        "nb_ventes": ventes.count(),
        "nb_paiements": paiements_payes.count(),
    }
    total_global = global_data["ventes"] + global_data["paiements"]
    nb_transactions_total = global_data["nb_ventes"] + global_data["nb_paiements"]

    labels_methodes = dict(Vente._meta.get_field("methode_paiement").choices)
    labels_methodes.update(dict(Payment.METHODES))
    methodes_encaissees = {
        methode: {"label": label, "total": Decimal("0"), "nb": 0}
        for methode, label in labels_methodes.items()
    }
    for item in ventes.values("methode_paiement").annotate(total=Sum("montant_total"), nb=Count("id")):
        data = methodes_encaissees[item["methode_paiement"]]
        data["total"] += item["total"] or 0
        data["nb"] += item["nb"] or 0
    for item in paiements_payes.values("methode").annotate(total=Sum("montant"), nb=Count("id")):
        data = methodes_encaissees[item["methode"]]
        data["total"] += item["total"] or 0
        data["nb"] += item["nb"] or 0
    methodes_encaissees = sorted(methodes_encaissees.values(), key=lambda item: item["total"], reverse=True)

    periodes = {
        "aujourd_hui": ("Aujourd'hui", aujourd_hui),
        "7_jours": ("7 derniers jours", debut_7_jours),
        "mois": ("Ce mois", debut_mois),
        "annee": ("Cette année", debut_annee),
    }
    periode = request.GET.get("periode", "7_jours")
    if periode not in periodes:
        periode = "7_jours"
    periode_label, periode_debut = periodes[periode]
    periode_mensuelle = periode == "annee"
    bucket_expression = TruncMonth if periode_mensuelle else TruncDate
    ventes_periode = ventes.filter(date_vente__date__gte=periode_debut, date_vente__date__lte=aujourd_hui)
    paiements_periode = _paid_payments_in_period(paiements_payes, periode_debut, aujourd_hui)
    ventes_groupes = ventes_periode.annotate(bucket=bucket_expression("date_vente")).values("bucket").annotate(total=Sum("montant_total"))
    paiement_date = Coalesce("date_paiement", "date_creation")
    paiements_groupes = paiements_periode.annotate(bucket=bucket_expression(paiement_date)).values("bucket").annotate(total=Sum("montant"))

    def bucket_key(value):
        value = value.date() if hasattr(value, "date") else value
        return value.replace(day=1) if periode_mensuelle else value

    totaux_par_bucket = {}
    for item in list(ventes_groupes) + list(paiements_groupes):
        key = bucket_key(item["bucket"])
        totaux_par_bucket[key] = totaux_par_bucket.get(key, 0) + float(item["total"] or 0)
    chart_buckets = []
    cursor = periode_debut.replace(day=1) if periode_mensuelle else periode_debut
    limite = aujourd_hui.replace(day=1) if periode_mensuelle else aujourd_hui
    while cursor <= limite:
        chart_buckets.append(cursor)
        cursor = date(cursor.year + 1, 1, 1) if periode_mensuelle and cursor.month == 12 else (date(cursor.year, cursor.month + 1, 1) if periode_mensuelle else cursor + timedelta(days=1))
    graphique_labels = [bucket.strftime("%m/%Y") if periode_mensuelle else bucket.strftime("%d/%m") for bucket in chart_buckets]
    graphique_totaux = [totaux_par_bucket.get(bucket, 0) for bucket in chart_buckets]
    methodes_graphique = {label: 0 for label in labels_methodes.values()}
    for item in ventes_periode.values("methode_paiement").annotate(total=Sum("montant_total")):
        methodes_graphique[labels_methodes[item["methode_paiement"]]] += float(item["total"] or 0)
    for item in paiements_periode.values("methode").annotate(total=Sum("montant")):
        methodes_graphique[labels_methodes[item["methode"]]] += float(item["total"] or 0)
    methodes_graphique = sorted(((label, total) for label, total in methodes_graphique.items() if total), key=lambda item: item[1], reverse=True)

    depenses = Depense.indicateurs(aujourd_hui)
    depenses_par_categorie = Depense.objects.filter(
        statut="validee", date_depense__range=(periode_debut, aujourd_hui),
    ).values("categorie__nom").annotate(total=Sum("montant")).order_by("-total", "categorie__nom")
    context = {
        **depenses,
        "resultat_jour": aujourd_hui_data["total"] - depenses["depenses_jour"],
        "resultat_mois": mois_data["total"] - depenses["depenses_mois"],
        "depenses_par_categorie": depenses_par_categorie,
        "boutique": BoutiqueSettings.get_solo(),
        "total_jour": aujourd_hui_data["total"],
        "total_semaine": sept_jours_data["total"],
        "total_mois": mois_data["total"],
        "total_annee": annee_data["total"],
        "total_global": total_global,
        "nb_transactions_jour": aujourd_hui_data["count"],
        "nb_transactions_mois": mois_data["count"],
        "nb_transactions_total": nb_transactions_total,
        "nb_transactions_encaissees": nb_transactions_total,
        "montant_moyen_encaisse": total_global / nb_transactions_total if nb_transactions_total else 0,
        "rev_ventes_jour": aujourd_hui_data["ventes"],
        "rev_ventes_semaine": sept_jours_data["ventes"],
        "rev_ventes_mois": mois_data["ventes"],
        "rev_ventes_total": global_data["ventes"],
        "nb_ventes_total": global_data["nb_ventes"],
        "rev_paiements_jour": aujourd_hui_data["paiements"],
        "rev_paiements_semaine": sept_jours_data["paiements"],
        "rev_paiements_mois": mois_data["paiements"],
        "rev_paiements_total": global_data["paiements"],
        "nb_paiements_total": global_data["nb_paiements"],
        "methodes_encaissees": methodes_encaissees,
        "methodes_graphique_labels_json": json.dumps([str(item[0]) for item in methodes_graphique]),
        "methodes_graphique_totaux_json": json.dumps([item[1] for item in methodes_graphique]),
        "graphique_labels_json": json.dumps(graphique_labels),
        "graphique_totaux_json": json.dumps(graphique_totaux),
        "graphique_has_data": any(graphique_totaux),
        "methodes_graphique_has_data": any(item[1] for item in methodes_graphique),
        "periode": periode,
        "periode_label": periode_label,
        "dernieres_ventes": ventes.select_related("vendeur", "produit").order_by("-date_vente", "-id")[:8],
        "derniers_paiements": paiements_payes.select_related("commande__utilisateur", "commande__vendeur_confirmateur").order_by("-date_paiement", "-id")[:8],
        "commandes_impayees": Order.objects.filter(statut__in=["en_attente", "confirmee"]).exclude(payment__statut="paye").count(),
        "paiements_attente": Payment.objects.filter(statut="en_attente").count(),
        "paiements_echoues": Payment.objects.filter(statut="echoue").count(),
        "paiements_recus": Payment.objects.filter(statut="paye").count(),
        "top_produits": Product.objects.filter(quantite_vendue__gt=0).order_by("-quantite_vendue")[:8],
        "aujourd_hui": aujourd_hui,
    }
    return render(request, "dashboard/comptable_dashboard.html", context)


def _transaction_rows(request):
    """Construit le registre sans mélanger encaissement et contrôle."""
    recherche = request.GET.get("q", "").strip().lower()
    date_debut = request.GET.get("date_debut", "")
    date_fin = request.GET.get("date_fin", "")
    methode = request.GET.get("methode", "")
    statut = request.GET.get("statut", "")
    source = request.GET.get("source", "")
    vendeur = request.GET.get("vendeur", "")
    debut = parse_date(date_debut) if date_debut else None
    fin = parse_date(date_fin) if date_fin else None
    rows = []

    ventes = Vente.objects.select_related("vendeur", "produit__categorie").all()
    paiements = Payment.objects.select_related(
        "commande__utilisateur", "commande__vendeur_confirmateur"
    ).all()
    if vendeur.isdigit():
        ventes = ventes.filter(vendeur_id=int(vendeur))
        paiements = paiements.filter(commande__vendeur_confirmateur_id=int(vendeur))
    if methode:
        ventes = ventes.filter(methode_paiement=methode)
        paiements = paiements.filter(methode=methode)
    if statut:
        if statut == "paye":
            ventes = ventes
        else:
            ventes = ventes.none()
        paiements = paiements.filter(statut=statut)
    if source == "en_ligne":
        ventes = ventes.none()
    elif source == "directe":
        paiements = paiements.none()

    for vente in ventes:
        rows.append({
            "id": f"V-{vente.id}", "date": vente.date_vente, "date_creation": vente.date_vente,
            "date_encaissement": vente.date_vente, "reference": f"V-{vente.id}",
            "source": "directe", "source_label": "Vente directe", "statut": "paye",
            "statut_label": "Encaissé", "methode": vente.methode_paiement,
            "methode_label": vente.get_methode_paiement_display(), "montant": vente.montant_total,
            "vendeur": vente.vendeur.get_full_name() or vente.vendeur.username,
            "vendeur_id": vente.vendeur_id, "client": vente.reference_client or "Client comptoir",
            "produit": vente.produit.nom, "categorie": vente.produit.categorie.nom,
            "quantite": vente.quantite, "prix_unitaire": vente.prix_unitaire,
            "commande_id": None, "commande_statut": "",
        })

    for paiement in paiements:
        date_affichage = paiement.date_paiement or paiement.date_creation
        rows.append({
            "id": f"P-{paiement.id}", "date": date_affichage, "date_creation": paiement.date_creation,
            "date_encaissement": paiement.date_paiement if paiement.statut == "paye" else None,
            "reference": paiement.reference or f"P-{paiement.id}", "source": "en_ligne",
            "source_label": "Commande en ligne", "statut": paiement.statut,
            "statut_label": paiement.get_statut_display(), "methode": paiement.methode,
            "methode_label": paiement.get_methode_display(), "montant": paiement.montant,
            "vendeur": (paiement.commande.vendeur_confirmateur.get_full_name() or paiement.commande.vendeur_confirmateur.username)
                if paiement.commande.vendeur_confirmateur else "Non attribué",
            "vendeur_id": paiement.commande.vendeur_confirmateur_id,
            "client": paiement.commande.utilisateur.get_full_name() or paiement.commande.utilisateur.username,
            "produit": f"Commande #{paiement.commande_id}", "categorie": "",
            "quantite": None, "prix_unitaire": None, "commande_id": paiement.commande_id,
            "commande_statut": paiement.commande.get_statut_display(),
        })

    if recherche:
        rows = [row for row in rows if recherche in " ".join(str(row[key]).lower() for key in ("reference", "produit", "vendeur", "client", "commande_id"))]
    if debut:
        rows = [row for row in rows if row["date"].date() >= debut]
    if fin:
        rows = [row for row in rows if row["date"].date() <= fin]
    return sorted(rows, key=lambda row: (row["date"], row["id"]), reverse=True), {
        "recherche": recherche, "date_debut": date_debut, "date_fin": date_fin,
        "methode": methode, "statut": statut, "source": source, "vendeur": vendeur,
    }


@comptable_required
def comptable_transactions(request):
    rows, filtres = _transaction_rows(request)
    page_obj = Paginator(rows, 15).get_page(request.GET.get("page"))
    total_perimetre = sum((row["montant"] for row in rows), Decimal("0"))
    total_encaisse = sum((row["montant"] for row in rows if row["statut"] == "paye"), Decimal("0"))
    return render(request, "dashboard/comptable_transactions_v2.html", {
        "page_obj": page_obj, "total_perimetre": total_perimetre, "total_encaisse": total_encaisse, **filtres,
        "methodes": Payment.METHODES,
        "statuts": Payment.STATUTS,
        "sources": (("directe", "Vente directe"), ("en_ligne", "Commande en ligne")),
        "vendeurs": User.objects.filter(profile__role="vendeur").order_by("first_name", "last_name", "username"),
    })


@comptable_required
def comptable_transaction_detail(request, reference):
    from django.http import Http404
    row = None
    if reference.startswith("V-") and reference[2:].isdigit():
        vente = Vente.objects.select_related("vendeur", "produit__categorie").filter(id=int(reference[2:])).first()
        if vente:
            row = {
                "source": "directe", "source_label": "Vente directe", "reference": reference,
                "date": vente.date_vente, "date_creation": vente.date_vente, "date_encaissement": vente.date_vente,
                "statut": "paye", "statut_label": "Encaissé", "montant": vente.montant_total,
                "methode_label": vente.get_methode_paiement_display(), "vendeur": vente.vendeur.get_full_name() or vente.vendeur.username,
                "client": vente.reference_client or "Client comptoir", "produit": vente.produit.nom,
                "categorie": vente.produit.categorie.nom, "quantite": vente.quantite, "prix_unitaire": vente.prix_unitaire,
                "notes": vente.notes, "commande_id": None,
            }
    if row is None:
        payment_query = Payment.objects.select_related(
            "commande__utilisateur", "commande__vendeur_confirmateur"
        ).prefetch_related("commande__items__produit__categorie")
        paiement = payment_query.filter(reference=reference).first()
        if paiement is None and reference.startswith("P-") and reference[2:].isdigit():
            paiement = payment_query.filter(id=int(reference[2:])).first()
        if paiement:
            commande = paiement.commande
            row = {
                "source": "en_ligne", "source_label": "Commande en ligne",
                "reference": paiement.reference or f"P-{paiement.id}", "date": paiement.date_paiement or paiement.date_creation,
                "date_creation": paiement.date_creation, "date_encaissement": paiement.date_paiement,
                "statut": paiement.statut, "statut_label": paiement.get_statut_display(), "montant": paiement.montant, "paiement": paiement,
                "methode_label": paiement.get_methode_display(), "vendeur": (commande.vendeur_confirmateur.get_full_name() or commande.vendeur_confirmateur.username) if commande.vendeur_confirmateur else "Non attribué",
                "client": commande.utilisateur.get_full_name() or commande.utilisateur.username, "commande_id": commande.id,
                "commande_statut": commande.get_statut_display(), "commande": commande,
                "sous_total": sum(item.sous_total() for item in commande.items.all()),
                "frais_livraison": commande.frais_livraison, "total_commande": commande.total(), "articles": commande.items.all(),
            }
    if row is None:
        raise Http404(gettext("Transaction introuvable"))
    return render(request, "dashboard/comptable_transaction_detail.html", {"row": row})


@comptable_required
def comptable_export_csv(request):
    rows, _ = _transaction_rows(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="transactions.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(["Date affichée", "Date création", "Date encaissement", "Référence", "Type/source", "Commande", "Client", "Vendeur", "Méthode", "Statut", "Statut commande", "Montant"])
    for row in rows:
        writer.writerow([
            row["date"].strftime("%d/%m/%Y %H:%M"), row["date_creation"].strftime("%d/%m/%Y %H:%M"),
            row["date_encaissement"].strftime("%d/%m/%Y %H:%M") if row["date_encaissement"] else "",
            _csv_safe(row["reference"]), _csv_safe(row["source_label"]), row["commande_id"] or "",
            _csv_safe(row["client"]), _csv_safe(row["vendeur"]), _csv_safe(row["methode_label"]),
            _csv_safe(row["statut_label"]), _csv_safe(row["commande_statut"]), row["montant"],
        ])
    return response


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

    paiements_mois = _paid_payments_in_period(paiements_qs, debut_mois, aujourd_hui)
    ca_mois_paiements = paiements_mois.aggregate(
        total=Sum("montant")
    )["total"] or Decimal("0")

    ca_mois = ca_mois_ventes + ca_mois_paiements

    # Nombre de ventes ce mois
    nb_ventes_mois = ventes_qs.filter(date_vente__date__gte=debut_mois).count()
    nb_paiements_mois = paiements_mois.count()
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
                        {"label": gettext("Montant HT"), "valeur": f"{montant_ht:,.2f} FCFA", "color": "text-primary"},
                        {"label": f"TVA ({taux_tva}%)", "valeur": f"{tva:,.2f} FCFA", "color": "text-warning"},
                        {"label": gettext("Montant TTC"), "valeur": f"{montant_ttc:,.2f} FCFA", "color": "text-success fw-bold fs-5"},
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
                        {"label": gettext("Prix d'achat"), "valeur": f"{prix_achat:,.2f} FCFA", "color": "text-danger"},
                        {"label": gettext("Prix de vente"), "valeur": f"{prix_vente:,.2f} FCFA", "color": "text-primary"},
                        {"label": gettext("Bénéfice brut"), "valeur": f"{benefice:,.2f} FCFA", "color": "text-success"},
                        {"label": gettext("Taux de marge"), "valeur": f"{taux_marge:.2f}%", "color": "text-success fw-bold fs-5"},
                        {"label": gettext("Taux de markup"), "valeur": f"{taux_markup:.2f}%", "color": "text-info"},
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
                        {"label": gettext("Chiffre d'affaires"), "valeur": f"{chiffre_affaires:,.2f} FCFA", "color": "text-primary"},
                        {"label": gettext("Charges fixes"), "valeur": f"-{charges_fixes:,.2f} FCFA", "color": "text-danger"},
                        {"label": gettext("Charges variables"), "valeur": f"-{charges_variables:,.2f} FCFA", "color": "text-danger"},
                        {"label": gettext("TVA collectée"), "valeur": f"{tva_collectee:,.2f} FCFA", "color": "text-warning"},
                        {"label": gettext("Bénéfice brut"), "valeur": f"{benefice_brut:,.2f} FCFA", "color": "text-info"},
                        {"label": gettext("Impôt estimé (25%)"), "valeur": f"-{impot:,.2f} FCFA", "color": "text-danger"},
                        {"label": gettext("Bénéfice Net"), "valeur": f"{benefice_net:,.2f} FCFA", "color": f"{'text-success' if benefice_net >= 0 else 'text-danger'} fw-bold fs-5"},
                        {"label": gettext("Taux de rentabilité"), "valeur": f"{rentabilite:.2f}%", "color": "text-info"},
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
                        {"label": gettext("Charges fixes"), "valeur": f"{charges_fixes2:,.2f} FCFA", "color": "text-danger"},
                        {"label": gettext("Taux de marge"), "valeur": f"{taux_marge2:.2f}%", "color": "text-info"},
                        {"label": gettext("Seuil de rentabilité"), "valeur": f"{seuil:,.2f} FCFA", "color": "text-warning fw-bold fs-5"},
                        {"label": gettext("CA du mois"), "valeur": f"{float(ca_mois):,.2f} FCFA", "color": "text-primary"},
                        {"label": gettext("Marge de sécurité"), "valeur": f"{marge_securite:,.2f} FCFA", "color": f"{'text-success' if marge_securite >= 0 else 'text-danger'} fw-bold"},
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
                        {"label": gettext("CA de départ"), "valeur": f"{ca_actuel:,.2f} FCFA", "color": "text-primary"},
                        {"label": gettext("Taux de croissance"), "valeur": f"{taux_croissance:.1f}% / période", "color": "text-info"},
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

