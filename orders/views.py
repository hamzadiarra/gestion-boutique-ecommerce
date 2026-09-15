from django.utils.translation import gettext, gettext_lazy
from decimal import Decimal
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from cart.models import Cart
from payments.models import Payment
from products.models import Product
from .models import Order, OrderItem
from dashboard.models import BoutiqueSettings
from .delivery_forms import AdresseLivraisonForm


DELIVERY_OPTIONS = {
    "standard": {"label": gettext_lazy("Livraison standard"), "description": gettext_lazy("Sous 2 à 4 jours ouvrés"), "fee": Decimal("0")},
    "express": {"label": gettext_lazy("Livraison express"), "description": gettext_lazy("Prioritaire sous 24 à 48 h"), "fee": Decimal("2500")},
}


def _checkout_context(request, panier=None, errors=None, active_step=1, values=None):
    panier = panier or Cart.objects.filter(utilisateur=request.user).first()
    articles = panier.items.select_related("produit__categorie").all() if panier else []
    profil = getattr(request.user, "profile", None)
    values = values or {}
    return {
        "panier": panier,
        "articles": articles,
        "sous_total": panier.total() if panier else 0,
        "delivery_options": DELIVERY_OPTIONS,
        "frais_estimes": DELIVERY_OPTIONS.get(values.get("mode_livraison", "standard"), DELIVERY_OPTIONS["standard"])["fee"],
        "total_estime": (panier.total() if panier else 0) + DELIVERY_OPTIONS.get(values.get("mode_livraison", "standard"), DELIVERY_OPTIONS["standard"])["fee"],
        "errors": errors or [],
        "active_step": active_step,
        "checkout_values": {
            "adresse": values.get("adresse", profil.adresse if profil else ""),
            "ville": values.get("ville", profil.ville if profil else ""),
            "code_postal": values.get("code_postal", profil.code_postal if profil else ""),
            "mode_livraison": values.get("mode_livraison", "standard"),
            "note": values.get("note", ""),
            "methode": values.get("methode", "orange_money"),
            "numero_rue": values.get("numero_rue", ""),
            "numero_porte": values.get("numero_porte", ""),
            "telephone_livraison": values.get("telephone_livraison", (profil.telephone or "") if profil else ""),
        },
    }


@never_cache
@login_required
def create_order(request):
    panier = Cart.objects.filter(utilisateur=request.user).first()
    if not panier or not panier.items.exists():
        messages.info(request, gettext("Votre panier est vide. Ajoutez un produit avant de poursuivre."))
        return redirect("cart_detail")

    if request.method != "POST" or request.POST.get("finalize") != "1":
        return render(request, "orders/checkout.html", _checkout_context(request, panier))

    values = {
        "adresse": request.POST.get("adresse", "").strip(),
        "ville": request.POST.get("ville", "").strip(),
        "code_postal": request.POST.get("code_postal", "").strip(),
        "mode_livraison": request.POST.get("mode_livraison", "standard"),
        "note": request.POST.get("note", "").strip(),
        "methode": request.POST.get("methode", ""),
        "numero_rue": request.POST.get("numero_rue", "").strip(),
        "numero_porte": request.POST.get("numero_porte", "").strip(),
        "telephone_livraison": request.POST.get("telephone_livraison", getattr(getattr(request.user, "profile", None), "telephone", "") or "").strip(),
    }
    errors = []
    adresse_form = AdresseLivraisonForm(values)
    if not adresse_form.is_valid():
        errors.extend(f"{field}: {error}" for field, items in adresse_form.errors.items() for error in items)
    if not values["adresse"] or not values["ville"]:
        errors.append("Renseignez votre adresse et votre ville de livraison.")
    if values["mode_livraison"] not in DELIVERY_OPTIONS:
        errors.append("Choisissez un mode de livraison valide.")
    if values["methode"] not in dict(Payment.METHODES):
        errors.append("Choisissez un moyen de paiement valide.")
    if errors:
        return render(request, "orders/checkout.html", _checkout_context(request, panier, errors, 1, values))

    try:
        with transaction.atomic():
            panier = Cart.objects.select_for_update().get(utilisateur=request.user)
            articles = list(panier.items.select_related("produit").all())
            if not articles:
                last_order_id = request.session.get("last_checkout_order_id")
                if last_order_id:
                    return redirect("order_detail", id=last_order_id)
                messages.info(request, gettext("Votre panier est déjà vide."))
                return redirect("cart_detail")

            locked_products = {}
            requested_quantities = {}
            for article in articles:
                produit = Product.objects.select_for_update().get(pk=article.produit_id)
                locked_products[produit.id] = produit
                requested_quantities[produit.id] = requested_quantities.get(produit.id, 0) + article.quantite
                if not produit.actif or article.quantite <= 0:
                    errors.append(f"Le produit « {produit.nom} » n'est plus disponible pour cette commande.")
                if requested_quantities[produit.id] > produit.stock:
                    errors.append(f"Stock insuffisant pour « {produit.nom} » : {produit.stock} disponible(s).")
            if errors:
                return render(request, "orders/checkout.html", _checkout_context(request, panier, errors, 2, values))

            delivery = DELIVERY_OPTIONS[values["mode_livraison"]]
            commande = Order.objects.create(
                utilisateur=request.user,
                note=values["note"] or None,
                adresse_livraison=values["adresse"],
                ville_livraison=values["ville"],
                code_postal_livraison=values["code_postal"] or None,
                mode_livraison=values["mode_livraison"],
                frais_livraison=delivery["fee"],
                **adresse_form.cleaned_data,
            )
            for article in articles:
                produit = locked_products[article.produit_id]
                OrderItem.objects.create(commande=commande, produit=produit, quantite=article.quantite, prix=article.prix)
                produit.stock -= article.quantite
                produit.quantite_vendue += article.quantite
                produit.save(update_fields=["stock", "quantite_vendue", "date_modification"])

            paiement = Payment.objects.create(
                commande=commande,
                montant=commande.total(),
                methode=values["methode"],
                statut="en_attente",
                reference=f"PAY-{uuid.uuid4().hex[:12].upper()}",
                date_paiement=None,
            )
            panier.items.all().delete()
            from .delivery_services import initialiser_livraison
            initialiser_livraison(commande, request.user, checkout=True)
            request.session["last_checkout_order_id"] = commande.id
    except Product.DoesNotExist:
        messages.error(request, gettext("Un produit de votre panier n'est plus disponible."))
        return redirect("cart_detail")

    return render(request, "orders/checkout_confirmation.html", {"commande": commande, "paiement": paiement})


@never_cache
@login_required
def my_orders(request):
    commandes = Order.objects.filter(utilisateur=request.user).select_related("payment", "livraison").prefetch_related("items__produit").order_by("-date_creation")
    statut = request.GET.get("statut", "")
    recherche = request.GET.get("q", "").strip()
    if statut in dict(Order.STATUT_CHOICES):
        commandes = commandes.filter(statut=statut)
    if recherche.isdigit():
        commandes = commandes.filter(id=int(recherche))
    query_params = request.GET.copy()
    query_params.pop("page", None)
    page_obj = Paginator(commandes, 8).get_page(request.GET.get("page"))
    return render(request, "orders/my_orders.html", {
        "page_obj": page_obj,
        "statut": statut,
        "recherche": recherche,
        "query_params": query_params.urlencode(),
        "statuts": Order.STATUT_CHOICES,
    })


@never_cache
@login_required
def order_detail(request, id):
    commande = get_object_or_404(
        Order.objects.select_related("payment", "utilisateur").prefetch_related("items__produit"),
        id=id,
    )
    role = getattr(getattr(request.user, "profile", None), "role", None)
    if not (request.user.is_superuser or role in {"admin", "vendeur"}) and commande.utilisateur_id != request.user.id:
        return get_object_or_404(Order, id=id, utilisateur=request.user)
    return render(request, "orders/order_detail.html", {
        "commande": commande,
            "commande_sous_total": sum(item.sous_total() for item in commande.items.all()),
            "boutique_settings": BoutiqueSettings.get_solo(),
    })
@never_cache
@login_required
def order_receipt(request, id):
    """
    Affiche le reçu officiel d'une commande.

    Le reçu n'est disponible qu'après confirmation de la commande.
    """

    commande = get_object_or_404(
        Order.objects
        .select_related(
            "utilisateur",
            "vendeur_confirmateur",
            "payment",
        )
        .prefetch_related(
            "items__produit",
            "items__produit__categorie",
        ),
        id=id,
    )

    # ==========================================
    # PERMISSIONS
    # ==========================================

    profile = getattr(request.user, "profile", None)

    is_owner = commande.utilisateur_id == request.user.id

    is_vendor = (
        profile is not None
        and profile.role == "vendeur"
    )

    is_admin = (
        request.user.is_superuser
        or (
            profile is not None
            and profile.role == "admin"
        )
    )

    # Le client ne peut voir que son propre reçu.
    # Vendeur/admin peuvent consulter un reçu confirmé.
    if not (is_owner or is_vendor or is_admin):
        messages.error(
            request,
            gettext("Vous n'êtes pas autorisé à consulter ce reçu.")
        )
        return redirect("home")

    # ==========================================
    # COMMANDE DEVANT ÊTRE CONFIRMÉE
    # ==========================================

    receipt_statuses = {
        "confirmee",
        "expediee",
        "livree",
    }

    paiement = getattr(commande, "payment", None)
    if commande.statut not in receipt_statuses or not paiement or paiement.statut != "paye":
        messages.info(
            request,
            gettext("Le reçu sera disponible après confirmation de la commande et du paiement.")
        )

        if is_owner:
            return redirect(
                "order_detail",
                id=commande.id
            )

        return redirect("vendeur_commandes")

    # ==========================================
    # CALCULS
    # ==========================================

    items = list(commande.items.all())

    sous_total = sum(
        item.sous_total()
        for item in items
    )

    frais_livraison = commande.frais_livraison or Decimal("0")

    total = sous_total + frais_livraison

    # ==========================================
    # PAIEMENT
    # ==========================================

    try:
        paiement = commande.payment
    except Payment.DoesNotExist:
        paiement = None

    # ==========================================
    # NUMÉRO DE REÇU
    # ==========================================

    year = commande.date_confirmation.year if commande.date_confirmation else commande.date_creation.year

    numero_recu = (
        f"REC-{year}-{commande.id:06d}"
    )

    # ==========================================
    # CLIENT
    # ==========================================

    client_name = (
        commande.utilisateur.get_full_name().strip()
        or commande.utilisateur.username
    )

    # ==========================================
    # VENDEUR
    # ==========================================

    vendeur_name = None

    if commande.vendeur_confirmateur:
        vendeur_name = (
            commande.vendeur_confirmateur
            .get_full_name()
            .strip()
            or commande.vendeur_confirmateur.username
        )

    return render(
        request,
        "orders/receipt.html",
        {
            "commande": commande,
            "items": items,
            "paiement": paiement,
            "numero_recu": numero_recu,
            "client_name": client_name,
            "vendeur_name": vendeur_name,
            "sous_total": sous_total,
            "frais_livraison": frais_livraison,
            "total": total,
            "boutique_settings": BoutiqueSettings.get_solo(),
        },
    )
