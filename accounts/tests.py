import io
import re

from PIL import Image
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse

from .models import Profile


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class AccountFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "client",
            password="secret123",
            email="client@example.com"
        )

    def test_login_accepts_email(self):
        response = self.client.post(
            reverse("login"),
            {"username": "client@example.com", "password": "secret123"}
        )
        self.assertRedirects(response, reverse("home"))

    def test_wrong_password_is_rejected(self):
        response = self.client.post(
            reverse("login"),
            {"username": "client", "password": "wrong"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Identifiant ou mot de passe incorrect")

    def test_profile_requires_login_and_edit_saves_address(self):
        self.assertRedirects(
            self.client.get(reverse("profile")),
            f"{reverse('login')}?next={reverse('profile')}"
        )
        self.client.login(username="client", password="secret123")
        response = self.client.post(
            reverse("profile_edit"),
            {
                "first_name": "Client",
                "last_name": "Test",
                "email": "client@example.com",
                "telephone": "76000000",
                "adresse": "Rue 1",
                "ville": "Bamako",
                "code_postal": "0000",
                "date_naissance": "1990-01-01",
                "lieu_naissance": "Bamako",
                "genre": "homme",
            }
        )
        self.assertRedirects(response, reverse("profile"))
        self.assertEqual(Profile.objects.get(utilisateur=self.user).ville, "Bamako")

    def test_profile_avatar_opens_viewer_and_edit_action_is_separate(self):
        self.client.login(username="client", password="secret123")
        profile = Profile.objects.get(utilisateur=self.user)
        profile.photo = self._image("avatar-view.png", "blue")
        profile.save(update_fields=["photo"])
        response = self.client.get(reverse("profile"))
        self.assertContains(response, f'href="{reverse("profile_edit")}"')
        self.assertContains(response, 'id="profile-photo-open"')
        self.assertContains(response, 'id="profile-photo-lightbox"')
        self.assertContains(response, "Voir la photo de profil")
        self.assertNotContains(response, 'id="profile-photo-open" href=')
        self.assertContains(response, "Modifier la photo")
        self.assertContains(response, "bi-pencil-fill")
        self.assertNotContains(response, "Modifier mes informations")
        self.assertNotContains(response, '>Modifier <i class="bi bi-arrow-up-right"></i>')

    def test_profile_without_photo_has_no_empty_lightbox(self):
        self.client.login(username="client", password="secret123")
        response = self.client.get(reverse("profile"))
        self.assertNotContains(response, 'id="profile-photo-lightbox"')
        self.assertContains(response, "Ajouter une photo")

    def test_profile_edit_hides_legacy_birthplace_and_splits_address_labels(self):
        self.client.login(username="client", password="secret123")
        response = self.client.get(reverse("profile_edit"))
        self.assertNotContains(response, "Lieu de naissance")
        self.assertContains(response, "Quartier / Avenue")
        self.assertContains(response, ">Repère<")
        self.assertNotContains(response, "N° de porte / Repère")

    def test_password_change_keeps_session(self):
        self.client.login(username="client", password="secret123")
        response = self.client.post(
            reverse("change_password"),
            {"old_password": "secret123", "new_password1": "newsecret", "new_password2": "newsecret"}
        )
        self.assertRedirects(response, reverse("profile"))
        self.assertTrue(self.client.session.get("_auth_user_id"))

    @staticmethod
    def _image(name, color):
        stream = io.BytesIO()
        Image.new("RGB", (8, 8), color=color).save(stream, format="PNG")
        return SimpleUploadedFile(name, stream.getvalue(), content_type="image/png")

    def test_registration_photo_is_saved_and_rendered_in_navbar_and_profile(self):
        response = self.client.post(
            reverse("register"),
            {
                "email": "photo@example.com",
                "first_name": "Awa",
                "last_name": "Traore",
                "birth_day": "1",
                "birth_month": "1",
                "birth_year": "1995",
                "genre": "femme",
                "password1": "SoleilBleu!45",
                "password2": "SoleilBleu!45",
                "accept_terms": "on",
                "photo": self._image("avatar.png", "blue"),
            }
        )
        self.assertRedirects(response, reverse("profile"))
        profile = Profile.objects.get(utilisateur__email="photo@example.com")
        self.assertTrue(profile.photo.name.startswith("profiles/"))

        profile_page = self.client.get(reverse("profile"))
        self.assertContains(profile_page, profile.photo.url)
        home_page = self.client.get(reverse("home"))
        self.assertContains(home_page, profile.photo.url)

        replacement = self._image("avatar-replaced.png", "red")
        response = self.client.post(
            reverse("profile_edit"),
            {
                "first_name": "Awa",
                "last_name": "Traore",
                "email": "photo@example.com",
                "telephone": "76000000",
                "adresse": "Rue 1",
                "ville": "Bamako",
                "code_postal": "0000",
                "date_naissance": "1995-01-01",
                "lieu_naissance": "Bamako",
                "genre": "femme",
                "photo": replacement,
            }
        )
        self.assertRedirects(response, reverse("profile"))
        profile.refresh_from_db()
        self.assertTrue(profile.photo.name.startswith("profiles/"))
        self.assertIn("avatar-replaced", profile.photo.name)

    def test_registration_without_photo_keeps_initials_fallback(self):
        response = self.client.post(
            reverse("register"),
            {
                "email": "sans-photo@example.com",
                "first_name": "Moussa",
                "last_name": "Diallo",
                "birth_day": "1",
                "birth_month": "1",
                "birth_year": "1990",
                "genre": "homme",
                "password1": "SoleilVert!67",
                "password2": "SoleilVert!67",
                "accept_terms": "on",
            }
        )
        self.assertRedirects(response, reverse("profile"))
        profile = Profile.objects.get(utilisateur__username="sans-photo")
        self.assertFalse(profile.photo)
        home_page = self.client.get(reverse("home"))
        self.assertContains(home_page, "MD")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordResetFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="reset_user",
            email="reset@example.com",
            password="secret123"
        )

    def _extract_reset_path(self, message_body):
        match = re.search(r"/accounts/reset/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+/?", message_body)
        self.assertIsNotNone(match, "Le lien de reset n'a pas été trouvé dans l'email.")
        return match.group(0)

    def _get_valid_reset_path(self):
        self.client.post(reverse("password_reset"), {"email": self.user.email})
        self.assertEqual(len(mail.outbox), 1)
        token_path = self._extract_reset_path(mail.outbox[0].body)
        response = self.client.get(token_path, follow=True)
        self.assertEqual(response.status_code, 200)
        return response.request["PATH_INFO"]

    def test_password_reset_get_password_reset(self):
        response = self.client.get(reverse("password_reset"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mot de passe oublié ?")

    def test_password_reset_known_email_redirects_to_done(self):
        response = self.client.post(
            reverse("password_reset"),
            {"email": self.user.email}
        )
        self.assertRedirects(response, reverse("password_reset_done"))

    def test_password_reset_unknown_email_generic_behavior(self):
        response = self.client.post(reverse("password_reset"), {"email": "nobody@example.com"})
        self.assertRedirects(response, reverse("password_reset_done"))

        response = self.client.post(reverse("password_reset"), {"email": self.user.email})
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)

    def test_password_reset_email_generated_for_known_account(self):
        self.client.post(reverse("password_reset"), {"email": self.user.email})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.user.email, mail.outbox[0].to)

    def test_password_reset_email_contains_reset_url(self):
        self.client.post(reverse("password_reset"), {"email": self.user.email})
        body = mail.outbox[0].body
        reset_path = self._extract_reset_path(body)
        self.assertTrue(reset_path.startswith("/accounts/reset/"), reset_path)

    def test_password_reset_token_opens_password_form(self):
        reset_path = self._get_valid_reset_path()
        response = self.client.get(reset_path)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choisir un nouveau mot de passe")

    def test_password_reset_confirm_accepts_new_password(self):
        reset_path = self._get_valid_reset_path()
        response = self.client.post(
            reset_path,
            {"new_password1": "newsecret123", "new_password2": "newsecret123"}
        )
        self.assertRedirects(response, reverse("password_reset_complete"))

    def test_password_reset_old_password_no_longer_works(self):
        reset_path = self._get_valid_reset_path()
        self.client.post(
            reset_path,
            {"new_password1": "newsecret123", "new_password2": "newsecret123"}
        )
        self.assertFalse(self.client.login(username="reset_user", password="secret123"))

    def test_password_reset_new_password_works(self):
        reset_path = self._get_valid_reset_path()
        self.client.post(
            reset_path,
            {"new_password1": "newsecret123", "new_password2": "newsecret123"}
        )
        self.assertTrue(self.client.login(username="reset_user", password="newsecret123"))

    def test_password_reset_invalid_token_is_rejected(self):
        response = self.client.get(reverse("password_reset_confirm", args=("uidbad", "invalid-token")))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "n’est pas valide ou a expiré")
        self.assertContains(response, "Retour à la connexion")

    def test_password_reset_validators_are_respected(self):
        reset_path = self._get_valid_reset_path()
        response = self.client.post(
            reset_path,
            {"new_password1": "123", "new_password2": "123"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)

    def test_password_reset_complete_returns_login_link(self):
        reset_path = self._get_valid_reset_path()
        self.client.post(
            reset_path,
            {"new_password1": "newsecret123", "new_password2": "newsecret123"}
        )
        complete = self.client.get(reverse("password_reset_complete"))
        self.assertEqual(complete.status_code, 200)
        self.assertContains(complete, "Mot de passe modifié")
        self.assertContains(complete, "Se connecter")
