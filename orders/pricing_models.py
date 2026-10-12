from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator
from .delivery_models import TraceModel


class TarifLivreur(TraceModel):
    livreur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="tarifs_livraison")
    mode = models.CharField(max_length=10, choices=[("standard", "Standard"), ("express", "Express")])
    zone = models.CharField(max_length=100, blank=True, help_text="Ville exacte ; vide pour toutes les villes.")
    montant = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    statut = models.CharField(max_length=10, default="propose", choices=[("propose", "Proposé"), ("approuve", "Approuvé"), ("refuse", "Refusé"), ("desactive", "Désactivé")])

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.CheckConstraint(condition=models.Q(montant__gte=0), name="tarif_montant_positif"),
            models.CheckConstraint(condition=models.Q(mode__in=["standard", "express"]), name="tarif_mode_valide"),
            models.CheckConstraint(condition=models.Q(statut__in=["propose", "approuve", "refuse", "desactive"]), name="tarif_statut_valide"),
        ]


class HistoriqueTarif(TraceModel):
    tarif = models.ForeignKey(TarifLivreur, on_delete=models.PROTECT, related_name="historique")
    acteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    statut = models.CharField(max_length=10)
    motif = models.CharField(max_length=1000)
