from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Profile


class AccountFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("client", password="secret123", email="client@example.com")

    def test_login_accepts_email(self):
        response = self.client.post(reverse("login"), {"username": "client@example.com", "password": "secret123"})
        self.assertRedirects(response, reverse("home"))

    def test_wrong_password_is_rejected(self):
        response = self.client.post(reverse("login"), {"username": "client", "password": "wrong"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Identifiant ou mot de passe incorrect")

    def test_profile_requires_login_and_edit_saves_address(self):
        self.assertRedirects(self.client.get(reverse("profile")), f"{reverse('login')}?next={reverse('profile')}")
        self.client.login(username="client", password="secret123")
        response = self.client.post(reverse("profile_edit"), {"telephone": "76000000", "adresse": "Rue 1", "ville": "Bamako", "code_postal": "0000"})
        self.assertRedirects(response, reverse("profile"))
        self.assertEqual(Profile.objects.get(utilisateur=self.user).ville, "Bamako")

    def test_password_change_keeps_session(self):
        self.client.login(username="client", password="secret123")
        response = self.client.post(reverse("change_password"), {"old_password": "secret123", "new_password1": "newsecret", "new_password2": "newsecret"})
        self.assertRedirects(response, reverse("profile"))
        self.assertTrue(self.client.session.get("_auth_user_id"))
