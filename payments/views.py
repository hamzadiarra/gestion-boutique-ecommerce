import uuid

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from orders.models import Order
from .models import Payment


@login_required
def payment_form(request, order_id):
    commande = get_object_or_404(Order, id=order_id, utilisateur=request.user)
    paiement = getattr(commande, "payment", None)

    if paiement and paiement.statut == "paye":
        return render(request, "payments/payment_success.html", {"paiement": paiement, "already_paid": True})
    if commande.statut == "annulee":
        return render(request, "payments/payment_result.html", {"commande": commande, "status": "annule", "message": "Cette commande a été annulée et ne peut plus être payée."})

    if request.method == "POST":
        methode = request.POST.get("methode")
        result = request.POST.get("simulation_result", "paye")
        if methode not in dict(Payment.METHODES):
            return render(request, "payments/payment_form.html", {"commande": commande, "errors": ["Choisissez un moyen de paiement valide."]})
        if result not in {"paye", "echoue", "annule"}:
            result = "paye"

        if paiement is None:
            paiement = Payment.objects.create(commande=commande, montant=commande.total(), methode=methode, statut=result, reference=f"SIM-{uuid.uuid4().hex[:12].upper()}")
        else:
            paiement.methode = methode
            paiement.montant = commande.total()
            paiement.statut = result
        if result == "paye":
            paiement.date_paiement = timezone.now()
            commande.statut = "confirmee"
            commande.save(update_fields=["statut"])
        paiement.save()
        if result == "paye":
            return render(request, "payments/payment_success.html", {"paiement": paiement})
        return render(request, "payments/payment_result.html", {"paiement": paiement, "commande": commande, "status": result})

    return render(request, "payments/payment_form.html", {"commande": commande, "paiement": paiement})
