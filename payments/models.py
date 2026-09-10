import uuid

from django.db import models
from orders.models import Order


class Payment(models.Model):

    METHODES = [
        ("especes", "Espèces"),
        ("orange_money", "Orange Money"),
        ("wave", "Wave"),
        ("carte", "Carte bancaire"),
        ("moov_money", "Moov Money"),
    ]


    STATUTS = [
        ("en_attente", "En attente"),
        ("paye", "Payé"),
        ("echoue", "Échoué"),
        ("annule", "Annulé"),
    ]


    commande = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name="payment"
    )


    montant = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )


    methode = models.CharField(
        max_length=50,
        choices=METHODES
    )


    statut = models.CharField(
        max_length=20,
        choices=STATUTS,
        default="en_attente"
    )


    date_creation = models.DateTimeField(
        auto_now_add=True
    )

    reference = models.CharField(max_length=80, unique=True, blank=True, null=True, editable=False)
    date_paiement = models.DateTimeField(null=True, blank=True)


    def __str__(self):
        return f"Paiement commande {self.commande.id}"
