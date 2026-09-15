from django.utils.translation import gettext
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.core.paginator import Paginator
from django.utils import timezone
from django.utils.text import slugify
from django.urls import reverse
from django.utils.dateparse import parse_date
from PIL import Image

from accounts.decorators import vendeur_required
from products.models import Product
from categories.models import Category
from orders.models import Order, OrderItem
from payments.models import Payment
from cart.models import Cart, CartItem
from .models import Vente, BoutiqueSettings, log_activity


MAX_PRODUCT_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_PRODUCT_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _filter_date(value):
    try:
        parsed = parse_date(value)
    except (TypeError, ValueError):
        parsed = None
    return parsed.isoformat() if parsed else ""


def _validate_product_image(uploaded_image):
    """Valide une image vendeur avant de la confier à ImageField."""
    if not uploaded_image:
        return None
    if uploaded_image.size > MAX_PRODUCT_IMAGE_BYTES:
        return "L'image doit peser 5 Mo maximum."
    if getattr(uploaded_image, "content_type", "") not in ALLOWED_PRODUCT_IMAGE_TYPES:
        return "Format non accepté. Utilisez une image JPG, PNG ou WebP."
    try:
        with Image.open(uploaded_image) as image:
            image.verify()
        uploaded_image.seek(0)
    except (OSError, Image.UnidentifiedImageError):
        return "Le fichier envoyé n'est pas une image valide."
    return None


def _product_form_context(request, categories, produit=None, form_errors=None):
    """Conserve la saisie et expose des erreurs directement sous les champs."""
    is_post = request.method == "POST"
    context = {
        "categories": categories,
        "form_data": request.POST if is_post else {},
        "form_errors": form_errors or {},
        "form_categorie": request.POST.get("categorie", "") if is_post else getattr(produit, "categorie_id", ""),
        "form_actif": request.POST.get("actif") == "on" if is_post else getattr(produit, "actif", True),
        "form_vedette": request.POST.get("vedette") == "on" if is_post else getattr(produit, "vedette", False),
    }
    if produit is not None:
        context["produit"] = produit
    return context


@vendeur_required
def vendeur_dashboard(request):
    """Dashboard principal du vendeur avec ses statistiques."""

    aujourd_hui = timezone.now().date()
    debut_mois = aujourd_hui.replace(day=1)

    # Ventes du vendeur
    mes_ventes = Vente.objects.filter(vendeur=request.user)
    ventes_jour = mes_ventes.filter(date_vente__date=aujourd_hui)
    ventes_mois = mes_ventes.filter(date_vente__date__gte=debut_mois)

    # Statistiques
    total_ventes_jour = ventes_jour.aggregate(Sum("montant_total"))["montant_total__sum"] or 0
    total_ventes_mois = ventes_mois.aggregate(Sum("montant_total"))["montant_total__sum"] or 0
    total_ventes_global = mes_ventes.aggregate(Sum("montant_total"))["montant_total__sum"] or 0
    nb_ventes_jour = ventes_jour.count()
    nb_ventes_mois = ventes_mois.count()
    nb_ventes_total = mes_ventes.count()

    # Produits disponibles pour la vente
    produits = Product.objects.filter(actif=True, stock__gt=0).order_by("nom")

    # Dernières ventes
    dernieres_ventes = mes_ventes[:10]

    # Commandes en attente de confirmation (lien vendeur-client)
    commandes_en_attente = Order.objects.filter(
        statut="en_attente"
    ).select_related("utilisateur").prefetch_related("items__produit").order_by("-date_creation")[:5]

    nb_commandes_attente = Order.objects.filter(statut="en_attente").count()
    nb_commandes_confirmees = Order.objects.filter(statut="confirmee").count()
    nb_ruptures = Product.objects.filter(actif=True, stock=0).count()
    nb_stock_faible = Product.objects.filter(actif=True, stock__gt=0, stock__lte=5).count()
    nb_produits_inactifs = Product.objects.filter(actif=False).count()

    derniere_vente_id = request.session.pop("last_sale_id", None)
    derniere_vente = None
    if derniere_vente_id:
        derniere_vente = mes_ventes.filter(id=derniere_vente_id).select_related("produit").first()

    context = {
        "total_ventes_jour": total_ventes_jour,
        "total_ventes_mois": total_ventes_mois,
        "total_ventes_global": total_ventes_global,
        "nb_ventes_jour": nb_ventes_jour,
        "nb_ventes_mois": nb_ventes_mois,
        "nb_ventes_total": nb_ventes_total,
        "produits": produits,
        "methodes_paiement": Vente._meta.get_field("methode_paiement").choices,
        "dernieres_ventes": dernieres_ventes,
        "commandes_en_attente": commandes_en_attente,
        "nb_commandes_attente": nb_commandes_attente,
        "nb_commandes_confirmees": nb_commandes_confirmees,
        "nb_ruptures": nb_ruptures,
        "nb_stock_faible": nb_stock_faible,
        "nb_produits_inactifs": nb_produits_inactifs,
        "derniere_vente": derniere_vente,
    }

    return render(request, "dashboard/vendeur_dashboard.html", context)


@vendeur_required
def enregistrer_vente(request):
    """Enregistrer une nouvelle vente (formulaire POST)."""

    if request.method != "POST":
        return redirect("vendeur_dashboard")

    produit_id = request.POST.get("produit")
    quantite = request.POST.get("quantite", 1)
    methode_paiement = request.POST.get("methode_paiement", "especes")
    reference_client = request.POST.get("reference_client", "").strip()
    notes = request.POST.get("notes", "").strip()

    try:
        produit_id = int(produit_id)
        if not 0 < produit_id <= 9223372036854775807:
            raise ValueError
    except (ValueError, TypeError):
        messages.error(request, gettext("Choisissez un produit valide."))
        return redirect("vendeur_dashboard")
    if methode_paiement not in dict(Vente._meta.get_field("methode_paiement").choices):
        messages.error(request, gettext("Choisissez un moyen de paiement valide."))
        return redirect("vendeur_dashboard")

    try:
        quantite = int(quantite)
        if quantite <= 0:
            raise ValueError
    except (ValueError, TypeError):
        messages.error(request, gettext("La quantité doit être un nombre positif."))
        return redirect("vendeur_dashboard")

    with transaction.atomic():
        produit = get_object_or_404(Product.objects.select_for_update(), id=produit_id, actif=True)

        if quantite > produit.stock:
            messages.error(
                request,
                f"Stock insuffisant pour « {produit.nom} » — disponible : {produit.stock}, demandé : {quantite}."
            )
            return redirect("vendeur_dashboard")

        prix_unitaire = produit.prix_promotion if produit.prix_promotion else produit.prix
        montant_total = prix_unitaire * quantite
        vente = Vente.objects.create(
            vendeur=request.user,
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

    # Logger l'activité
    log_activity(
        user=request.user,
        action="vente_creee",
        details=(
            f"Vente #{vente.id} — {produit.nom} x{quantite} à {prix_unitaire} FCFA/unité. "
            f"Total : {montant_total} FCFA. Paiement : {vente.get_methode_paiement_display()}. "
            f"Client : {reference_client or 'Non spécifié'}. Stock restant : {produit.stock}."
        ),
        request=request,
        niveau="info"
    )

    request.session["last_sale_id"] = vente.id
    messages.success(request, gettext("Vente #{sale_id} enregistrée — {name} x{quantity} = {amount} FCFA").format(sale_id=vente.id, name=produit.nom, quantity=quantite, amount=montant_total))
    return redirect(
        "vendeur_vente_recu",
        vente_id=vente.id,
    )


@vendeur_required
def vendeur_vente_recu(request, vente_id):
    """
    Affiche le reçu d'une vente directe réalisée au comptoir.
    Le vendeur ne peut consulter que ses propres ventes.
    """

    vente = get_object_or_404(
        Vente.objects.select_related(
            "vendeur",
            "produit",
            "produit__categorie",
        ),
        id=vente_id,
        vendeur=request.user,
    )

    numero_recu = f"VTE-{vente.date_vente.year}-{vente.id:06d}"

    vendeur_name = (
        vente.vendeur.get_full_name().strip()
        or vente.vendeur.username
    )

    return render(
        request,
        "dashboard/vendeur_vente_recu.html",
        {
            "vente": vente,
            "numero_recu": numero_recu,
            "vendeur_name": vendeur_name,
            "boutique_settings": BoutiqueSettings.get_solo(),
        },
    )


@vendeur_required
def historique_ventes(request):
    """Historique complet des ventes du vendeur."""

    mes_ventes = Vente.objects.filter(vendeur=request.user).select_related("produit")
    recherche = request.GET.get("q", "").strip()
    date_debut = _filter_date(request.GET.get("date_debut", ""))
    date_fin = _filter_date(request.GET.get("date_fin", ""))
    methode = request.GET.get("methode", "")
    if recherche:
        mes_ventes = mes_ventes.filter(Q(produit__nom__icontains=recherche) | Q(reference_client__icontains=recherche))
    if date_debut:
        mes_ventes = mes_ventes.filter(date_vente__date__gte=date_debut)
    if date_fin:
        mes_ventes = mes_ventes.filter(date_vente__date__lte=date_fin)
    if methode:
        mes_ventes = mes_ventes.filter(methode_paiement=methode)
    total_filtre = mes_ventes.aggregate(total=Sum("montant_total"))["total"] or 0
    page_obj = Paginator(mes_ventes, 12).get_page(request.GET.get("page"))
    pagination_params = request.GET.copy()
    pagination_params.pop("page", None)
    previous_page_url = f"?{pagination_params.urlencode()}&page={page_obj.previous_page_number()}" if page_obj.has_previous() else ""
    next_page_url = f"?{pagination_params.urlencode()}&page={page_obj.next_page_number()}" if page_obj.has_next() else ""

    return render(request, "dashboard/vendeur_historique.html", {
        "ventes": page_obj,
        "page_obj": page_obj,
        "recherche": recherche, "date_debut": date_debut, "date_fin": date_fin,
        "methode": methode, "total_filtre": total_filtre,
        "methodes_paiement": Vente._meta.get_field("methode_paiement").choices,
        "query_params": request.GET.copy(),
        "previous_page_url": previous_page_url, "next_page_url": next_page_url,
    })


# =============================================
# GESTION DES COMMANDES CLIENTS (Vendeur)
# =============================================

@vendeur_required
def vendeur_commandes(request):
    """Liste toutes les commandes clients avec possibilité de confirmation."""

    # Filtre par statut
    statut_filtre = request.GET.get("statut", "en_attente")
    statuts_valides = ["en_attente", "confirmee", "expediee", "livree", "annulee", "toutes"]

    if statut_filtre not in statuts_valides:
        statut_filtre = "en_attente"

    if statut_filtre == "toutes":
        commandes = Order.objects.all()
    else:
        commandes = Order.objects.filter(statut=statut_filtre)

    recherche = request.GET.get("q", "").strip()
    if recherche:
        commande_q = Q(utilisateur__username__icontains=recherche) | Q(utilisateur__email__icontains=recherche)
        if recherche.isdigit():
            commande_q |= Q(id=int(recherche))
        commandes = commandes.filter(commande_q)

    commandes = commandes.select_related(
        "utilisateur", "vendeur_confirmateur"
    ).prefetch_related("items__produit").order_by("-date_creation")
    page_obj = Paginator(commandes, 10).get_page(request.GET.get("page"))
    pagination_params = request.GET.copy(); pagination_params.pop("page", None)
    previous_page_url = f"?{pagination_params.urlencode()}&page={page_obj.previous_page_number()}" if page_obj.has_previous() else ""
    next_page_url = f"?{pagination_params.urlencode()}&page={page_obj.next_page_number()}" if page_obj.has_next() else ""

    # Compteurs par statut
    nb_attente = Order.objects.filter(statut="en_attente").count()
    nb_confirmees = Order.objects.filter(statut="confirmee").count()
    nb_expediees = Order.objects.filter(statut="expediee").count()
    nb_livrees = Order.objects.filter(statut="livree").count()
    nb_annulees = Order.objects.filter(statut="annulee").count()

    context = {
        "commandes": commandes,
        "statut_filtre": statut_filtre,
        "nb_attente": nb_attente,
        "nb_confirmees": nb_confirmees,
        "nb_expediees": nb_expediees,
        "nb_livrees": nb_livrees,
        "nb_annulees": nb_annulees,
        "page_obj": page_obj,
        "recherche": recherche,
        "query_params": request.GET.copy(),
        "previous_page_url": previous_page_url, "next_page_url": next_page_url,
    }

    return render(request, "dashboard/vendeur_commandes.html", context)


@vendeur_required
def vendeur_commande_detail(request, commande_id):
    commande = get_object_or_404(
        Order.objects
        .select_related(
            "utilisateur",
            "vendeur_confirmateur",
            "payment",
        )
        .prefetch_related("items__produit"),
        id=commande_id,
    )

    return render(
        request,
        "dashboard/vendeur_commande_detail.html",
        {
            "commande": commande,
            "paiement": getattr(commande, "payment", None),
            "commande_sous_total": sum(
                item.sous_total()
                for item in commande.items.all()
            ),
        },
    )


@vendeur_required
def confirmer_commande(request, commande_id, action=None):
    """
    Gère le cycle de vie d'une commande côté vendeur.

    - confirmer : valide le paiement manuel et confirme la commande
    - rejeter_paiement : rejette un paiement en attente
    - expediee : marque une commande confirmée comme expédiée
    - livree : marque une commande expédiée comme livrée
    - annuler : annule la commande et restitue le stock
    """

    if request.method != "POST":
        return redirect("vendeur_commandes")

    action = action or request.POST.get("action", "").strip()

    # =========================================================
    # CONFIRMATION DU PAIEMENT + COMMANDE
    # =========================================================
    if action == "confirmer":
        with transaction.atomic():
            commande = get_object_or_404(
                Order.objects
                .select_for_update()
                .select_related("utilisateur"),
                id=commande_id,
            )

            if commande.statut != "en_attente":
                messages.error(
                    request,
                    gettext("Cette commande n'est plus en attente de confirmation."),
                )
                return redirect(
                    "vendeur_commande_detail",
                    commande_id=commande.id,
                )

            try:
                paiement = Payment.objects.select_for_update().get(
                    commande=commande
                )
            except Payment.DoesNotExist:
                messages.error(
                    request,
                    gettext("Aucun paiement n'est associé à cette commande."),
                )
                return redirect(
                    "vendeur_commande_detail",
                    commande_id=commande.id,
                )

            if paiement.statut == "paye":
                messages.info(
                    request,
                    gettext("Ce paiement est déjà confirmé."),
                )
                return redirect(
                    "vendeur_commande_detail",
                    commande_id=commande.id,
                )

            if paiement.statut != "en_attente":
                messages.error(
                    request,
                    gettext("Ce paiement ne peut pas être confirmé dans son état actuel."),
                )
                return redirect(
                    "vendeur_commande_detail",
                    commande_id=commande.id,
                )

            if paiement.montant != commande.total():
                messages.error(request, gettext("Le montant du paiement ne correspond pas au total de la commande."))
                return redirect("vendeur_commande_detail", commande_id=commande.id)

            paiement.statut = "paye"
            paiement.date_paiement = timezone.now()
            paiement.save(
                update_fields=[
                    "statut",
                    "date_paiement",
                ]
            )

            commande.statut = "confirmee"
            commande.vendeur_confirmateur = request.user
            commande.date_confirmation = timezone.now()
            commande.save(
                update_fields=[
                    "statut",
                    "vendeur_confirmateur",
                    "date_confirmation",
                ]
            )

        log_activity(
            user=request.user,
            action="autre",
            details=(
                f"Paiement de la commande #{commande.id} confirmé "
                f"par {request.user.username}. "
                f"Moyen : {paiement.get_methode_display()}. "
                f"Montant : {paiement.montant} FCFA. "
                f"Référence : {paiement.reference or 'Aucune'}."
            ),
            request=request,
            niveau="info",
        )

        messages.success(
            request,
            (
                f"Commande #{commande.id} confirmée. "
                "Le paiement est validé et le reçu est disponible."
            ),
        )

        return redirect(
            "order_receipt",
            id=commande.id,
        )

    # =========================================================
    # REJETER LE PAIEMENT
    # =========================================================
    if action == "rejeter_paiement":
        with transaction.atomic():
            commande = get_object_or_404(
                Order.objects.select_for_update(),
                id=commande_id,
            )

            try:
                paiement = Payment.objects.select_for_update().get(
                    commande=commande
                )
            except Payment.DoesNotExist:
                messages.error(
                    request,
                    gettext("Aucun paiement n'est associé à cette commande."),
                )
                return redirect(
                    "vendeur_commande_detail",
                    commande_id=commande.id,
                )

            if paiement.statut != "en_attente":
                messages.error(
                    request,
                    gettext("Seul un paiement en attente peut être rejeté."),
                )
                return redirect(
                    "vendeur_commande_detail",
                    commande_id=commande.id,
                )

            paiement.statut = "echoue"
            paiement.date_paiement = None
            paiement.save(
                update_fields=[
                    "statut",
                    "date_paiement",
                ]
            )

        log_activity(
            user=request.user,
            action="autre",
            details=(
                f"Paiement de la commande #{commande.id} rejeté "
                f"par {request.user.username}. "
                f"Moyen : {paiement.get_methode_display()}. "
                f"Montant : {paiement.montant} FCFA."
            ),
            request=request,
            niveau="warning",
        )

        messages.warning(
            request,
            f"Paiement de la commande #{commande.id} rejeté.",
        )
        return redirect(
            "vendeur_commande_detail",
            commande_id=commande.id,
        )

    # =========================================================
    # EXPÉDITION
    # =========================================================
    if action == "expediee":
        from orders.models import Livraison
        delivery = Livraison.objects.filter(commande_id=commande_id).first()
        if delivery:
            if delivery.commande.statut == "confirmee":
                delivery.commande.statut = "expediee"
                delivery.commande.date_expedition = timezone.now()
                delivery.commande.save(update_fields=["statut", "date_expedition"])
            messages.info(request, gettext("Utilisez les actions du suivi de livraison."))
            return redirect("livraison_detail", livraison_id=delivery.pk)
        with transaction.atomic():
            commande = get_object_or_404(
                Order.objects.select_for_update(),
                id=commande_id,
            )

            if commande.statut != "confirmee":
                messages.error(
                    request,
                    gettext("Seule une commande confirmée peut être expédiée."),
                )
                return redirect(
                    "vendeur_commande_detail",
                    commande_id=commande.id,
                )

            commande.statut = "expediee"
            commande.date_expedition = timezone.now()
            commande.save(
                update_fields=[
                    "statut",
                    "date_expedition",
                ]
            )

        log_activity(
            user=request.user,
            action="autre",
            details=(
                f"Commande #{commande.id} marquée comme expédiée "
                f"par {request.user.username}."
            ),
            request=request,
            niveau="info",
        )

        messages.success(
            request,
            f"Commande #{commande.id} marquée comme expédiée.",
        )
        return redirect(
            "vendeur_commande_detail",
            commande_id=commande.id,
        )

    # =========================================================
    # LIVRAISON
    # =========================================================
    if action == "livree":
        from orders.models import Livraison
        delivery = Livraison.objects.filter(commande_id=commande_id).first()
        if delivery:
            messages.info(request, gettext("Utilisez les actions du suivi de livraison."))
            return redirect("livraison_detail", livraison_id=delivery.pk)
        with transaction.atomic():
            commande = get_object_or_404(
                Order.objects.select_for_update(),
                id=commande_id,
            )

            if commande.statut != "expediee":
                messages.error(
                    request,
                    gettext("Seule une commande expédiée peut être marquée comme livrée."),
                )
                return redirect(
                    "vendeur_commande_detail",
                    commande_id=commande.id,
                )

            commande.statut = "livree"
            commande.date_livraison = timezone.now()
            commande.save(
                update_fields=[
                    "statut",
                    "date_livraison",
                ]
            )

        log_activity(
            user=request.user,
            action="autre",
            details=(
                f"Commande #{commande.id} marquée comme livrée "
                f"par {request.user.username}."
            ),
            request=request,
            niveau="info",
        )

        messages.success(
            request,
            f"Commande #{commande.id} marquée comme livrée.",
        )
        return redirect(
            "vendeur_commande_detail",
            commande_id=commande.id,
        )

    # =========================================================
    # ANNULATION COMMANDE
    # =========================================================
    if action == "annuler":
        with transaction.atomic():
            commande = get_object_or_404(
                Order.objects
                .select_for_update()
                .prefetch_related("items"),
                id=commande_id,
            )

            if commande.statut not in {
                "en_attente",
                "confirmee",
                "expediee",
            }:
                messages.error(
                    request,
                    gettext("Cette commande ne peut plus être annulée."),
                )
                return redirect(
                    "vendeur_commande_detail",
                    commande_id=commande.id,
                )

            for item in commande.items.all():
                produit = Product.objects.select_for_update().get(
                    pk=item.produit_id
                )
                produit.stock += item.quantite
                produit.quantite_vendue = max(
                    0,
                    produit.quantite_vendue - item.quantite,
                )
                produit.save(
                    update_fields=[
                        "stock",
                        "quantite_vendue",
                    ]
                )

            try:
                paiement = Payment.objects.select_for_update().get(
                    commande=commande
                )
                if paiement.statut == "en_attente":
                    paiement.statut = "annule"
                    paiement.save(
                        update_fields=["statut"]
                    )
            except Payment.DoesNotExist:
                pass

            commande.statut = "annulee"
            commande._delivery_actor = request.user
            commande.date_annulation = timezone.now()
            commande.save(
                update_fields=[
                    "statut",
                    "date_annulation",
                ]
            )

        log_activity(
            user=request.user,
            action="autre",
            details=(
                f"Commande #{commande.id} annulée "
                f"par {request.user.username}. "
                "Le stock correspondant a été restitué."
            ),
            request=request,
            niveau="warning",
        )

        messages.warning(
            request,
            f"Commande #{commande.id} annulée.",
        )
        return redirect(
            "vendeur_commande_detail",
            commande_id=commande.id,
        )

    messages.error(
        request,
        gettext("Action non reconnue."),
    )
    return redirect(
        "vendeur_commande_detail",
        commande_id=commande_id,
    )


# =============================================
# GESTION DES PRODUITS (Vendeur)
# =============================================

@vendeur_required
def vendeur_liste_produits(request):
    """Liste des produits que le vendeur peut gérer."""

    recherche = request.GET.get("q", "").strip()
    categorie_id = request.GET.get("categorie", "")
    try:
        if categorie_id and not 0 < int(categorie_id) <= 9223372036854775807:
            raise ValueError
    except (TypeError, ValueError):
        categorie_id = ""
    actif = request.GET.get("actif", "")
    stock_filtre = request.GET.get("stock", "")
    tri = request.GET.get("tri", "recent")
    produits = Product.objects.select_related("categorie").order_by("-date_creation")

    if recherche:
        produits = produits.filter(
            Q(nom__icontains=recherche)
            | Q(nom_en__icontains=recherche)
            | Q(marque__icontains=recherche)
            | Q(description__icontains=recherche)
            | Q(description_en__icontains=recherche)
        )
    if categorie_id:
        produits = produits.filter(categorie_id=categorie_id)
    if actif == "actif":
        produits = produits.filter(actif=True)
    elif actif == "inactif":
        produits = produits.filter(actif=False)
    if stock_filtre == "rupture":
        produits = produits.filter(stock=0)
    elif stock_filtre == "faible":
        produits = produits.filter(stock__gt=0, stock__lte=5)
    elif stock_filtre == "disponible":
        produits = produits.filter(stock__gt=5)
    produits = produits.order_by({"nom": "nom", "stock": "stock", "prix": "prix"}.get(tri, "-date_creation"))
    page_obj = Paginator(produits, 12).get_page(request.GET.get("page"))
    pagination_params = request.GET.copy(); pagination_params.pop("page", None)
    previous_page_url = f"?{pagination_params.urlencode()}&page={page_obj.previous_page_number()}" if page_obj.has_previous() else ""
    next_page_url = f"?{pagination_params.urlencode()}&page={page_obj.next_page_number()}" if page_obj.has_next() else ""

    context = {
        "produits": page_obj,
        "page_obj": page_obj,
        "recherche": recherche,
        "nb_produits": Product.objects.count(),
        "nb_actifs": Product.objects.filter(actif=True).count(),
        "nb_rupture": Product.objects.filter(stock=0).count(),
        "categories": Category.objects.filter(active=True).order_by("nom"),
        "categorie_id": categorie_id, "actif": actif, "stock_filtre": stock_filtre, "tri": tri,
        "query_params": request.GET.copy(),
        "previous_page_url": previous_page_url, "next_page_url": next_page_url,
    }
    return render(request, "dashboard/vendeur_produits.html", context)


@vendeur_required
def vendeur_stock(request):
    """Vue opérationnelle du stock vendeur."""
    recherche = request.GET.get("q", "").strip()
    etat = request.GET.get("etat", "")
    actif = request.GET.get("actif", "")
    tri = request.GET.get("tri", "stock")
    produits = Product.objects.select_related("categorie")
    if recherche:
        produits = produits.filter(
            Q(nom__icontains=recherche)
            | Q(nom_en__icontains=recherche)
            | Q(marque__icontains=recherche)
            | Q(description__icontains=recherche)
            | Q(description_en__icontains=recherche)
        )
    if etat == "rupture":
        produits = produits.filter(stock=0)
    elif etat == "faible":
        produits = produits.filter(stock__gt=0, stock__lte=5)
    elif etat == "en_stock":
        produits = produits.filter(stock__gt=5)
    if actif == "actif":
        produits = produits.filter(actif=True)
    elif actif == "inactif":
        produits = produits.filter(actif=False)
    produits = produits.order_by({"stock": "stock", "stock_desc": "-stock", "nom": "nom"}.get(tri, "stock"))
    page_obj = Paginator(produits, 12).get_page(request.GET.get("page"))
    pagination_params = request.GET.copy(); pagination_params.pop("page", None)
    previous_page_url = f"?{pagination_params.urlencode()}&page={page_obj.previous_page_number()}" if page_obj.has_previous() else ""
    next_page_url = f"?{pagination_params.urlencode()}&page={page_obj.next_page_number()}" if page_obj.has_next() else ""
    return render(request, "dashboard/vendeur_stock.html", {
        "produits": page_obj, "page_obj": page_obj, "recherche": recherche,
        "etat": etat, "actif": actif, "tri": tri, "query_params": request.GET.copy(),
        "nb_rupture": Product.objects.filter(stock=0).count(),
        "nb_faible": Product.objects.filter(stock__gt=0, stock__lte=5).count(),
        "nb_disponibles": Product.objects.filter(stock__gt=5).count(),
        "previous_page_url": previous_page_url, "next_page_url": next_page_url,
    })


@vendeur_required
def vendeur_ajouter_categorie(request):
    """Créer rapidement une nouvelle catégorie depuis l'espace vendeur."""

    if request.method != "POST":
        return redirect("vendeur_ajouter_produit")

    nom = request.POST.get("nom_categorie", "").strip()
    nom_en = request.POST.get("nom_categorie_en", "").strip()

    if not nom:
        messages.error(
            request,
            gettext("Le nom de la catégorie est obligatoire.")
        )
        return redirect("vendeur_ajouter_produit")

    # Éviter les doublons de catégories
    categorie_existante = Category.objects.filter(
        nom__iexact=nom
    ).first()

    if categorie_existante:
        messages.info(
            request,
            f"La catégorie « {categorie_existante.nom} » existe déjà."
        )
        return redirect(
            f"{reverse('vendeur_ajouter_produit')}?categorie={categorie_existante.id}"
        )

    # Générer un slug unique
    base_slug = slugify(nom) or "categorie"
    slug = base_slug
    compteur = 1

    while Category.objects.filter(slug=slug).exists():
        slug = f"{base_slug}-{compteur}"
        compteur += 1

    categorie = Category.objects.create(
        nom=nom,
        nom_en=nom_en,
        slug=slug,
        active=True,
    )

    log_activity(
        user=request.user,
        action="autre",
        details=(
            f"Nouvelle catégorie créée par "
            f"{request.user.username} : {categorie.nom}."
        ),
        request=request,
        niveau="info",
    )

    messages.success(
        request,
        f"Catégorie « {categorie.nom} » créée avec succès."
    )

    return redirect(
        f"{reverse('vendeur_ajouter_produit')}?categorie={categorie.id}"
    )


@vendeur_required
def vendeur_ajouter_produit(request):
    """Ajouter un nouveau produit depuis le dashboard vendeur."""

    categories = Category.objects.filter(active=True).order_by("nom")
    categorie_prefill = request.GET.get("categorie", "")

    if request.method == "POST":
        nom = request.POST.get("nom", "").strip()
        nom_en = request.POST.get("nom_en", "").strip()
        description = request.POST.get("description", "").strip()
        description_en = request.POST.get("description_en", "").strip()
        prix = request.POST.get("prix", "")
        prix_promotion = request.POST.get("prix_promotion", "").strip()
        stock = request.POST.get("stock", 0)
        categorie_id = request.POST.get("categorie")
        marque = request.POST.get("marque", "").strip()
        actif = request.POST.get("actif") == "on"
        vedette = request.POST.get("vedette") == "on"
        image = request.FILES.get("image")

        image_error = _validate_product_image(image)
        if image_error:
            messages.error(request, image_error)
            return render(request, "dashboard/vendeur_ajouter_produit.html", _product_form_context(
                request, categories, form_errors={"image": image_error}
            ))

        if not nom:
            error = "Le nom du produit est obligatoire."
            messages.error(request, error)
            return render(request, "dashboard/vendeur_ajouter_produit.html", _product_form_context(
                request, categories, form_errors={"nom": error}
            ))

        try:
            prix = float(prix)
            if prix <= 0:
                raise ValueError
        except (ValueError, TypeError):
            error = "Le prix doit être un nombre supérieur à 0."
            messages.error(request, error)
            return render(request, "dashboard/vendeur_ajouter_produit.html", _product_form_context(
                request, categories, form_errors={"prix": error}
            ))

        try:
            stock = int(stock)
            if stock < 0:
                raise ValueError
        except (ValueError, TypeError):
            error = "Le stock doit être un nombre entier supérieur ou égal à 0."
            messages.error(request, error)
            return render(request, "dashboard/vendeur_ajouter_produit.html", _product_form_context(
                request, categories, form_errors={"stock": error}
            ))

        promo_value = None
        if prix_promotion:
            try:
                promo_value = float(prix_promotion)
                if promo_value < 0 or promo_value >= prix:
                    raise ValueError
            except (ValueError, TypeError):
                error = "Le prix promotionnel doit être inférieur au prix normal."
                messages.error(request, error)
                return render(request, "dashboard/vendeur_ajouter_produit.html", _product_form_context(
                    request, categories, form_errors={"prix_promotion": error}
                ))

        categorie = get_object_or_404(Category, id=categorie_id) if categorie_id else None
        if not categorie:
            error = "Veuillez choisir une catégorie."
            messages.error(request, error)
            return render(request, "dashboard/vendeur_ajouter_produit.html", _product_form_context(
                request, categories, form_errors={"categorie": error}
            ))

        # Générer slug unique
        base_slug = slugify(nom)
        slug = base_slug
        counter = 1
        while Product.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

        produit = Product(
            nom=nom,
            slug=slug,
            description=description,
            nom_en=nom_en,
            description_en=description_en,
            prix=prix,
            stock=stock,
            categorie=categorie,
            marque=marque,
            actif=actif,
            vedette=vedette,
        )

        produit.prix_promotion = promo_value

        if image:
            produit.image = image

        produit.save()

        log_activity(
            user=request.user,
            action="stock_modifie",
            details=f"Nouveau produit ajouté par {request.user.username} : {nom} (Stock: {stock}, Prix: {prix} FCFA).",
            request=request,
            niveau="info"
        )

        messages.success(request, gettext("Produit « {name} » ajouté avec succès.").format(name=nom))
        return redirect("vendeur_liste_produits")

    context = _product_form_context(
        request,
        categories
    )

    if categorie_prefill:
        context["form_categorie"] = categorie_prefill

    return render(
        request,
        "dashboard/vendeur_ajouter_produit.html",
        context
    )


@vendeur_required
def vendeur_modifier_produit(request, produit_id):
    """Modifier un produit existant depuis le dashboard vendeur."""

    produit = get_object_or_404(Product, id=produit_id)
    categories = Category.objects.filter(active=True).order_by("nom")

    if request.method == "POST":
        nom = request.POST.get("nom", "").strip()
        nom_en = request.POST.get("nom_en", "").strip()
        description = request.POST.get("description", "").strip()
        description_en = request.POST.get("description_en", "").strip()
        prix = request.POST.get("prix", "")
        prix_promotion = request.POST.get("prix_promotion", "").strip()
        stock = request.POST.get("stock", 0)
        categorie_id = request.POST.get("categorie")
        marque = request.POST.get("marque", "").strip()
        actif = request.POST.get("actif") == "on"
        vedette = request.POST.get("vedette") == "on"
        image = request.FILES.get("image")

        image_error = _validate_product_image(image)
        if image_error:
            messages.error(request, image_error)
            return render(request, "dashboard/vendeur_modifier_produit.html", _product_form_context(
                request, categories, produit, {"image": image_error}
            ))

        if not nom:
            error = "Le nom du produit est obligatoire."
            messages.error(request, error)
            return render(request, "dashboard/vendeur_modifier_produit.html", _product_form_context(
                request, categories, produit, {"nom": error}
            ))

        try:
            prix = float(prix)
            if prix <= 0:
                raise ValueError
        except (ValueError, TypeError):
            error = "Le prix doit être un nombre supérieur à 0."
            messages.error(request, error)
            return render(request, "dashboard/vendeur_modifier_produit.html", _product_form_context(
                request, categories, produit, {"prix": error}
            ))

        try:
            stock = int(stock)
            if stock < 0:
                raise ValueError
        except (ValueError, TypeError):
            error = "Le stock doit être un nombre entier supérieur ou égal à 0."
            messages.error(request, error)
            return render(request, "dashboard/vendeur_modifier_produit.html", _product_form_context(
                request, categories, produit, {"stock": error}
            ))

        promo_value = None
        if prix_promotion:
            try:
                promo_value = float(prix_promotion)
                if promo_value < 0 or promo_value >= prix:
                    raise ValueError
            except (ValueError, TypeError):
                error = "Le prix promotionnel doit être inférieur au prix normal."
                messages.error(request, error)
                return render(request, "dashboard/vendeur_modifier_produit.html", _product_form_context(
                    request, categories, produit, {"prix_promotion": error}
                ))

        categorie = get_object_or_404(Category, id=categorie_id) if categorie_id else produit.categorie
        if not categorie:
            error = "Veuillez choisir une catégorie."
            messages.error(request, error)
            return render(request, "dashboard/vendeur_modifier_produit.html", _product_form_context(
                request, categories, produit, {"categorie": error}
            ))

        ancien_stock = produit.stock
        produit.nom = nom
        produit.description = description
        produit.nom_en = nom_en
        produit.description_en = description_en
        produit.prix = prix
        produit.stock = stock
        produit.categorie = categorie
        produit.marque = marque
        produit.actif = actif
        produit.vedette = vedette

        produit.prix_promotion = promo_value

        if image:
            produit.image = image

        produit.save()

        log_activity(
            user=request.user,
            action="prix_modifie",
            details=(
                f"Produit modifié par {request.user.username} : {nom}. "
                f"Stock : {ancien_stock} → {stock}. Prix : {prix} FCFA."
            ),
            request=request,
            niveau="info"
        )

        messages.success(request, gettext("Produit « {name} » modifié avec succès.").format(name=nom))
        return redirect("vendeur_liste_produits")

    return render(request, "dashboard/vendeur_modifier_produit.html", _product_form_context(
        request, categories, produit
    ))


@vendeur_required
def vendeur_toggle_produit(request, produit_id):
    """Activer/désactiver un produit."""

    if request.method == "POST":
        produit = get_object_or_404(Product, id=produit_id)
        produit.actif = not produit.actif
        produit.save()

        etat = "activé" if produit.actif else "désactivé"
        messages.success(request, gettext("Produit « {name} » {state}.").format(name=produit.nom, state=etat))

    return redirect("vendeur_liste_produits")


# =============================================
# GESTION DES PANIERS (Vendeur)
# =============================================

@vendeur_required
def vendeur_paniers(request):
    """Vue des paniers actifs des clients."""

    paniers = Cart.objects.select_related("utilisateur").prefetch_related(
        "items__produit"
    ).exclude(items=None).order_by("-date_creation")

    # Valeur totale de tous les paniers actifs
    total_paniers = sum(panier.total() for panier in paniers)

    context = {
        "paniers": paniers,
        "nb_paniers": paniers.count(),
        "total_paniers": total_paniers,
    }
    return render(request, "dashboard/vendeur_paniers.html", context)
