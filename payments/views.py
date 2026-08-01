from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required

from orders.models import Order
from .models import Payment


@login_required
def payment_form(request, order_id):

    commande = get_object_or_404(
        Order,
        id=order_id,
        utilisateur=request.user
    )


    if request.method == "POST":

        methode = request.POST.get("methode")


        paiement = Payment.objects.create(
            commande=commande,
            montant=commande.total(),
            methode=methode,
            statut="paye"
        )


        commande.statut = "confirmee"
        commande.save()


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