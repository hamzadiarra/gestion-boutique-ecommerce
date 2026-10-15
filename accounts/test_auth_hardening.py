from unittest.mock import patch

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
                   AUTH_LOGIN_MAX_FAILURES=2, AUTH_LOGIN_WINDOW_SECONDS=300,
                   AUTH_PASSWORD_RESET_MAX_REQUESTS=2, AUTH_PASSWORD_RESET_WINDOW_SECONDS=300,
                   EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
                   CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "auth-hardening-tests"}})
class AuthenticationHardeningTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.user = User.objects.create_user("hardening-user", email="hardening@example.test", password="Known-password-927!")
        self.request = RequestFactory().post("/accounts/login/", REMOTE_ADDR="192.0.2.10")

    def attempt(self, password="wrong", request=None, username="hardening-user"):
        return authenticate(request=request or self.request, username=username, password=password)

    def test_logout_get_and_head_preserve_session(self):
        self.client.force_login(self.user)
        for method in (self.client.get, self.client.head):
            self.assertEqual(method(reverse("logout")).status_code, 405)
            self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))

    def test_logout_post_requires_csrf_and_valid_post_ends_session(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse("logout")).status_code, 403)
        client.get(reverse("profile"))
        response = client.post(reverse("logout"), HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", client.session)

    def test_failed_attempt_limit_rejects_correct_password_temporarily(self):
        self.attempt()
        self.attempt()
        self.assertIsNone(self.attempt("Known-password-927!"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_limit_is_separate_per_source_and_identifier(self):
        self.attempt()
        self.attempt()
        other_source = RequestFactory().post("/", REMOTE_ADDR="192.0.2.11")
        self.assertEqual(self.attempt("Known-password-927!", request=other_source), self.user)
        other = User.objects.create_user("other", password="Known-password-927!")
        self.assertEqual(self.attempt("Known-password-927!", username="other"), other)

    def test_success_resets_failures(self):
        self.attempt()
        self.assertEqual(self.attempt("Known-password-927!"), self.user)
        self.attempt()
        self.assertEqual(self.attempt("Known-password-927!"), self.user)

    def test_limit_expires_without_blocked_attempts_extending_it(self):
        with patch("time.time", return_value=1000):
            self.attempt()
            self.attempt()
        with patch("time.time", return_value=1299):
            self.assertIsNone(self.attempt("Known-password-927!"))
        with patch("time.time", return_value=1301):
            self.assertEqual(self.attempt("Known-password-927!"), self.user)

    def test_forwarded_header_does_not_bypass_source_limit(self):
        self.attempt()
        self.attempt()
        self.request.META["HTTP_X_FORWARDED_FOR"] = "192.0.2.99"
        self.assertIsNone(self.attempt("Known-password-927!"))

    def test_login_and_admin_share_backend_limit(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        for _ in range(2):
            self.client.post(reverse("login"), {"username": self.user.username, "password": "wrong"})
        response = self.client.post(reverse("admin:login"), {"username": self.user.username, "password": "Known-password-927!"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_reset_limit_does_not_reveal_email_existence(self):
        url = reverse("password_reset")
        for _ in range(2):
            self.assertEqual(self.client.post(url, {"email": self.user.email}).status_code, 302)
        self.assertEqual(len(mail.outbox), 2)
        known = self.client.post(url, {"email": self.user.email})
        unknown = self.client.post(url, {"email": "missing@example.test"})
        self.assertEqual(known.status_code, 302)
        self.assertEqual(known["Location"], unknown["Location"])
        self.assertEqual(len(mail.outbox), 2)
        self.client.post(url, {"email": self.user.email}, REMOTE_ADDR="192.0.2.20")
        self.assertEqual(len(mail.outbox), 3)

    def test_reset_limit_expires(self):
        url = reverse("password_reset")
        with patch("time.time", return_value=1000):
            for _ in range(3):
                self.client.post(url, {"email": self.user.email})
        self.assertEqual(len(mail.outbox), 2)
        with patch("time.time", return_value=1301):
            self.client.post(url, {"email": self.user.email})
        self.assertEqual(len(mail.outbox), 3)

    def test_blocked_attempts_do_not_amplify_security_log(self):
        from .security_models import SecurityEvent
        self.attempt()
        self.attempt()
        before = SecurityEvent.objects.filter(kind="login_failed").count()
        for _ in range(5):
            self.assertIsNone(self.attempt())
        self.assertEqual(SecurityEvent.objects.filter(kind="login_failed").count(), before)

    def test_login_email_alias_shares_username_limit(self):
        for _ in range(2):
            self.client.post(reverse("login"), {"username": self.user.email.upper(), "password": "wrong"})
        response = self.client.post(reverse("login"), {"username": self.user.username, "password": "Known-password-927!"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
