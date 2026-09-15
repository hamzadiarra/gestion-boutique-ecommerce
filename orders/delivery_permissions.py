from django.utils.translation import gettext
from django.core.exceptions import PermissionDenied


def role(user):
    return getattr(getattr(user, "profile", None), "role", None)


def peut_gerer_livraison(user, livraison=None):
    # Existing seller workflow supervises all web orders, not only those confirmed
    # personally. is_staff alone grants no operational authorization.
    return user.is_authenticated and user.is_active and (user.is_superuser or role(user) in {"admin", "vendeur"})


def peut_acceder_livraison(user, livraison):
    return user.is_authenticated and user.is_active and (
        peut_gerer_livraison(user, livraison)
        or (role(user) == "client" and livraison.commande.utilisateur_id == user.pk)
        or (role(user) == "livreur" and livraison.livreur_id == user.pk))


def peut_ecrire_livraison(user, livraison):
    return peut_acceder_livraison(user, livraison) and not livraison.terminee and livraison.commande.statut != "annulee"


def exiger_acces(user, livraison):
    if not peut_acceder_livraison(user, livraison):
        raise PermissionDenied(gettext("Cette livraison ne vous est pas accessible."))
