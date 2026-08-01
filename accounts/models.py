from django.db import models
from django.contrib.auth.models import User


class Profile(models.Model):

    ROLE_CHOICES = [
        ('admin', 'Administrateur'),
        ('client', 'Client'),
        ('vendeur', 'Vendeur'),
        ('comptable', 'Comptable'),
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
        verbose_name="Rôle"
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

        verbose_name = "Profil utilisateur"
        verbose_name_plural = "Profils utilisateurs"


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