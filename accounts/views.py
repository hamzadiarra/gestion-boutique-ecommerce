from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .models import Profile
from .forms import ProfileForm


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
        messages.success(request, f"Bienvenue {username} ! Votre compte {role_label} a été créé avec succès. 🎉")

        # Redirection selon le rôle
        if role == 'vendeur':
            return redirect("vendeur_dashboard")
        return redirect("profile")

    return render(request, "accounts/register.html")


# ==========================
# CONNEXION
# ==========================

def login_view(request):

    if request.method == "POST":

        username = request.POST.get("username")
        password = request.POST.get("password")

        utilisateur = authenticate(
            request,
            username=username,
            password=password
        )

        if utilisateur is not None:

            login(request, utilisateur)

            # Redirection selon le rôle
            next_url = request.GET.get("next")
            if next_url:
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
                "error": "Nom d'utilisateur ou mot de passe incorrect."
            }
        )

    return render(
        request,
        "accounts/login.html"
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

    return render(
        request,
        "accounts/profile.html",
        {
            "profil": profil
        }
    )


# ==========================
# MODIFIER LE PROFIL
# ==========================

@login_required
def profile_edit(request):

    profil, created = Profile.objects.get_or_create(utilisateur=request.user)

    if request.method == "POST":

        # Mise à jour des champs texte
        profil.telephone = request.POST.get("telephone", "").strip()
        profil.adresse = request.POST.get("adresse", "").strip()
        profil.ville = request.POST.get("ville", "").strip()
        profil.code_postal = request.POST.get("code_postal", "").strip()

        # Mise à jour de la photo seulement si un nouveau fichier est envoyé
        photo = request.FILES.get("photo")
        if photo:
            profil.photo = photo

        profil.save()

        messages.success(request, "Profil mis à jour avec succès ! ✅")
        return redirect("profile")

    # GET : on passe le profil pour préremplir les champs dans le template
    return render(request, "accounts/profile_edit.html", {"form": profil})


# ==========================
# CHANGER LE MOT DE PASSE
# ==========================

@login_required
def change_password(request):

    if request.method == "POST":

        old_password = request.POST.get("old_password")
        new_password1 = request.POST.get("new_password1")
        new_password2 = request.POST.get("new_password2")

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

        messages.success(request, "Mot de passe modifié avec succès ! 🔒")

        return redirect("profile")

    return render(
        request,
        "accounts/change_password.html"
    )