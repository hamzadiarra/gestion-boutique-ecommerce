from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class DashboardPermissionTests(TestCase):
    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("vendeur_dashboard"))
        self.assertRedirects(response, reverse("login"))

    def test_client_cannot_open_professional_spaces(self):
        User.objects.create_user("client", password="secret123")
        self.client.login(username="client", password="secret123")
        self.assertRedirects(self.client.get(reverse("vendeur_dashboard")), reverse("home"))
        self.assertRedirects(self.client.get(reverse("comptable_dashboard")), reverse("home"))

    def test_seller_reaches_main_dashboard(self):
        user = User.objects.create_user("seller", password="secret123")
        user.profile.role = "vendeur"
        user.profile.save()
        self.client.login(username="seller", password="secret123")
        self.assertEqual(self.client.get(reverse("vendeur_dashboard")).status_code, 200)
