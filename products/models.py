from django.db import models
from django.utils.text import slugify
from django.contrib.auth.models import User
from categories.models import Category


class Product(models.Model):
    categorie = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="products"
    )

    nom = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)

    description = models.TextField(blank=True, null=True)

    prix = models.DecimalField(
        max_digits=10,
        decimal_places=2
        
    )
    prix_promotion = models.DecimalField(
    max_digits=10,
    decimal_places=2,
    blank=True,
    null=True
)
    stock = models.PositiveIntegerField(default=0)

    quantite_vendue = models.PositiveIntegerField(default=0)
    
    image = models.ImageField(
        upload_to="products/",
        blank=True,
        null=True
    )

    marque = models.CharField(
        max_length=100,
        blank=True
    )

    actif = models.BooleanField(default=True)
    vedette = models.BooleanField(default=False)

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nom"]
        verbose_name = "Produit"
        verbose_name_plural = "Produits"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nom)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nom


class Wishlist(models.Model):
    utilisateur = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="wishlist"
    )
    produits = models.ManyToManyField(
        Product,
        related_name="wishlisted_by",
        blank=True
    )
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Liste de souhaits"
        verbose_name_plural = "Listes de souhaits"

    def __str__(self):
        return f"Wishlist de {self.utilisateur.username}"