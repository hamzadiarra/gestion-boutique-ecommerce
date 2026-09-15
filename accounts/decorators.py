from django.utils.translation import gettext
from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps


def livreur_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        if request.user.is_active and getattr(getattr(request.user, "profile", None), "role", None) == "livreur":
            return view_func(request, *args, **kwargs)
        return redirect("home")
    return wrapped


def role_required(role, redirect_url='home'):
    """
    Décorateur générique pour vérifier le rôle de l'utilisateur.
    Redirige avec un message d'erreur si le rôle ne correspond pas.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.warning(request, gettext("Veuillez vous connecter pour accéder à cette page."))
                return redirect('login')

            profile = getattr(request.user, 'profile', None)

            if profile is None:
                messages.error(request, gettext("Profil introuvable. Veuillez contacter l'administrateur."))
                return redirect(redirect_url)

            # Les superusers ont accès à tout
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            if profile.role != role:
                messages.error(
                    request,
                    gettext("⛔ Accès refusé — Vous n'avez pas les permissions nécessaires pour accéder à cette page.")
                )
                return redirect(redirect_url)

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def admin_required(view_func):
    """Seuls les administrateurs (et superusers) peuvent accéder."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, gettext("Veuillez vous connecter."))
            return redirect('login')

        profile = getattr(request.user, 'profile', None)

        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)

        if profile and profile.role == 'admin':
            return view_func(request, *args, **kwargs)

        messages.error(request, gettext("⛔ Accès refusé — Espace réservé aux administrateurs."))
        return redirect('home')
    return _wrapped_view


def vendeur_required(view_func):
    """Seuls les vendeurs et administrateurs peuvent accéder."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, gettext("Veuillez vous connecter."))
            return redirect('login')

        profile = getattr(request.user, 'profile', None)

        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)

        if profile and profile.role in ('vendeur', 'admin'):
            return view_func(request, *args, **kwargs)

        messages.error(request, gettext("⛔ Accès refusé — Espace réservé aux vendeurs."))
        return redirect('home')
    return _wrapped_view


def client_required(view_func):
    """Seuls les clients et administrateurs peuvent accéder."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, gettext("Veuillez vous connecter."))
            return redirect('login')

        profile = getattr(request.user, 'profile', None)

        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)

        if profile and profile.role in ('client', 'admin'):
            return view_func(request, *args, **kwargs)

        messages.error(request, gettext("⛔ Accès refusé — Espace réservé aux clients."))
        return redirect('home')
    return _wrapped_view


def comptable_required(view_func):
    """Seuls les comptables et administrateurs peuvent accéder."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, gettext("Veuillez vous connecter."))
            return redirect('login')

        profile = getattr(request.user, 'profile', None)

        # is_staff donne seulement accès à l'interface Django Admin. Il ne
        # doit pas ouvrir l'espace financier métier.
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)

        if profile and profile.role in ('comptable', 'admin'):
            return view_func(request, *args, **kwargs)

        messages.error(request, gettext("⛔ Accès refusé — Espace réservé aux comptables."))
        return redirect('home')
    return _wrapped_view

