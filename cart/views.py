from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from products.models import Product
from .models import Cart, CartItem



from django.http import JsonResponse

@login_required
def add_to_cart(request, product_id):

    produit = get_object_or_404(
        Product,
        id=product_id,
        actif=True
    )

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('ajax') == '1'

    # Vérifier le stock
    if produit.stock <= 0:
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': f"« {produit.nom} » est en rupture de stock."})
        messages.warning(request, f"« {produit.nom} » est en rupture de stock.")
        return redirect("product_list")

    panier, created = Cart.objects.get_or_create(
        utilisateur=request.user
    )


    article, created = CartItem.objects.get_or_create(
        panier=panier,
        produit=produit,
        defaults={
            "prix": produit.prix_effectif,
            "quantite": 1
        }
    )


    if not created:
        if article.quantite >= produit.stock:
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': f"Stock maximum atteint pour « {produit.nom} »."})
            messages.warning(
                request,
                f"Stock maximum atteint pour « {produit.nom} » ({produit.stock} disponibles)."
            )
            return redirect("cart_detail")

        article.quantite += 1
        article.save()

    cart_count = sum(item.quantite for item in panier.items.all())

    if is_ajax:
        return JsonResponse({
            'status': 'success', 
            'message': f"« {produit.nom} » ajouté au panier ! 🛒",
            'cart_count': cart_count
        })

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
