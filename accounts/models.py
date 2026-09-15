from django.utils.translation import gettext_lazy
from django.db import models
from django.contrib.auth.models import User


class Profile(models.Model):

    ROLE_CHOICES = [
        ('admin', gettext_lazy('Administrateur')),
        ('client', gettext_lazy('Client')),
        ('vendeur', gettext_lazy('Vendeur')),
        ('comptable', gettext_lazy('Comptable')),
        ('livreur', gettext_lazy('Livreur')),
    ]

    utilisateur = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile"
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='client',
        verbose_name=gettext_lazy("Rôle")
    )

    telephone = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    adresse = models.TextField(
        blank=True,
        null=True
    )

    ville = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    code_postal = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    date_naissance = models.DateField(
        blank=True,
        null=True,
        verbose_name=gettext_lazy("Date de naissance")
    )

    lieu_naissance = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name=gettext_lazy("Lieu de naissance")
    )

    GENRE_CHOICES = [
        ("homme", gettext_lazy("Homme")),
        ("femme", gettext_lazy("Femme")),
        ("non_precise", gettext_lazy("Préfère ne pas préciser")),
    ]

    genre = models.CharField(
        max_length=20,
        choices=GENRE_CHOICES,
        blank=True,
        null=True,
        verbose_name=gettext_lazy("Genre")
    )

    photo = models.ImageField(
        upload_to="profiles/",
        blank=True,
        null=True
    )

    date_creation = models.DateTimeField(
        auto_now_add=True
    )

    date_modification = models.DateTimeField(
        auto_now=True
    )


    class Meta:

        verbose_name = gettext_lazy("Profil utilisateur")
        verbose_name_plural = gettext_lazy("Profils utilisateurs")


    def __str__(self):

        return f"{self.utilisateur.username} ({self.get_role_display()})"

    @property
    def is_admin(self):
        return self.role == 'admin' or self.utilisateur.is_superuser

    @property
    def is_vendeur(self):
        return self.role == 'vendeur'

    @property
    def is_client(self):
        return self.role == 'client'

    @property
    def is_comptable(self):
        return self.role == 'comptable'
