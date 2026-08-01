from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from products.models import Product
from .models import Cart, CartItem



@login_required
def add_to_cart(request, product_id):

    produit = get_object_or_404(
        Product,
        id=product_id,
        actif=True
    )

    # Vérifier le stock
    if produit.stock <= 0:
        messages.warning(request, f"« {produit.nom} » est en rupture de stock.")
        return redirect("product_list")

    panier, created = Cart.objects.get_or_create(
        utilisateur=request.user
    )


    article, created = CartItem.objects.get_or_create(
        panier=panier,
        produit=produit,
        defaults={
            "prix": produit.prix_promotion or produit.prix,
            "quantite": 1
        }
    )


    if not created:
        if article.quantite >= produit.stock:
            messages.warning(
                request,
                f"Stock maximum atteint pour « {produit.nom} » ({produit.stock} disponibles)."
            )
            return redirect("cart_detail")

        article.quantite += 1
        article.save()

    messages.success(request, f"« {produit.nom} » ajouté au panier ! 🛒")

    return redirect("cart_detail")




@login_required
def cart_detail(request):

    panier, created = Cart.objects.get_or_create(
        utilisateur=request.user
    )


    articles = panier.items.all()


    context = {
        "panier": panier,
        "articles": articles,
        "total": panier.total()
    }


    return render(
        request,
        "cart/cart_detail.html",
        context
    )




@login_required
def increase_quantity(request, item_id):

    article = get_object_or_404(
        CartItem,
        id=item_id,
        panier__utilisateur=request.user
    )

    if article.quantite >= article.produit.stock:
        messages.warning(
            request,
            f"Stock maximum atteint pour « {article.produit.nom} »."
        )
        return redirect("cart_detail")

    article.quantite += 1
    article.save()


    return redirect("cart_detail")




@login_required
def decrease_quantity(request, item_id):

    article = get_object_or_404(
        CartItem,
        id=item_id,
        panier__utilisateur=request.user
    )


    if article.quantite > 1:
        article.quantite -= 1
        article.save()
    else:
        article.delete()
        messages.info(request, "Article retiré du panier.")


    return redirect("cart_detail")




@login_required
def remove_from_cart(request, item_id):

    article = get_object_or_404(
        CartItem,
        id=item_id,
        panier__utilisateur=request.user
    )


    article.delete()

    messages.info(request, "Article retiré du panier.")

    return redirect("cart_detail")