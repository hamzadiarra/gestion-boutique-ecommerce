from django.db import transaction
from django.utils import timezone

from cart.models import Cart
from .models import Order, OrderItem


class BusinessRuleError(Exception):
    pass


@transaction.atomic
def create_order_from_cart(user, note=""):
    try:
        panier = Cart.objects.select_for_update().get(utilisateur=user)
    except Cart.DoesNotExist as exc:
        raise BusinessRuleError("Votre panier est vide.") from exc

    articles = list(
        panier.items.select_related("produit").select_for_update()
    )
    if not articles:
        raise BusinessRuleError("Votre panier est vide.")

    for article in articles:
        if article.quantite > article.produit.stock:
            raise BusinessRuleError(
                f"Stock insuffisant pour « {article.produit.nom} » "
                f"(disponible : {article.produit.stock}, demandé : {article.quantite})."
            )

    commande = Order.objects.create(
        utilisateur=user,
        note=note.strip() or None,
    )

    for article in articles:
        OrderItem.objects.create(
            commande=commande,
            produit=article.produit,
            quantite=article.quantite,
            prix=article.prix,
        )
        article.produit.stock -= article.quantite
        article.produit.quantite_vendue += article.quantite
        article.produit.save(update_fields=["stock", "quantite_vendue"])

    panier.items.all().delete()
    return commande


@transaction.atomic
def change_order_status(commande, action, user=None):
    if action == "confirmer":
        if commande.statut == "annulee":
            raise BusinessRuleError("Une commande annulée ne peut pas être confirmée.")
        commande.statut = "confirmee"
        commande.vendeur_confirmateur = user
        commande.date_confirmation = timezone.now()
        commande.save(update_fields=["statut", "vendeur_confirmateur", "date_confirmation"])
        return commande

    if action == "expediee":
        if commande.statut != "confirmee":
            raise BusinessRuleError("Seule une commande confirmée peut être expédiée.")
        commande.statut = "expediee"
        commande.save(update_fields=["statut"])
        return commande

    if action == "livree":
        if commande.statut != "expediee":
            raise BusinessRuleError("Seule une commande expédiée peut être livrée.")
        commande.statut = "livree"
        commande.save(update_fields=["statut"])
        return commande

    if action == "annuler":
        if commande.statut in ("expediee", "livree"):
            raise BusinessRuleError("Une commande expédiée ou livrée ne peut pas être annulée.")

        if commande.statut != "annulee":
            for item in commande.items.select_related("produit"):
                item.produit.stock += item.quantite
                item.produit.quantite_vendue = max(
                    0,
                    item.produit.quantite_vendue - item.quantite,
                )
                item.produit.save(update_fields=["stock", "quantite_vendue"])

        commande.statut = "annulee"
        commande.save(update_fields=["statut"])
        return commande

    raise BusinessRuleError("Action non reconnue.")
