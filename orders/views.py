from decimal import Decimal
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from cart.models import Cart
from payments.models import Payment
from products.models import Product
from .models import Order, OrderItem


DELIVERY_OPTIONS = {
    "standard": {"label": "Livraison standard", "description": "Sous 2 à 4 jours ouvrés", "fee": Decimal("0")},
    "express": {"label": "Livraison express", "description": "Prioritaire sous 24 à 48 h", "fee": Decimal("2500")},
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
        },
    }


@login_required
def create_order(request):
    panier = Cart.objects.filter(utilisateur=request.user).first()
    if not panier or not panier.items.exists():
        messages.info(request, "Votre panier est vide. Ajoutez un produit avant de poursuivre.")
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
    }
    errors = []
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
                messages.info(request, "Votre panier est déjà vide.")
                return redirect("cart_detail")

            locked_products = {}
            for article in articles:
                produit = Product.objects.select_for_update().get(pk=article.produit_id)
                locked_products[produit.id] = produit
                if article.quantite > produit.stock:
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
                statut="paye",
                reference=f"SIM-{uuid.uuid4().hex[:12].upper()}",
                date_paiement=timezone.now(),
            )
            panier.items.all().delete()
            request.session["last_checkout_order_id"] = commande.id
    except Product.DoesNotExist:
        messages.error(request, "Un produit de votre panier n'est plus disponible.")
        return redirect("cart_detail")

    return render(request, "orders/checkout_confirmation.html", {"commande": commande, "paiement": paiement})


@login_required
def my_orders(request):
    commandes = Order.objects.filter(utilisateur=request.user).select_related("payment").order_by("-date_creation")
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


@login_required
def order_detail(request, id):
    commande = get_object_or_404(
        Order.objects.select_related("payment", "utilisateur").prefetch_related("items__produit"),
        id=id,
    )
    if not request.user.is_staff and commande.utilisateur_id != request.user.id:
        return get_object_or_404(Order, id=id, utilisateur=request.user)
    return render(request, "orders/order_detail.html", {
        "commande": commande,
        "commande_sous_total": sum(item.sous_total() for item in commande.items.all()),
    })
