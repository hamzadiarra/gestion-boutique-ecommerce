from django.db import models
from django.contrib.auth.models import User
from products.models import Product


class Review(models.Model):
    produit = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="reviews"
    )

    utilisateur = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="reviews"
    )

    note = models.PositiveIntegerField(
        default=5,
        choices=[(i, f"{i} ★") for i in range(1, 6)]
    )

    commentaire = models.TextField()

    date_creation = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        verbose_name = "Avis"
        verbose_name_plural = "Avis"
        ordering = ["-date_creation"]

    def __str__(self):
        return f"Avis de {self.utilisateur.username} sur {self.produit.nom} ({self.note} ★)"
