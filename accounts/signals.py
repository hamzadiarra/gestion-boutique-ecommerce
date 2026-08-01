from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User

from .models import Profile


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    """Crée un profil uniquement lors de la création d'un nouvel utilisateur."""
    if created:
        Profile.objects.get_or_create(utilisateur=instance)


# NOTE: On ne re-sauvegarde PAS automatiquement le profil à chaque save() de User
# car cela écraserait les modifications de rôle faites par l'administrateur.