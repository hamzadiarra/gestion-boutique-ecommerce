from django.utils.translation import gettext
from datetime import date

from django.contrib import messages
from django.contrib.auth import (
    authenticate,
    login,
    logout,
    update_session_auth_hash,
)
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import ProfileForm, validate_profile_photo
from .models import Profile
from orders.models import Order
from products.models import Wishlist


# ==========================
# INSCRIPTION
# ==========================

def register(request):

    # Jours proposés dans le formulaire
    days = range(1, 32)

    # Mois affichés en toutes lettres dans l'inscription
    mois_choices = [
        (1, "Janvier"),
        (2, "Février"),
        (3, "Mars"),
        (4, "Avril"),
        (5, "Mai"),
        (6, "Juin"),
        (7, "Juillet"),
        (8, "Août"),
        (9, "Septembre"),
        (10, "Octobre"),
        (11, "Novembre"),
        (12, "Décembre"),
    ]

    # Années proposées dans le formulaire
    current_year = date.today().year
    years = range(current_year, 1899, -1)

    if request.method == "POST":

        # ==================================================
        # ÉTAPE 1 — IDENTITÉ
        # ==================================================

        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()

        # ==================================================
        # ÉTAPE 2 — INFORMATIONS PERSONNELLES
        # ==================================================

        birth_day = request.POST.get("birth_day", "").strip()
        birth_month = request.POST.get("birth_month", "").strip()
        birth_year = request.POST.get("birth_year", "").strip()

        genre = request.POST.get("genre", "").strip()

        # ==================================================
        # ÉTAPE 3 — COMPTE / SÉCURITÉ
        # ==================================================

        email = request.POST.get("email", "").strip().lower()

        photo = request.FILES.get("photo")

        password1 = request.POST.get("password1", "")
        password2 = request.POST.get("password2", "")

        accept_terms = request.POST.get("accept_terms") == "on"

        # L'inscription publique crée TOUJOURS un client.
        # Toute valeur "role" falsifiée dans le POST est ignorée.
        role = "client"

        # ==================================================
        # CONSERVATION DES DONNÉES EN CAS D'ERREUR
        # ==================================================

        form_data = {
            "first_name": first_name,
            "last_name": last_name,
            "birth_day": birth_day,
            "birth_month": birth_month,
            "birth_year": birth_year,
            "genre": genre,
            "email": email,
            "accept_terms": accept_terms,
        }

        errors = {}

        # ==================================================
        # VALIDATION ÉTAPE 1
        # ==================================================

        if not first_name:
            errors["first_name"] = "Veuillez saisir votre prénom."

        if not last_name:
            errors["last_name"] = "Veuillez saisir votre nom."

        # ==================================================
        # VALIDATION ÉTAPE 2
        # ==================================================

        parsed_birth_date = None

        if not birth_day:
            errors["birth_day"] = "Choisissez le jour."

        if not birth_month:
            errors["birth_month"] = "Choisissez le mois."

        if not birth_year:
            errors["birth_year"] = "Choisissez l'année."

        if birth_day and birth_month and birth_year:
            try:
                parsed_birth_date = date(
                    int(birth_year),
                    int(birth_month),
                    int(birth_day),
                )

                if parsed_birth_date > date.today():
                    parsed_birth_date = None
                    errors["date_naissance"] = (
                        "La date de naissance ne peut pas être dans le futur."
                    )

            except (TypeError, ValueError):
                parsed_birth_date = None
                errors["date_naissance"] = (
                    "Cette date de naissance n'est pas valide."
                )

        valid_genres = dict(Profile.GENRE_CHOICES)

        if genre not in valid_genres:
            errors["genre"] = "Veuillez sélectionner une option."

        # ==================================================
        # VALIDATION ÉTAPE 3
        # ==================================================

        if not email:
            errors["email"] = "Veuillez saisir votre adresse e-mail."

        else:
            try:
                validate_email(email)

            except ValidationError:
                errors["email"] = (
                    "Cette adresse e-mail n'est pas valide."
                )

            if User.objects.filter(email__iexact=email).exists():
                errors["email"] = (
                    "Cette adresse e-mail est déjà utilisée."
                )

        if not password1:
            errors["password1"] = (
                "Veuillez choisir un mot de passe."
            )

        else:
            try:
                validate_password(password1)

            except ValidationError as error:
                errors["password1"] = " ".join(error.messages)

        if not password2:
            errors["password2"] = (
                "Veuillez confirmer votre mot de passe."
            )

        elif password1 and password1 != password2:
            errors["password2"] = (
                "Les deux mots de passe ne correspondent pas."
            )

        if not accept_terms:
            errors["accept_terms"] = (
                "Vous devez accepter les conditions d'utilisation "
                "pour créer votre compte."
            )

        if photo:
            try:
                validate_profile_photo(photo)
            except ValidationError as error:
                errors["photo"] = " ".join(error.messages)

        # ==================================================
        # DÉTERMINER L'ÉTAPE À RÉAFFICHER
        # ==================================================

        step_1_fields = {
            "first_name",
            "last_name",
        }

        step_2_fields = {
            "birth_day",
            "birth_month",
            "birth_year",
            "date_naissance",
            "genre",
        }

        if any(field in errors for field in step_1_fields):
            active_step = 1

        elif any(field in errors for field in step_2_fields):
            active_step = 2

        else:
            active_step = 3

        # ==================================================
        # RETOUR AVEC ERREURS
        # ==================================================

        if errors:
            return render(
                request,
                "accounts/register.html",
                {
                    "errors": errors,
                    "form_data": form_data,
                    "active_step": active_step,
                    "days": days,
                    "mois_choices": mois_choices,
                    "years": years,
                },
            )

        # ==================================================
        # GÉNÉRER UN USERNAME INTERNE
        # ==================================================

        username_base = "".join(
            char
            for char in email.split("@", 1)[0]
            if char.isalnum() or char in "._-"
        )[:130] or "user"

        username = username_base
        counter = 1

        while User.objects.filter(username=username).exists():

            suffix = str(counter)

            username = (
                f"{username_base[:150 - len(suffix)]}{suffix}"
            )

            counter += 1

        # ==================================================
        # CRÉATION DU COMPTE
        # ==================================================

        with transaction.atomic():

            user = User.objects.create_user(
                username=username,
                email=email,
                password=password1,
                first_name=first_name,
                last_name=last_name,
            )

            # Le Profile peut déjà avoir été créé par le signal post_save.
            profil, _ = Profile.objects.get_or_create(
                utilisateur=user
            )

            # Sécurité absolue :
            # une inscription publique = client.
            profil.role = role

            profil.date_naissance = parsed_birth_date
            profil.genre = genre
            profil.photo = photo

            # Le lieu de naissance n'est désormais
            # plus demandé pendant l'inscription.
            profil.save()

        # ==================================================
        # CONNEXION AUTOMATIQUE
        # ==================================================

        login(request, user)

        messages.success(
            request,
            f"Bienvenue {first_name} ! Votre compte est prêt."
        )

        return redirect("profile")

    # ==================================================
    # PREMIER AFFICHAGE
    # ==================================================

    return render(
        request,
        "accounts/register.html",
        {
            "errors": {},
            "form_data": {},
            "active_step": 1,
            "days": days,
            "mois_choices": mois_choices,
            "years": years,
        },
    )


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

            user_by_email = User.objects.filter(
                email__iexact=identifiant
            ).first()

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

            # Redirection sécurisée vers l'URL demandée
            if next_url and url_has_allowed_host_and_scheme(
                url=next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure()
            ):
                return redirect(next_url)

            # Redirection selon le rôle
            profile = getattr(utilisateur, "profile", None)

            if profile:

                if profile.role == "livreur" and not utilisateur.is_superuser:
                    return redirect("livreur_dashboard")

                if (
                    utilisateur.is_superuser
                    or utilisateur.is_staff
                    or profile.role == "admin"
                ):
                    return redirect("admin_dashboard")

                elif profile.role == "vendeur":
                    return redirect("vendeur_dashboard")

                elif profile.role == "comptable":
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

    messages.info(
        request,
        gettext("Vous avez été déconnecté.")
    )

    return redirect("home")


# ==========================
# PROFIL
# ==========================

@login_required
def profile_view(request):

    profil, created = Profile.objects.get_or_create(
        utilisateur=request.user
    )

    recent_orders = Order.objects.filter(
        utilisateur=request.user
    ).order_by("-date_creation")[:3]

    return render(
        request,
        "accounts/profile.html",
        {
            "profil": profil,
            "recent_orders": recent_orders,
            "order_count": Order.objects.filter(
                utilisateur=request.user
            ).count(),
            "wishlist_count": Wishlist.objects.filter(
                utilisateur=request.user
            ).values("produits").count(),
        }
    )


# ==========================
# MODIFIER LE PROFIL
# ==========================

@login_required
def profile_edit(request):

    profil, created = Profile.objects.get_or_create(
        utilisateur=request.user
    )

    # Capturer avant form.is_valid(): ModelForm peut déjà affecter le nouveau
    # fichier à l'instance pendant son étape de nettoyage.
    old_photo_name = profil.photo.name if profil.photo else None
    old_photo_storage = profil.photo.storage if profil.photo else None

    form = ProfileForm(
        request.POST or None,
        request.FILES or None,
        instance=profil
    )

    if request.method == "POST" and form.is_valid():

        # Conserver l'ancien FieldFile jusqu'à l'enregistrement réussi de la
        # nouvelle image. Ainsi une nouvelle image invalide ne supprime jamais
        # la photo actuelle.
        form.save()

        if (
            old_photo_name
            and old_photo_storage
            and old_photo_name != getattr(profil.photo, "name", None)
        ):
            # Le nom et le storage sont figés avant l'affectation du nouveau
            # fichier : ModelForm peut réutiliser l'objet FieldFile de l'instance.
            old_photo_storage.delete(old_photo_name)

        messages.success(
            request,
            gettext("Vos informations personnelles ont été mises à jour.")
        )

        return redirect("profile")

    return render(
        request,
        "accounts/profile_edit.html",
        {
            "form": form
        }
    )


@login_required
@require_POST
def delete_profile_photo(request):
    """Supprime uniquement la photo du profil de l'utilisateur connecté."""
    profil, _ = Profile.objects.get_or_create(utilisateur=request.user)
    photo = profil.photo if profil.photo else None

    if photo and photo.name:
        photo.delete(save=False)
        profil.photo = None
        profil.save(update_fields=["photo", "date_modification"])
        messages.success(
            request,
            gettext("Votre photo de profil a été supprimée.")
        )
    else:
        messages.info(request, gettext("Aucune photo de profil à supprimer."))

    return redirect("profile")


# ==========================
# CHANGER LE MOT DE PASSE
# ==========================

@login_required
def change_password(request):

    if request.method == "POST":

        old_password = request.POST.get(
            "old_password",
            ""
        )

        new_password1 = request.POST.get(
            "new_password1",
            ""
        )

        new_password2 = request.POST.get(
            "new_password2",
            ""
        )

        if not request.user.check_password(old_password):

            messages.error(
                request,
                gettext("L'ancien mot de passe est incorrect.")
            )

            return render(
                request,
                "accounts/change_password.html"
            )

        if new_password1 != new_password2:

            messages.error(
                request,
                gettext("Les nouveaux mots de passe ne correspondent pas.")
            )

            return render(
                request,
                "accounts/change_password.html"
            )

        try:
            validate_password(
                new_password1,
                user=request.user
            )

        except ValidationError as error:

            messages.error(
                request,
                " ".join(error.messages)
            )

            return render(
                request,
                "accounts/change_password.html"
            )

        request.user.set_password(new_password1)
        request.user.save()

        # Garder l'utilisateur connecté après le changement
        update_session_auth_hash(
            request,
            request.user
        )

        messages.success(
            request,
            gettext("Votre mot de passe a été modifié avec succès.")
        )

        return redirect("profile")

    return render(
        request,
        "accounts/change_password.html"
    )
