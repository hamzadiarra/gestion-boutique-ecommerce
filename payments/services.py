from django.db import transaction

from orders.services import BusinessRuleError
from .models import Payment


@transaction.atomic
def pay_order(commande, methode):
    methodes_valides = {code for code, _label in Payment.METHODES}
    if methode not in methodes_valides:
        raise BusinessRuleError("Méthode de paiement invalide.")

    paiement, created = Payment.objects.get_or_create(
        commande=commande,
        defaults={
            "montant": commande.total(),
            "methode": methode,
            "statut": "paye",
        },
    )

    if not created:
        if paiement.statut == "paye":
            return paiement
        paiement.montant = commande.total()
        paiement.methode = methode
        paiement.statut = "paye"
        paiement.save(update_fields=["montant", "methode", "statut"])

    commande.statut = "confirmee"
    commande.save(update_fields=["statut"])
    return paiement
