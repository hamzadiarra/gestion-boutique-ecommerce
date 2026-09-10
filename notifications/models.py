from django.db import models
from django.contrib.auth.models import User


class Notification(models.Model):
    TYPE_CHOICES = [
        ("commande", "Commande"),
        ("paiement", "Paiement"),
        ("livraison", "Livraison"),
        ("stock", "Stock"),
        ("compte", "Compte"),
        ("information", "Information"),
    ]
    utilisateur = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications"
    )

    message = models.TextField()

    titre = models.CharField(max_length=160, default="Information")

    type_notification = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default="information",
    )

    lien = models.CharField(max_length=255, blank=True, default="")

    lu = models.BooleanField(
        default=False
    )

    date_creation = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ["-date_creation"]

    def __str__(self):
        return f"Notification pour {self.utilisateur.username} : {self.titre}"
