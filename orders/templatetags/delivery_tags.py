from django import template
from orders.models import Livraison
from orders.delivery_permissions import peut_gerer_livraison, peut_acceder_livraison
from orders.delivery_services import avec_non_lus

register = template.Library()


@register.inclusion_tag("orders/delivery/_summary.html", takes_context=True)
def delivery_summary(context, commande):
    user = context["request"].user
    delivery = avec_non_lus(Livraison.objects.filter(commande=commande).select_related("livreur", "commande"), user).first()
    if delivery and not peut_acceder_livraison(user, delivery):
        return {}
    return {"commande": commande, "livraison": delivery, "gerer": peut_gerer_livraison(user), "csrf_token": context.get("csrf_token")}
