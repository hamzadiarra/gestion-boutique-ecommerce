from django.shortcuts import redirect, render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .models import Order
from .services import BusinessRuleError, create_order_from_cart


@login_required
def create_order(request):
    if request.method != "POST":
        return redirect("cart_detail")

    note = request.POST.get("note", "")
    try:
        commande = create_order_from_cart(request.user, note=note)
    except BusinessRuleError as exc:
        messages.warning(request, str(exc))
        return redirect("cart_detail")

    messages.success(request, f"Commande #{commande.id} créée avec succès.")

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
