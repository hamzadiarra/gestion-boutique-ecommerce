from django.utils.translation import gettext_lazy
import uuid

from django.db import models, transaction
from orders.models import Order


class Payment(models.Model):

    METHODES = [
        ("especes", gettext_lazy("Espèces")),
        ("orange_money", gettext_lazy("Orange Money")),
        ("wave", gettext_lazy("Wave")),
        ("carte", gettext_lazy("Carte bancaire")),
        ("moov_money", gettext_lazy("Moov Money")),
        ("online", gettext_lazy("Paiement en ligne")),
    ]


    STATUTS = [
        ("en_attente", gettext_lazy("En attente")),
        ("paye", gettext_lazy("Payé")),
        ("echoue", gettext_lazy("Échoué")),
        ("annule", gettext_lazy("Annulé")),
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
    provider = models.CharField(max_length=40, blank=True, default="")
    provider_reference = models.CharField(max_length=120, blank=True, default="")
    provider_status = models.CharField(max_length=40, blank=True, default="")
    provider_payload = models.JSONField(null=True, blank=True)
    date_confirmation = models.DateTimeField(null=True, blank=True)


    def save(self, *args, **kwargs):
        with transaction.atomic():
            previous = type(self).objects.select_for_update().filter(pk=self.pk).values_list("statut", flat=True).first() if self.pk else None
            super().save(*args, **kwargs)
            fields = kwargs.get("update_fields")
            if self.statut == "paye" and previous != "paye" and (fields is None or "statut" in fields):
                from dashboard.finance_services import enregistrer_paiement
                enregistrer_paiement(self)

    def __str__(self):
        return f"Paiement commande {self.commande.id}"
