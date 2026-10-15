from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from .models import Notification


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class NotificationRedirectSecurityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("notification-owner")
        self.notification = Notification.objects.create(utilisateur=self.user, message="Test")
        self.client.force_login(self.user)
        self.urls = [reverse("mark_as_read", args=[self.notification.pk]), reverse("mark_all_as_read")]

    def test_external_and_scheme_relative_referers_fall_back(self):
        for url in self.urls:
            for referer in ("https://outside.example/", "//outside.example/", "https://testserver.outside.example/"):
                with self.subTest(url=url, referer=referer):
                    response = self.client.post(url, HTTP_REFERER=referer)
                    self.assertEqual(response["Location"], reverse("notification_list"))

    def test_https_does_not_redirect_to_http(self):
        for url in self.urls:
            response = self.client.post(url, secure=True, HTTP_REFERER="http://testserver/accounts/profile/")
            self.assertEqual(response["Location"], reverse("notification_list"))

    def test_internal_destination_is_preserved(self):
        for url in self.urls:
            response = self.client.post(url, HTTP_REFERER="/accounts/profile/")
            self.assertEqual(response["Location"], "/accounts/profile/")

    def test_notification_mutations_stay_scoped_to_owner(self):
        other = User.objects.create_user("notification-other")
        notification = Notification.objects.create(utilisateur=other, message="Private")
        self.assertEqual(self.client.post(reverse("mark_as_read", args=[notification.pk])).status_code, 404)
        self.client.post(reverse("mark_all_as_read"))
        notification.refresh_from_db()
        self.assertFalse(notification.lu)
