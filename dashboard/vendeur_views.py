from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Count
from django.utils import timezone
from django.utils.text import slugify

from accounts.decorators import vendeur_required
from products.models import Product
from categories.models import Category
from orders.models import Order, OrderItem
from cart.models import Cart, CartItem
from .models import Vente, log_activity


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

    context = {
        "total_ventes_jour": total_ventes_jour,
        "total_ventes_mois": total_ventes_mois,
        "total_ventes_global": total_ventes_global,
        "nb_ventes_jour": nb_ventes_jour,
        "nb_ventes_mois": nb_ventes_mois,
        "nb_ventes_total": nb_ventes_total,
        "produits": produits,
        "dernieres_ventes": dernieres_ventes,
        "commandes_en_attente": commandes_en_attente,
        "nb_commandes_attente": nb_commandes_attente,
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
        quantite = int(quantite)
        if quantite <= 0:
            raise ValueError
    except (ValueError, TypeError):
        messages.error(request, "La quantité doit être un nombre positif.")
        return redirect("vendeur_dashboard")

    produit = get_object_or_404(Product, id=produit_id, actif=True)

    # Vérifier le stock
    if quantite > produit.stock:
        messages.error(
            request,
            f"Stock insuffisant pour « {produit.nom} » — disponible : {produit.stock}, demandé : {quantite}."
        )
        return redirect("vendeur_dashboard")

    # Calculer le montant
    prix_unitaire = produit.prix_promotion if produit.prix_promotion else produit.prix
    montant_total = prix_unitaire * quantite

    # Créer la vente
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

    # Mettre à jour le stock
    produit.stock -= quantite
    produit.quantite_vendue += quantite
    produit.save()

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

    messages.success(
        request,
        f"✅ Vente #{vente.id} enregistrée — {produit.nom} x{quantite} = {montant_total} FCFA"
    )
    return redirect("vendeur_dashboard")


@vendeur_required
def historique_ventes(request):
    """Historique complet des ventes du vendeur."""

    mes_ventes = Vente.objects.filter(vendeur=request.user)

    return render(request, "dashboard/vendeur_historique.html", {
        "ventes": mes_ventes,
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

    commandes = commandes.select_related(
        "utilisateur", "vendeur_confirmateur"
    ).prefetch_related("items__produit").order_by("-date_creation")

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
    }

    return render(request, "dashboard/vendeur_commandes.html", context)


@vendeur_required
def confirmer_commande(request, commande_id):
    """Confirmer ou refuser une commande client."""

    if request.method != "POST":
        return redirect("vendeur_commandes")

    commande = get_object_or_404(Order, id=commande_id)
    action = request.POST.get("action")

    if action == "confirmer":
        commande.statut = "confirmee"
        commande.vendeur_confirmateur = request.user
        commande.date_confirmation = timezone.now()
        commande.save()

        log_activity(
            user=request.user,
            action="autre",
            details=f"Commande #{commande.id} de {commande.utilisateur.username} confirmée par {request.user.username}.",
            request=request,
            niveau="info"
        )
        messages.success(request, f"✅ Commande #{commande.id} confirmée avec succès !")

    elif action == "expediee":
        commande.statut = "expediee"
        commande.save()
        messages.success(request, f"🚚 Commande #{commande.id} marquée comme expédiée.")

    elif action == "livree":
        commande.statut = "livree"
        commande.save()
        messages.success(request, f"📦 Commande #{commande.id} marquée comme livrée.")

    elif action == "annuler":
        if commande.statut == "en_attente":
            # Remettre le stock des produits
            for item in commande.items.all():
                item.produit.stock += item.quantite
                item.produit.quantite_vendue -= item.quantite
                item.produit.save()

        commande.statut = "annulee"
        commande.save()

        log_activity(
            user=request.user,
            action="autre",
            details=f"Commande #{commande.id} de {commande.utilisateur.username} annulée par {request.user.username}.",
            request=request,
            niveau="warning"
        )
        messages.warning(request, f"❌ Commande #{commande.id} annulée.")

    else:
        messages.error(request, "Action non reconnue.")

    return redirect("vendeur_commandes")


# =============================================
# GESTION DES PRODUITS (Vendeur)
# =============================================

@vendeur_required
def vendeur_liste_produits(request):
    """Liste des produits que le vendeur peut gérer."""

    recherche = request.GET.get("q", "")
    produits = Product.objects.select_related("categorie").order_by("-date_creation")

    if recherche:
        produits = produits.filter(nom__icontains=recherche)

    context = {
        "produits": produits,
        "recherche": recherche,
        "nb_produits": produits.count(),
        "nb_actifs": Product.objects.filter(actif=True).count(),
        "nb_rupture": Product.objects.filter(stock=0).count(),
    }
    return render(request, "dashboard/vendeur_produits.html", context)


@vendeur_required
def vendeur_ajouter_produit(request):
    """Ajouter un nouveau produit depuis le dashboard vendeur."""

    categories = Category.objects.filter(active=True).order_by("nom")

    if request.method == "POST":
        nom = request.POST.get("nom", "").strip()
        description = request.POST.get("description", "").strip()
        prix = request.POST.get("prix", "")
        prix_promotion = request.POST.get("prix_promotion", "").strip()
        stock = request.POST.get("stock", 0)
        categorie_id = request.POST.get("categorie")
        marque = request.POST.get("marque", "").strip()
        actif = request.POST.get("actif") == "on"
        vedette = request.POST.get("vedette") == "on"
        image = request.FILES.get("image")

        # Validations
        if not nom:
            messages.error(request, "Le nom du produit est obligatoire.")
            return render(request, "dashboard/vendeur_ajouter_produit.html", {"categories": categories})

        try:
            prix = float(prix)
            if prix <= 0:
                raise ValueError
        except (ValueError, TypeError):
            messages.error(request, "Le prix doit être un nombre positif.")
            return render(request, "dashboard/vendeur_ajouter_produit.html", {"categories": categories})

        try:
            stock = int(stock)
        except (ValueError, TypeError):
            stock = 0

        categorie = get_object_or_404(Category, id=categorie_id) if categorie_id else None
        if not categorie:
            messages.error(request, "Veuillez choisir une catégorie.")
            return render(request, "dashboard/vendeur_ajouter_produit.html", {"categories": categories})

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
            prix=prix,
            stock=stock,
            categorie=categorie,
            marque=marque,
            actif=actif,
            vedette=vedette,
        )

        if prix_promotion:
            try:
                produit.prix_promotion = float(prix_promotion)
            except (ValueError, TypeError):
                pass

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

        messages.success(request, f"✅ Produit « {nom} » ajouté avec succès !")
        return redirect("vendeur_liste_produits")

    return render(request, "dashboard/vendeur_ajouter_produit.html", {"categories": categories})


@vendeur_required
def vendeur_modifier_produit(request, produit_id):
    """Modifier un produit existant depuis le dashboard vendeur."""

    produit = get_object_or_404(Product, id=produit_id)
    categories = Category.objects.filter(active=True).order_by("nom")

    if request.method == "POST":
        nom = request.POST.get("nom", "").strip()
        description = request.POST.get("description", "").strip()
        prix = request.POST.get("prix", "")
        prix_promotion = request.POST.get("prix_promotion", "").strip()
        stock = request.POST.get("stock", 0)
        categorie_id = request.POST.get("categorie")
        marque = request.POST.get("marque", "").strip()
        actif = request.POST.get("actif") == "on"
        vedette = request.POST.get("vedette") == "on"
        image = request.FILES.get("image")

        if not nom:
            messages.error(request, "Le nom du produit est obligatoire.")
            return render(request, "dashboard/vendeur_modifier_produit.html", {
                "produit": produit, "categories": categories
            })

        try:
            prix = float(prix)
        except (ValueError, TypeError):
            messages.error(request, "Prix invalide.")
            return render(request, "dashboard/vendeur_modifier_produit.html", {
                "produit": produit, "categories": categories
            })

        try:
            stock = int(stock)
        except (ValueError, TypeError):
            stock = produit.stock

        categorie = get_object_or_404(Category, id=categorie_id) if categorie_id else produit.categorie

        ancien_stock = produit.stock
        produit.nom = nom
        produit.description = description
        produit.prix = prix
        produit.stock = stock
        produit.categorie = categorie
        produit.marque = marque
        produit.actif = actif
        produit.vedette = vedette

        produit.prix_promotion = float(prix_promotion) if prix_promotion else None

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

        messages.success(request, f"✅ Produit « {nom} » modifié avec succès !")
        return redirect("vendeur_liste_produits")

    return render(request, "dashboard/vendeur_modifier_produit.html", {
        "produit": produit,
        "categories": categories,
    })


@vendeur_required
def vendeur_toggle_produit(request, produit_id):
    """Activer/désactiver un produit."""

    if request.method == "POST":
        produit = get_object_or_404(Product, id=produit_id)
        produit.actif = not produit.actif
        produit.save()

        etat = "activé" if produit.actif else "désactivé"
        messages.success(request, f"Produit « {produit.nom} » {etat}.")

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
