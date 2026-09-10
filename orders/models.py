from django.db import models
from django.contrib.auth.models import User
from products.models import Product


class Order(models.Model):

    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('confirmee', 'Confirmée'),
        ('expediee', 'Expédiée'),
        ('livree', 'Livrée'),
        ('annulee', 'Annulée'),
    ]

    utilisateur = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    date_creation = models.DateTimeField(
        auto_now_add=True
    )

    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='en_attente'
    )

    note = models.TextField(
        blank=True,
        null=True
    )

    adresse_livraison = models.TextField(blank=True, null=True)
    ville_livraison = models.CharField(max_length=100, blank=True, null=True)
    code_postal_livraison = models.CharField(max_length=20, blank=True, null=True)
    mode_livraison = models.CharField(max_length=30, default="standard")
    frais_livraison = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    vendeur_confirmateur = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commandes_confirmees",
        verbose_name="Vendeur confirmateur"
    )

    date_confirmation = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de confirmation"
    )

    date_expedition = models.DateTimeField(null=True, blank=True)
    date_livraison = models.DateTimeField(null=True, blank=True)
    date_annulation = models.DateTimeField(null=True, blank=True)


    def total(self):
        return sum(
            item.sous_total()
            for item in self.items.all()
        ) + self.frais_livraison


    def __str__(self):
        return f"Commande {self.id} - {self.utilisateur.username}"



class OrderItem(models.Model):

    commande = models.ForeignKey(
        Order,
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


    def sous_total(self):
        return self.quantite * self.prix


    def __str__(self):
        return self.produit.nom
