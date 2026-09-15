from django.utils.translation import gettext_lazy
from django.db import models, transaction
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth.models import User
from products.models import Product


class Order(models.Model):

    STATUT_CHOICES = [
        ('en_attente', gettext_lazy('En attente')),
        ('confirmee', gettext_lazy('Confirmée')),
        ('expediee', gettext_lazy('Expédiée')),
        ('livree', gettext_lazy('Livrée')),
        ('annulee', gettext_lazy('Annulée')),
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
    numero_rue = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(1000)])
    numero_porte = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(1000)])
    telephone_livraison = models.CharField(max_length=20, blank=True, default="")
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
        verbose_name=gettext_lazy("Vendeur confirmateur")
    )

    date_confirmation = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=gettext_lazy("Date de confirmation")
    )

    date_expedition = models.DateTimeField(null=True, blank=True)
    date_livraison = models.DateTimeField(null=True, blank=True)
    date_annulation = models.DateTimeField(null=True, blank=True)


    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(numero_rue__isnull=True) | models.Q(numero_rue__range=(0, 1000)), name="order_rue_range"),
            models.CheckConstraint(condition=models.Q(numero_porte__isnull=True) | models.Q(numero_porte__range=(0, 1000)), name="order_porte_range"),
        ]

    @property
    def rue_porte(self):
        return " · ".join(f"{label} {value}" for label, value in (("Rue", self.numero_rue), ("Porte", self.numero_porte)) if value is not None)

    @property
    def repere(self):
        return self.code_postal_livraison or ""

    @property
    def est_livrable(self):
        return self.mode_livraison in {"standard", "express"} and bool(self.adresse_livraison and self.ville_livraison)

    @property
    def telephone_appel(self):
        return "".join(c for c in self.telephone_livraison if c in "+0123456789")

    def save(self, *args, **kwargs):
        for field in ("numero_rue", "numero_porte"):
            setattr(self, field, self._meta.get_field(field).clean(getattr(self, field), self))
        with transaction.atomic():
            super().save(*args, **kwargs)
            fields = kwargs.get("update_fields")
            if self.statut == "annulee" and (fields is None or "statut" in fields):
                from .delivery_services import annuler_pour_commande
                annuler_pour_commande(self, getattr(self, "_delivery_actor", None))

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


from .delivery_models import Livraison, HistoriqueLivraison, MessageLivraison, LectureLivraison  # noqa: E402,F401
