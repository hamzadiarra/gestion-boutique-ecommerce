from django.utils.translation import gettext_lazy
"""Daily observations, deliberately independent from financial movements."""
import uuid
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q, F
from django.db.models.functions import Round
from django.utils import timezone

from .depense_files import PrivateExpenseStorage, validate_justificatif
from .finance_models import ImmutableQuerySet


def cloture_upload_to(instance, filename):
    return f"clotures/justificatifs/{timezone.localdate():%Y/%m}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class ClotureFinanciere(models.Model):
    STATUTS = [("brouillon", gettext_lazy("Brouillon")), ("validee", gettext_lazy("Validée")), ("annulee", gettext_lazy("Annulée"))]
    reference = models.CharField(max_length=45, unique=True, editable=False)
    compte = models.ForeignKey("dashboard.CompteFinancier", on_delete=models.PROTECT, related_name="clotures")
    date_cloture = models.DateField(default=timezone.localdate)
    solde_theorique = models.DecimalField(max_digits=24, decimal_places=2, default=Decimal("0"), editable=False)
    solde_constate = models.DecimalField(max_digits=24, decimal_places=2)
    ecart = models.DecimalField(max_digits=24, decimal_places=2, default=Decimal("0"), editable=False)
    solde_initial_snapshot = models.DecimalField(max_digits=24, decimal_places=2, default=Decimal("0"), editable=False)
    total_entrees = models.DecimalField(max_digits=24, decimal_places=2, default=Decimal("0"), editable=False)
    total_sorties = models.DecimalField(max_digits=24, decimal_places=2, default=Decimal("0"), editable=False)
    nombre_mouvements = models.PositiveIntegerField(default=0, editable=False)
    devise = models.CharField(max_length=12, editable=False)
    statut = models.CharField(max_length=12, choices=STATUTS, default="brouillon", editable=False)
    commentaire = models.TextField(blank=True)
    justificatif = models.FileField(storage=PrivateExpenseStorage(), upload_to=cloture_upload_to, validators=[validate_justificatif], blank=True, max_length=255)
    cree_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="clotures_creees", editable=False)
    validee_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="clotures_validees", null=True, blank=True, editable=False)
    date_validation = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = ImmutableQuerySet.as_manager()

    class Meta:
        ordering = ["-date_cloture", "-pk"]
        constraints = [
            models.UniqueConstraint(fields=["compte", "date_cloture"], condition=Q(statut="validee"), name="cloture_unique_validee_compte_date"),
            models.CheckConstraint(condition=Q(ecart=Round(F("solde_constate") - F("solde_theorique"), 2)), name="cloture_ecart_coherent"),
            models.CheckConstraint(condition=(Q(statut="brouillon", date_validation__isnull=True, validee_par__isnull=True) | Q(statut__in=["validee", "annulee"], date_validation__isnull=False, validee_par__isnull=False)), name="cloture_validation_coherente"),
        ]
        indexes = [models.Index(fields=["date_cloture", "statut"], name="cloture_date_statut_idx")]

    def __str__(self):
        return self.reference

    def clean(self):
        super().clean()
        if self.date_cloture and self.date_cloture > timezone.localdate():
            raise ValidationError({"date_cloture": gettext_lazy("Une clôture ne peut pas être datée dans le futur.")})

    def save(self, *args, **kwargs):
        from .cloture_services import snapshot_a_date
        with transaction.atomic():
            creating = self._state.adding
            if creating:
                self.reference = f"TMP-{uuid.uuid4().hex}"
                self.statut = "brouillon"
                self.validee_par = None
                self.date_validation = None
            else:
                original = type(self).objects.select_for_update().get(pk=self.pk)
                if original.statut != "brouillon" or self.statut != "brouillon":
                    raise ValidationError(gettext_lazy("Seul un brouillon est modifiable."))
                if self.reference != original.reference or self.cree_par_id != original.cree_par_id:
                    raise ValidationError(gettext_lazy("Référence et créateur non modifiables."))
            # Validate user input before any arithmetic (NaN/Infinity included).
            self._meta.get_field("solde_constate").clean(self.solde_constate, self)
            self.solde_constate = Decimal(str(self.solde_constate))
            self.clean()
            for field, value in snapshot_a_date(self.compte, self.date_cloture).items():
                setattr(self, field, value)
            self.ecart = self.solde_constate - self.solde_theorique
            self.full_clean()
            kwargs.pop("update_fields", None)  # Snapshot fields must be saved together.
            super().save(*args, **kwargs)
            if creating:
                self.reference = f"CLO-{timezone.localtime(self.created_at).year}-{self.pk:06d}"
                models.QuerySet(model=type(self), using=self._state.db).filter(pk=self.pk).update(reference=self.reference)

    def delete(self, *args, **kwargs):
        raise ValidationError(gettext_lazy("Une clôture reste dans l'historique ; aucune suppression."))

    @property
    def ecart_label(self):
        if self.ecart > 0:
            return "Excédent constaté"
        if self.ecart < 0:
            return "Manquant constaté"
        return "Conforme"
