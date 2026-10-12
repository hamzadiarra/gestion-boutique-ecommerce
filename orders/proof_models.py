from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from .delivery_models import Livraison, TraceModel


class PreuveLivraison(TraceModel):
    livraison = models.OneToOneField(Livraison, on_delete=models.PROTECT, related_name="preuve")
    livreur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="preuves_remises")
    receptionnaire = models.CharField(max_length=150)
    # Database-only storage: no FileField, media URL or public object key.
    signature = models.BinaryField(null=True, blank=True, editable=False)
    empreinte = models.CharField(max_length=64, blank=True)
    exceptionnelle = models.BooleanField(default=False)
    autorisee_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="preuves_autorisees")
    motif = models.CharField(max_length=1000, blank=True)
    expire_at = models.DateTimeField()
    purged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=(
            models.Q(exceptionnelle=True, autorisee_par__isnull=False, signature__isnull=True)
            | models.Q(exceptionnelle=False, autorisee_par__isnull=True)), name="preuve_exception_autorisee")]


class DemandeDerogation(TraceModel):
    livraison = models.ForeignKey(Livraison, on_delete=models.PROTECT, related_name="derogations")
    livreur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    receptionnaire = models.CharField(max_length=150)
    motif = models.CharField(max_length=1000)
    decision = models.CharField(max_length=10, default="attente", choices=[("attente", "En attente"), ("accordee", "Accordée"), ("refusee", "Refusée")])
    administrateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="derogations_traitees")
    motif_decision = models.CharField(max_length=1000, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["livraison"], condition=models.Q(decision="attente"), name="une_derogation_en_attente")]


class RetourLivraison(TraceModel):
    livraison = models.ForeignKey(Livraison, on_delete=models.PROTECT, related_name="retours")
    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    type = models.CharField(max_length=12, choices=[("confirmation", "Réception confirmée"), ("probleme", "Problème signalé")])
    note = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    commentaire = models.CharField(max_length=1000, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["livraison", "type"], name="retour_unique_type"),
            models.CheckConstraint(condition=models.Q(note__isnull=True) | models.Q(note__range=(1, 5)), name="retour_note_valide"),
            models.CheckConstraint(condition=models.Q(type__in=["confirmation", "probleme"]), name="retour_type_valide"),
        ]


class AccesPreuve(TraceModel):
    preuve = models.ForeignKey(PreuveLivraison, on_delete=models.PROTECT, related_name="acces")
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
