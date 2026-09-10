from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.http import url_has_allowed_host_and_scheme

from .models import Profile
from .forms import ProfileForm
from orders.models import Order
from products.models import Wishlist


# ==========================
# INSCRIPTION
# ==========================

def register(request):

    if request.method == "POST":

        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        password1 = request.POST.get("password1", "")
        password2 = request.POST.get("password2", "")
        telephone = request.POST.get("telephone", "").strip()
        role = request.POST.get("role", "client").strip()

        # Sécurité : seuls client et vendeur sont autorisés à l'inscription
        if role not in ('client', 'vendeur'):
            role = 'client'

        # Contexte à retransmettre en cas d'erreur (pour ne pas vider le formulaire)
        form_data = {
            "username": username,
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "telephone": telephone,
            "selected_role": role,
        }

        def render_error(msg):
            return render(request, "accounts/register.html", {"error": msg, **form_data})

        # Validation des champs obligatoires
        if not username:
            return render_error("Le nom d'utilisateur est obligatoire.")

        if not email:
            return render_error("L'adresse e-mail est obligatoire.")

        if not password1:
            return render_error("Le mot de passe est obligatoire.")

        # Vérifier que les mots de passe correspondent
        if password1 != password2:
            return render_error("Les mots de passe ne correspondent pas.")

        # Vérifier la longueur du mot de passe
        if len(password1) < 6:
            return render_error("Le mot de passe doit contenir au moins 6 caractères.")

        # Vérifier si le nom d'utilisateur existe déjà
        if User.objects.filter(username=username).exists():
            return render_error("Ce nom d'utilisateur est déjà pris.")

        # Vérifier si l'email existe déjà
        if User.objects.filter(email=email).exists():
            return render_error("Cette adresse e-mail est déjà associée à un compte.")

        # Création de l'utilisateur
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password1,
            first_name=first_name,
            last_name=last_name,
        )

        # Le profil est créé automatiquement par le signal post_save
        profil, created = Profile.objects.get_or_create(utilisateur=user)
        profil.role = role
        photo = request.FILES.get("photo")
        if telephone:
            profil.telephone = telephone
        if photo:
            profil.photo = photo
        profil.save()

        # Connexion automatique
        login(request, user)

        role_label = profil.get_role_display()
        messages.success(request, f"Bienvenue {username} ! Votre compte {role_label} a été créé avec succès.")

        # Redirection selon le rôle
        if role == 'vendeur':
            return redirect("vendeur_dashboard")
        return redirect("profile")

    return render(request, "accounts/register.html")


# ==========================
# CONNEXION
# ==========================

def login_view(request):

    next_url = request.GET.get("next", "")

    if request.method == "POST":

        identifiant = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        remember_me = request.POST.get("remember_me") == "on"
        next_url = request.POST.get("next") or next_url

        username = identifiant
        if "@" in identifiant:
            user_by_email = User.objects.filter(email__iexact=identifiant).first()
            if user_by_email:
                username = user_by_email.username

        utilisateur = authenticate(
            request,
            username=username,
            password=password
        )

        if utilisateur is not None:

            login(request, utilisateur)
            if not remember_me:
                request.session.set_expiry(0)

            # Redirection selon le rôle
            if next_url and url_has_allowed_host_and_scheme(
                url=next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure()
            ):
                return redirect(next_url)

            profile = getattr(utilisateur, 'profile', None)
            if profile:
                if utilisateur.is_superuser or utilisateur.is_staff or profile.role == 'admin':
                    return redirect("admin_dashboard")
                elif profile.role == 'vendeur':
                    return redirect("vendeur_dashboard")
                elif profile.role == 'comptable':
                    return redirect("comptable_dashboard")

            return redirect("home")

        return render(
            request,
            "accounts/login.html",
            {
                "error": "Identifiant ou mot de passe incorrect.",
                "username": identifiant,
                "next": next_url,
                "remember_me": remember_me,
            }
        )

    return render(
        request,
        "accounts/login.html",
        {
            "next": next_url
        }
    )


# ==========================
# DECONNEXION
# ==========================

def logout_view(request):

    logout(request)
    messages.info(request, "Vous avez été déconnecté.")

    return redirect("home")


# ==========================
# PROFIL
# ==========================

@login_required
def profile_view(request):

    profil, created = Profile.objects.get_or_create(
        utilisateur=request.user
    )

    recent_orders = Order.objects.filter(utilisateur=request.user).order_by("-date_creation")[:3]
    return render(
        request,
        "accounts/profile.html",
        {
            "profil": profil,
            "recent_orders": recent_orders,
            "order_count": Order.objects.filter(utilisateur=request.user).count(),
            "wishlist_count": Wishlist.objects.filter(utilisateur=request.user).values("produits").count(),
        }
    )


# ==========================
# MODIFIER LE PROFIL
# ==========================

@login_required
def profile_edit(request):

    profil, created = Profile.objects.get_or_create(utilisateur=request.user)

    form = ProfileForm(request.POST or None, request.FILES or None, instance=profil)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Vos informations personnelles ont été mises à jour.")
        return redirect("profile")

    return render(request, "accounts/profile_edit.html", {"form": form})


# ==========================
# CHANGER LE MOT DE PASSE
# ==========================

@login_required
def change_password(request):

    if request.method == "POST":

        old_password = request.POST.get("old_password", "")
        new_password1 = request.POST.get("new_password1", "")
        new_password2 = request.POST.get("new_password2", "")

        if not request.user.check_password(old_password):
            messages.error(request, "L'ancien mot de passe est incorrect.")
            return render(request, "accounts/change_password.html")

        if new_password1 != new_password2:
            messages.error(request, "Les nouveaux mots de passe ne correspondent pas.")
            return render(request, "accounts/change_password.html")

        if len(new_password1) < 6:
            messages.error(request, "Le mot de passe doit contenir au moins 6 caractères.")
            return render(request, "accounts/change_password.html")

        request.user.set_password(new_password1)
        request.user.save()

        # Garder l'utilisateur connecté après le changement
        update_session_auth_hash(request, request.user)

        messages.success(request, "Votre mot de passe a été modifié avec succès.")

        return redirect("profile")

    return render(
        request,
        "accounts/change_password.html"
    )
