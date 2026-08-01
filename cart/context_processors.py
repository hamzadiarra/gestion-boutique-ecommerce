from .models import Cart

def cart_processor(request):
    if request.user.is_authenticated:
        try:
            # Récupérer le panier de l'utilisateur s'il existe
            panier = getattr(request.user, 'cart', None)
            if panier:
                # Somme des quantités de tous les articles dans le panier
                count = sum(item.quantite for item in panier.items.all())
            else:
                count = 0
        except Exception:
            count = 0
        return {"cart_items_count": count}
    return {"cart_items_count": 0}
