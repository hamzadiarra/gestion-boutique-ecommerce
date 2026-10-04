from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from orders.models import Order
from orders.services import BusinessRuleError
from .services import pay_order


@login_required
def payment_form(request, order_id):

    commande = get_object_or_404(
        Order,
        id=order_id,
        utilisateur=request.user
    )


    if request.method == "POST":

        methode = request.POST.get("methode")

        try:
            paiement = pay_order(commande, methode)
        except BusinessRuleError as exc:
            messages.error(request, str(exc))
            return redirect("payment_form", order_id=commande.id)


        return render(
            request,
            "payments/payment_success.html",
            {
                "paiement": paiement
            }
        )


    return render(
        request,
        "payments/payment_form.html",
        {
            "commande": commande
        }
    )
