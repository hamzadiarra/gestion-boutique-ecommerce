from django.db import models
from django.contrib.auth.models import User
from products.models import Product


class Vente(models.Model):
    """
    Enregistre chaque vente effectuée par un vendeur.
    Permet à l'administrateur de tracer toutes les transactions.
    """

    vendeur = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="ventes",
        verbose_name="Vendeur"
    )

    produit = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="ventes",
        verbose_name="Produit"
    )

    quantite = models.PositiveIntegerField(
        default=1,
        verbose_name="Quantité vendue"
    )

    prix_unitaire = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Prix unitaire"
    )

    montant_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Montant total"
    )

    methode_paiement = models.CharField(
        max_length=50,
        choices=[
            ("especes", "Espèces"),
            ("orange_money", "Orange Money"),
            ("wave", "Wave"),
            ("carte", "Carte bancaire"),
        ],
        default="especes",
        verbose_name="Méthode de paiement"
    )

    reference_client = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name="Nom du client"
    )

    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name="Notes"
    )

    date_vente = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de vente"
    )

    class Meta:
        ordering = ["-date_vente"]
        verbose_name = "Vente"
        verbose_name_plural = "Ventes"

    def __str__(self):
        return f"Vente #{self.id} — {self.produit.nom} x{self.quantite} par {self.vendeur.username}"


class JournalActivite(models.Model):
    """
    Journal d'activité pour tracer toutes les actions des vendeurs.
    Permet de détecter les anomalies et les tentatives de vol.
    """

    ACTION_CHOICES = [
        ("vente_creee", "🛒 Vente enregistrée"),
        ("vente_modifiee", "✏️ Vente modifiée"),
        ("vente_supprimee", "🗑️ Vente supprimée"),
        ("connexion", "🔑 Connexion"),
        ("deconnexion", "🚪 Déconnexion"),
        ("stock_modifie", "📦 Stock modifié"),
        ("prix_modifie", "💰 Prix modifié"),
        ("acces_refuse", "⛔ Accès refusé"),
        ("autre", "📝 Autre action"),
    ]

    NIVEAU_CHOICES = [
        ("info", "Information"),
        ("warning", "Avertissement"),
        ("danger", "Alerte critique"),
    ]

    utilisateur = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="journal_activites",
        verbose_name="Utilisateur"
    )

    action = models.CharField(
        max_length=50,
        choices=ACTION_CHOICES,
        verbose_name="Action"
    )

    niveau = models.CharField(
        max_length=20,
        choices=NIVEAU_CHOICES,
        default="info",
        verbose_name="Niveau d'alerte"
    )

    details = models.TextField(
        verbose_name="Détails de l'action"
    )

    adresse_ip = models.GenericIPAddressField(
        blank=True,
        null=True,
        verbose_name="Adresse IP"
    )

    date = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date"
    )

    class Meta:
        ordering = ["-date"]
        verbose_name = "Journal d'activité"
        verbose_name_plural = "Journal des activités"

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
