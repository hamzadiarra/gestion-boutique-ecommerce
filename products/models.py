from django.utils.translation import gettext_lazy, get_language
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
    nom_en = models.CharField(max_length=200, blank=True, default="")
    slug = models.SlugField(unique=True, blank=True)

    description = models.TextField(blank=True, null=True)
    description_en = models.TextField(blank=True, default="")

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
        verbose_name = gettext_lazy("Produit")
        verbose_name_plural = gettext_lazy("Produits")

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nom)
        super().save(*args, **kwargs)

    @property
    def image_is_product(self):
        """N'autorise que les images stockées dans l'espace produit."""
        return bool(self.image and self.image.name.replace('\\', '/').startswith('products/'))

    @property
    def localized_name(self):
        return self.nom_en.strip() if get_language() == "en" and self.nom_en.strip() else self.nom

    @property
    def localized_description(self):
        if get_language() == "en" and self.description_en.strip():
            return self.description_en
        return self.description

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
        verbose_name = gettext_lazy("Liste de souhaits")
        verbose_name_plural = gettext_lazy("Listes de souhaits")

    def __str__(self):
        return f"Wishlist de {self.utilisateur.username}"
