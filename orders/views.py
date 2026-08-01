from django.shortcuts import redirect, render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from cart.models import Cart
from .models import Order, OrderItem


@login_required
def create_order(request):
    if request.method != "POST":
        return redirect("cart_detail")

    try:
        panier = Cart.objects.get(
            utilisateur=request.user
        )
    except Cart.DoesNotExist:
        messages.warning(request, "Votre panier est vide.")
        return redirect("cart_detail")

    articles = panier.items.all()


    if not articles.exists():
        messages.warning(request, "Votre panier est vide.")
        return redirect("cart_detail")

    # Vérifier le stock avant de créer la commande
    for article in articles:
        if article.quantite > article.produit.stock:
            messages.error(
                request,
                f"Stock insuffisant pour « {article.produit.nom} » "
                f"(disponible : {article.produit.stock}, demandé : {article.quantite})."
            )
            return redirect("cart_detail")

    note = request.POST.get("note", "").strip() if request.method == "POST" else ""

    commande = Order.objects.create(
        utilisateur=request.user,
        note=note if note else None
    )


    for article in articles:

        OrderItem.objects.create(
            commande=commande,
            produit=article.produit,
            quantite=article.quantite,
            prix=article.prix
        )

        # Décrémenter le stock et incrémenter les ventes
        article.produit.stock -= article.quantite
        article.produit.quantite_vendue += article.quantite
        article.produit.save()


    panier.items.all().delete()

    messages.success(request, f"Commande #{commande.id} créée avec succès ! 🎉")

    return render(
        request,
        "orders/order_success.html",
        {
            "commande": commande
        }
    )



@login_required
def my_orders(request):

    commandes = Order.objects.filter(
        utilisateur=request.user
    ).order_by("-date_creation")


    return render(
        request,
        "orders/my_orders.html",
        {
            "commandes": commandes
        }
    )



@login_required
def order_detail(request, id):
    if request.user.is_staff:
        commande = get_object_or_404(Order, id=id)
    else:
        commande = get_object_or_404(
            Order,
            id=id,
            utilisateur=request.user
        )


    return render(
        request,
        "orders/order_detail.html",
        {
            "commande": commande
        }
    )