from django.utils.translation import gettext_lazy
from django.db import models
from django.contrib.auth.models import User
from products.models import Product
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import transaction
from django.db.models import Q, Sum, Count
from django.utils import timezone
from .depense_files import PrivateExpenseStorage, justificatif_upload_to, validate_justificatif


class CategorieDepense(models.Model):
    nom = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nom"]
        verbose_name = gettext_lazy("Catégorie de dépense")
        verbose_name_plural = gettext_lazy("Catégories de dépenses")

    def __str__(self):
        return self.nom

    def save(self, *args, **kwargs):
        self.nom = self.nom.strip()
        self.full_clean()
        return super().save(*args, **kwargs)


class Depense(models.Model):
    MOYENS_PAIEMENT = [
        ("especes", gettext_lazy("Espèces")), ("orange_money", gettext_lazy("Orange Money")),
        ("wave", gettext_lazy("Wave")), ("moov_money", gettext_lazy("Moov Money")), ("carte", gettext_lazy("Carte / Banque")),
    ]
    STATUTS = [("brouillon", gettext_lazy("Brouillon")), ("validee", gettext_lazy("Validée")), ("annulee", gettext_lazy("Annulée"))]

    reference = models.CharField(max_length=40, unique=True, null=True, blank=True, editable=False)
    date_depense = models.DateField(default=timezone.localdate)
    categorie = models.ForeignKey(CategorieDepense, on_delete=models.PROTECT, related_name="depenses")
    libelle = models.CharField(max_length=200)
    montant = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    moyen_paiement = models.CharField(max_length=20, choices=MOYENS_PAIEMENT)
    beneficiaire = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    justificatif = models.FileField(
        upload_to=justificatif_upload_to, storage=PrivateExpenseStorage(),
        validators=[validate_justificatif], blank=True, max_length=255,
    )
    cree_par = models.ForeignKey(User, on_delete=models.PROTECT, related_name="depenses_creees", editable=False)
    statut = models.CharField(max_length=12, choices=STATUTS, default="brouillon", editable=False)
    date_validation = models.DateTimeField(null=True, blank=True, editable=False)
    validee_par = models.ForeignKey(User, on_delete=models.PROTECT, related_name="depenses_validees", null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_depense", "-id"]
        verbose_name = gettext_lazy("Dépense")
        verbose_name_plural = gettext_lazy("Dépenses")
        indexes = [models.Index(fields=["statut", "date_depense"], name="depense_statut_date_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(montant__gt=0), name="depense_montant_positif"),
            models.CheckConstraint(
                condition=(Q(statut="brouillon", date_validation__isnull=True, validee_par__isnull=True)
                           | Q(statut__in=["validee", "annulee"], date_validation__isnull=False, validee_par__isnull=False)),
                name="depense_validation_coherente",
            ),
        ]

    def __str__(self):
        return f"{self.reference or 'Brouillon'} - {self.libelle}"

    def save(self, *args, **kwargs):
        with transaction.atomic():
            creating = self._state.adding
            if creating:
                self.reference = None
                self.statut = "brouillon"
                self.validee_par = None
                self.date_validation = None
            else:
                original = type(self).objects.select_for_update().get(pk=self.pk)
                if original.statut != "brouillon" or self.statut != "brouillon":
                    raise ValidationError(gettext_lazy("Seul un brouillon est modifiable ; utilisez les actions de validation et d'annulation."))
                if self.reference != original.reference or self.cree_par_id != original.cree_par_id:
                    raise ValidationError(gettext_lazy("La référence et le créateur ne sont pas modifiables."))
            self.full_clean(exclude=["reference"] if creating else None)
            super().save(*args, **kwargs)
            if creating:
                self.reference = f"DEP-{timezone.localtime(self.created_at).year}-{self.pk:06d}"
                type(self).objects.filter(pk=self.pk).update(reference=self.reference)

    @classmethod
    def indicateurs(cls, today=None):
        today = today or timezone.localdate()
        validated = Q(statut="validee")
        data = cls.objects.aggregate(
            depenses_jour=Sum("montant", filter=validated & Q(date_depense=today)),
            depenses_mois=Sum("montant", filter=validated & Q(date_depense__range=(today.replace(day=1), today))),
            depenses_annee=Sum("montant", filter=validated & Q(date_depense__range=(today.replace(month=1, day=1), today))),
            nb_brouillons=Count("pk", filter=Q(statut="brouillon")),
            nb_annulees=Count("pk", filter=Q(statut="annulee")),
        )
        for key in ("depenses_jour", "depenses_mois", "depenses_annee"):
            data[key] = data[key] or Decimal("0")
        return data


class Vente(models.Model):
    """
    Enregistre chaque vente effectuée par un vendeur.
    Permet à l'administrateur de tracer toutes les transactions.
    """

    vendeur = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="ventes",
        verbose_name=gettext_lazy("Vendeur")
    )

    produit = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="ventes",
        verbose_name=gettext_lazy("Produit")
    )

    quantite = models.PositiveIntegerField(
        default=1,
        verbose_name=gettext_lazy("Quantité vendue")
    )

    prix_unitaire = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=gettext_lazy("Prix unitaire")
    )

    montant_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=gettext_lazy("Montant total")
    )

    methode_paiement = models.CharField(
        max_length=50,
        choices=[
            ("especes", gettext_lazy("Espèces")),
            ("orange_money", gettext_lazy("Orange Money")),
            ("wave", gettext_lazy("Wave")),
            ("moov_money", gettext_lazy("Moov Money")),
            ("carte", gettext_lazy("Carte bancaire")),
        ],
        default="especes",
        verbose_name=gettext_lazy("Méthode de paiement")
    )

    reference_client = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name=gettext_lazy("Nom du client")
    )

    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name=gettext_lazy("Notes")
    )

    date_vente = models.DateTimeField(
        auto_now_add=True,
        verbose_name=gettext_lazy("Date de vente")
    )

    class Meta:
        ordering = ["-date_vente"]
        verbose_name = gettext_lazy("Vente")
        verbose_name_plural = gettext_lazy("Ventes")

    def save(self, *args, **kwargs):
        with transaction.atomic():
            creating = self._state.adding
            super().save(*args, **kwargs)
            if creating:
                from .finance_services import enregistrer_vente
                enregistrer_vente(self)

    def __str__(self):
        return f"Vente #{self.id} — {self.produit.nom} x{self.quantite} par {self.vendeur.username}"


class BoutiqueSettings(models.Model):
    nom = models.CharField(max_length=160, default="Gestion Boutique")
    logo = models.ImageField(upload_to="boutique/", blank=True, null=True)
    telephone = models.CharField(max_length=40, blank=True)
    whatsapp = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    pays = models.CharField(max_length=80, default="Mali", blank=True)
    ville = models.CharField(max_length=120, blank=True)
    adresse = models.TextField(blank=True)
    nif = models.CharField(max_length=80, blank=True)
    rccm = models.CharField(max_length=80, blank=True)
    devise = models.CharField(max_length=12, default="FCFA")
    seuil_stock_faible = models.PositiveIntegerField(default=5)
    livraison_active = models.BooleanField(default=True)
    message_recu = models.CharField(max_length=255, default="Merci pour votre achat.")
    afficher_message_recu = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_solo(cls):
        return cls.objects.first() or cls.objects.create()


class JournalActivite(models.Model):
    """
    Journal d'activité pour tracer toutes les actions des vendeurs.
    Permet de détecter les anomalies et les tentatives de vol.
    """

    ACTION_CHOICES = [
        ("vente_creee", gettext_lazy("🛒 Vente enregistrée")),
        ("vente_modifiee", gettext_lazy("✏️ Vente modifiée")),
        ("vente_supprimee", gettext_lazy("🗑️ Vente supprimée")),
        ("connexion", gettext_lazy("🔑 Connexion")),
        ("deconnexion", gettext_lazy("🚪 Déconnexion")),
        ("stock_modifie", gettext_lazy("📦 Stock modifié")),
        ("prix_modifie", gettext_lazy("💰 Prix modifié")),
        ("acces_refuse", gettext_lazy("⛔ Accès refusé")),
        ("autre", gettext_lazy("📝 Autre action")),
    ]

    NIVEAU_CHOICES = [
        ("info", gettext_lazy("Information")),
        ("warning", gettext_lazy("Avertissement")),
        ("danger", gettext_lazy("Alerte critique")),
    ]

    utilisateur = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="journal_activites",
        verbose_name=gettext_lazy("Utilisateur")
    )

    action = models.CharField(
        max_length=50,
        choices=ACTION_CHOICES,
        verbose_name=gettext_lazy("Action")
    )

    niveau = models.CharField(
        max_length=20,
        choices=NIVEAU_CHOICES,
        default="info",
        verbose_name=gettext_lazy("Niveau d'alerte")
    )

    details = models.TextField(
        verbose_name=gettext_lazy("Détails de l'action")
    )

    adresse_ip = models.GenericIPAddressField(
        blank=True,
        null=True,
        verbose_name=gettext_lazy("Adresse IP")
    )

    date = models.DateTimeField(
        auto_now_add=True,
        verbose_name=gettext_lazy("Date")
    )

    class Meta:
        ordering = ["-date"]
        verbose_name = gettext_lazy("Journal d'activité")
        verbose_name_plural = gettext_lazy("Journal des activités")

    def __str__(self):
        return f"[{self.get_action_display()}] {self.utilisateur.username} — {self.date.strftime('%d/%m/%Y %H:%M')}"


def log_activity(user, action, details, request=None, niveau="info"):
    """Fonction utilitaire pour enregistrer une activité dans le journal."""
    ip = None
    if request:
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded:
            ip = x_forwarded.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')

    JournalActivite.objects.create(
        utilisateur=user,
        action=action,
        details=details,
        adresse_ip=ip,
        niveau=niveau,
    )


from .finance_models import CompteFinancier, MouvementFinancier, TransfertFinancier  # noqa: E402,F401
from .cloture_models import ClotureFinanciere  # noqa: E402,F401
