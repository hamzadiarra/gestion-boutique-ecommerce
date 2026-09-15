from django.utils.translation import gettext_lazy
from django.db import models
from django.contrib.auth.models import User
from products.models import Product


class Cart(models.Model):

    utilisateur = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="cart"
    )

    date_creation = models.DateTimeField(
        auto_now_add=True
    )


    class Meta:
        verbose_name = gettext_lazy("Panier")
        verbose_name_plural = gettext_lazy("Paniers")


    def total(self):
        return sum(
            item.sous_total()
            for item in self.items.all()
        )


    def __str__(self):
        return f"Panier de {self.utilisateur.username}"



class CartItem(models.Model):

    panier = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items"
    )

    produit = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )

    quantite = models.PositiveIntegerField(
        default=1
    )

    prix = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )


    class Meta:
        verbose_name = gettext_lazy("Article du panier")
        verbose_name_plural = gettext_lazy("Articles du panier")


    def sous_total(self):
        return self.quantite * self.prix


    def __str__(self):
        return f"{self.produit.nom} ({self.quantite})"