from django.utils.translation import gettext_lazy
"""Financial ledger schema. All workflow writes go through finance_services."""
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Q, Sum, Max
from django.utils import timezone

TYPES_COMPTE = [("especes", gettext_lazy("Espèces")), ("orange_money", gettext_lazy("Orange Money")),
                ("wave", gettext_lazy("Wave")), ("moov_money", gettext_lazy("Moov Money")), ("banque", gettext_lazy("Banque"))]
SENS = [("entree", gettext_lazy("Entrée")), ("sortie", gettext_lazy("Sortie"))]
TYPES_MOUVEMENT = [(v, label) for v, label in (("vente", gettext_lazy("Vente")), ("paiement", gettext_lazy("Paiement")),
    ("depense", gettext_lazy("Dépense")), ("transfert", gettext_lazy("Transfert")), ("ajustement", gettext_lazy("Ajustement")), ("annulation", gettext_lazy("Annulation")))]


class CompteFinancier(models.Model):
    nom = models.CharField(max_length=160)
    type_compte = models.CharField(max_length=20, choices=TYPES_COMPTE)
    devise = models.CharField(max_length=12, default="FCFA")
    solde_initial = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    actif = models.BooleanField(default=True)
    est_par_defaut = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    cree_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="comptes_crees")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["type_compte", "nom", "pk"]
        constraints = [models.UniqueConstraint(fields=["type_compte"], condition=Q(actif=True, est_par_defaut=True), name="finance_default_active_type")]

    def __str__(self):
        return f"{self.nom} ({self.devise})"

    def clean(self):
        super().clean()
        self.devise = self.devise.strip().upper()
        if self.devise == "XOF":
            self.devise = "FCFA"
        if self.pk and self.mouvements.exists():
            previous = type(self).objects.get(pk=self.pk)
            for field in ("type_compte", "devise", "solde_initial"):
                if getattr(previous, field) != getattr(self, field):
                    raise ValidationError({field: gettext_lazy("Compte utilisé : utilisez un ajustement, pas une modification du solde initial.")})

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.pk:
                type(self).objects.select_for_update().get(pk=self.pk)
            self.full_clean()
            return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(gettext_lazy("Désactivez le compte ; aucune suppression financière."))

    @property
    def total_entrees(self):
        return self.mouvements.filter(sens="entree").aggregate(total=Sum("montant"))["total"] or Decimal("0")

    @property
    def total_sorties(self):
        return self.mouvements.filter(sens="sortie").aggregate(total=Sum("montant"))["total"] or Decimal("0")

    @property
    def solde_theorique(self):
        return self.solde_initial + self.total_entrees - self.total_sorties

    @classmethod
    def avec_soldes(cls):
        return cls.objects.annotate(
            entrees=Sum("mouvements__montant", filter=Q(mouvements__sens="entree"), default=Decimal("0")),
            sorties=Sum("mouvements__montant", filter=Q(mouvements__sens="sortie"), default=Decimal("0")),
            derniere_operation=Max("mouvements__date_mouvement"),
        ).annotate(solde=models.F("solde_initial") + models.F("entrees") - models.F("sorties"))


class ImmutableQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError(gettext_lazy("Journal immuable : utilisez un workflow financier explicite."))

    def delete(self):
        raise ValidationError(gettext_lazy("Aucune suppression du journal financier."))

    def bulk_create(self, *args, **kwargs):
        raise ValidationError(gettext_lazy("Utilisez le service financier pour conserver références et contraintes."))


class FinancialRecord(models.Model):
    reference = models.CharField(max_length=45, unique=True, editable=False)
    montant = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    cree_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    objects = ImmutableQuerySet.as_manager()
    reference_prefix = "MVT"

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(gettext_lazy("Enregistrement financier immuable."))
        with transaction.atomic():
            self.reference = f"TMP-{uuid.uuid4().hex}"
            self.full_clean()
            super().save(*args, **kwargs)
            self.reference = f"{self.reference_prefix}-{timezone.localtime(self.created_at).year}-{self.pk:06d}"
            models.QuerySet(model=type(self), using=self._state.db).filter(pk=self.pk).update(reference=self.reference)

    def delete(self, *args, **kwargs):
        raise ValidationError(gettext_lazy("Aucune suppression financière."))

    def __str__(self):
        return self.reference


class TransfertFinancier(FinancialRecord):
    reference_prefix = "TRF"
    compte_source = models.ForeignKey(CompteFinancier, on_delete=models.PROTECT, related_name="transferts_sortants")
    compte_destination = models.ForeignKey(CompteFinancier, on_delete=models.PROTECT, related_name="transferts_entrants")
    date_transfert = models.DateTimeField(default=timezone.now)
    motif = models.CharField(max_length=255)
    cle_operation = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    class Meta:
        ordering = ["-date_transfert", "-pk"]
        constraints = [models.CheckConstraint(condition=Q(montant__gt=0), name="transfert_montant_positif"),
                       models.CheckConstraint(condition=~Q(compte_source=models.F("compte_destination")), name="transfert_comptes_distincts")]

    def clean(self):
        super().clean()
        if self.compte_source_id and self.compte_destination_id:
            if self.compte_source.devise != self.compte_destination.devise:
                raise ValidationError(gettext_lazy("Transfert entre devises interdit : aucune conversion implicite."))
            if not self.compte_source.actif or not self.compte_destination.actif:
                raise ValidationError(gettext_lazy("Les deux comptes doivent être actifs."))


class MouvementFinancier(FinancialRecord):
    compte = models.ForeignKey(CompteFinancier, on_delete=models.PROTECT, null=True, blank=True, related_name="mouvements")
    sens = models.CharField(max_length=10, choices=SENS)
    type_mouvement = models.CharField(max_length=15, choices=TYPES_MOUVEMENT)
    date_mouvement = models.DateTimeField(default=timezone.now)
    libelle = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    type_compte_attendu = models.CharField(max_length=20, choices=TYPES_COMPTE)
    devise = models.CharField(max_length=12, default="FCFA")
    raison_regularisation = models.CharField(max_length=255, blank=True)
    vente = models.ForeignKey("dashboard.Vente", on_delete=models.PROTECT, null=True, blank=True, related_name="mouvements_financiers")
    paiement = models.ForeignKey("payments.Payment", on_delete=models.PROTECT, null=True, blank=True, related_name="mouvements_financiers")
    depense = models.ForeignKey("dashboard.Depense", on_delete=models.PROTECT, null=True, blank=True, related_name="mouvements_financiers")
    transfert = models.ForeignKey(TransfertFinancier, on_delete=models.PROTECT, null=True, blank=True, related_name="mouvements")
    cle_operation = models.UUIDField(null=True, blank=True, unique=True, editable=False)

    class Meta:
        ordering = ["-date_mouvement", "-pk"]
        indexes = [models.Index(fields=["compte", "date_mouvement"], name="finance_compte_date_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(montant__gt=0), name="mouvement_montant_positif"),
            models.CheckConstraint(condition=Q(sens__in=["entree", "sortie"]), name="mouvement_sens_valide"),
            models.UniqueConstraint(fields=["vente"], condition=Q(type_mouvement="vente"), name="mouvement_unique_vente"),
            models.UniqueConstraint(fields=["paiement"], condition=Q(type_mouvement="paiement"), name="mouvement_unique_paiement"),
            models.UniqueConstraint(fields=["depense"], condition=Q(type_mouvement="depense"), name="mouvement_unique_depense"),
            models.UniqueConstraint(fields=["depense"], condition=Q(type_mouvement="annulation"), name="mouvement_unique_annulation"),
            models.UniqueConstraint(fields=["transfert", "sens"], condition=Q(type_mouvement="transfert"), name="mouvement_unique_transfert_sens"),
            models.CheckConstraint(condition=(
                Q(type_mouvement="vente", sens="entree", vente__isnull=False, paiement__isnull=True, depense__isnull=True, transfert__isnull=True)
                | Q(type_mouvement="paiement", sens="entree", paiement__isnull=False, vente__isnull=True, depense__isnull=True, transfert__isnull=True)
                | Q(type_mouvement="depense", sens="sortie", depense__isnull=False, vente__isnull=True, paiement__isnull=True, transfert__isnull=True)
                | Q(type_mouvement="annulation", sens="entree", depense__isnull=False, vente__isnull=True, paiement__isnull=True, transfert__isnull=True)
                | Q(type_mouvement="transfert", transfert__isnull=False, compte__isnull=False, vente__isnull=True, paiement__isnull=True, depense__isnull=True)
                | Q(type_mouvement="ajustement", compte__isnull=False, vente__isnull=True, paiement__isnull=True, depense__isnull=True, transfert__isnull=True)
            ), name="mouvement_source_coherente"),
        ]

    def clean(self):
        super().clean()
        if self.compte_id and (self.compte.type_compte != self.type_compte_attendu or self.compte.devise != self.devise):
            raise ValidationError(gettext_lazy("Compte incompatible avec le type ou la devise du mouvement."))

    @property
    def source(self):
        for field, prefix in (("vente_id", "V"), ("paiement_id", "P"), ("depense_id", "DEP"), ("transfert_id", "TRF")):
            if getattr(self, field):
                return f"{prefix}-{getattr(self, field)}"
        return "Ajustement"
