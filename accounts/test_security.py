from datetime import timedelta
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.test import TestCase, Client, override_settings
from django.utils import timezone


@override_settings(LIVE_SECURITY_ENABLED=True, PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SecurityTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("security-admin", password="Test-Admin-482!")
        self.admin.profile.role = "admin"
        self.admin.profile.save()
        self.customer = User.objects.create_user("customer", password="Test-Client-482!")
        self.client.force_login(self.admin)

    def test_dashboard_restricted_and_never_cached(self):
        response = self.client.get("/dashboard/security/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.customer.is_staff = True
        self.customer.save()
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get("/dashboard/security/").status_code, 403)
        self.assertEqual(self.client.post("/dashboard/security/", {}).status_code, 403)

    def test_suspend_requires_review_reason_and_post(self):
        response = self.client.post("/dashboard/security/", {"action": "suspend", "user_id": self.customer.pk, "hours": 1, "reason": "À examiner"})
        self.assertEqual(response.status_code, 400)

    def test_suspension_blocks_login_and_sessions_then_can_be_revoked(self):
        from .security_models import SecurityEvent, AccountSuspension
        event = SecurityEvent.objects.create(kind="login_failed", subject=self.customer, detail="Échecs répétés", alert=True)
        target = Client()
        target.force_login(self.customer)
        self.client.post("/dashboard/security/", {"action": "review", "event_id": event.pk})
        response = self.client.post("/dashboard/security/", {"action": "suspend", "user_id": self.customer.pk, "event_id": event.pk, "hours": 1, "reason": "Vérification manuelle demandée"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(AccountSuspension.objects.filter(user=self.customer, revoked_at__isnull=True).exists())
        self.assertIsNone(authenticate(username="customer", password="Test-Client-482!"))
        self.assertEqual(target.get("/accounts/profile/").status_code, 302)
        self.assertNotIn("_auth_user_id", target.session)
        response = self.client.post("/dashboard/security/", {"action": "reactivate", "user_id": self.customer.pk, "reason": "Identité vérifiée"})
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(authenticate(username="customer", password="Test-Client-482!"))
        self.assertTrue(SecurityEvent.objects.filter(kind="account_reactivated", subject=self.customer, actor=self.admin).exists())

    def test_expired_suspension_and_inactive_account(self):
        from .security_models import AccountSuspension
        AccountSuspension.objects.create(user=self.customer, actor=self.admin, reason="Test", until=timezone.now()-timedelta(seconds=1))
        self.assertIsNotNone(authenticate(username="customer", password="Test-Client-482!"))
        self.customer.is_active = False
        self.customer.save()
        self.assertIsNone(authenticate(username="customer", password="Test-Client-482!"))

    def test_browsing_is_not_an_alert_and_failed_login_contains_no_password(self):
        from .security_models import SecurityEvent
        self.client.get("/products/")
        self.assertFalse(SecurityEvent.objects.filter(alert=True).exists())
        for _ in range(5):
            authenticate(username="customer", password="NEVER-STORE-THIS")
        events = SecurityEvent.objects.filter(subject=self.customer, kind="login_failed")
        self.assertEqual(events.count(), 5)
        self.assertTrue(events.filter(alert=True).exists())
        self.assertNotIn("NEVER-STORE-THIS", str(list(events.values())))
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_active)

    def test_protected_accounts_cannot_be_suspended(self):
        from .security_models import SecurityEvent
        event = SecurityEvent.objects.create(kind="login_failed", subject=self.admin, alert=True, reviewed_by=self.admin, reviewed_at=timezone.now())
        response = self.client.post("/dashboard/security/", {"action": "suspend", "user_id": self.admin.pk, "event_id": event.pk, "hours": 1, "reason": "Test"})
        self.assertEqual(response.status_code, 400)

    def test_security_actions_require_csrf_and_never_expose_session_keys(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        response = csrf_client.get("/dashboard/security/")
        self.assertNotContains(response, csrf_client.session.session_key)
        self.assertEqual(csrf_client.post("/dashboard/security/", {"action": "review", "event_id": 1}).status_code, 403)
        self.assertEqual(Client().get("/dashboard/security/").status_code, 403)

    def test_review_cannot_be_reused_for_another_account_or_invalid_duration(self):
        from .security_models import SecurityEvent, AccountSuspension
        event = SecurityEvent.objects.create(kind="login_failed", subject=self.customer, alert=True, reviewed_by=self.admin, reviewed_at=timezone.now())
        other = User.objects.create_user("another-customer")
        data = {"action": "suspend", "user_id": other.pk, "event_id": event.pk, "hours": 1, "reason": "Motif documenté"}
        self.assertEqual(self.client.post("/dashboard/security/", data).status_code, 400)
        data["user_id"] = self.customer.pk
        data["hours"] = 999
        self.assertEqual(self.client.post("/dashboard/security/", data).status_code, 400)
        data["hours"] = 1
        data["reason"] = " "
        self.assertEqual(self.client.post("/dashboard/security/", data).status_code, 400)
        self.assertFalse(AccountSuspension.objects.exists())

    def test_old_sessions_stay_closed_after_reactivation(self):
        from .security_models import SecurityEvent
        event = SecurityEvent.objects.create(kind="login_failed", subject=self.customer, alert=True, reviewed_by=self.admin, reviewed_at=timezone.now())
        old_session = Client()
        old_session.force_login(self.customer)
        self.client.post("/dashboard/security/", {"action": "suspend", "user_id": self.customer.pk, "event_id": event.pk, "hours": 1, "reason": "Vérification du compte"})
        self.client.post("/dashboard/security/", {"action": "reactivate", "user_id": self.customer.pk, "reason": "Identité vérifiée"})
        self.assertEqual(old_session.get("/accounts/profile/").status_code, 302)

    def test_expired_review_is_rejected_and_audit_purge_is_preview_by_default(self):
        from io import StringIO
        from django.core.management import call_command
        from .security_models import SecurityEvent
        event = SecurityEvent.objects.create(kind="login_failed", subject=self.customer, alert=True, reviewed_by=self.admin, reviewed_at=timezone.now()-timedelta(days=2))
        response = self.client.post("/dashboard/security/", {"action": "suspend", "user_id": self.customer.pk, "event_id": event.pk, "hours": 1, "reason": "Motif documenté"})
        self.assertEqual(response.status_code, 400)
        SecurityEvent.objects.filter(pk=event.pk).update(created_at=timezone.now()-timedelta(days=100))
        out = StringIO()
        call_command("purge_security_events", stdout=out)
        self.assertIn("1 événements éligibles", out.getvalue())
        self.assertTrue(SecurityEvent.objects.filter(pk=event.pk).exists())

    def test_live_security_hidden_and_denied_to_other_roles(self):
        self.client.logout()
        self.assertEqual(self.client.get("/dashboard/security/").status_code, 403)
        self.assertNotContains(self.client.get("/"), 'href="/dashboard/security/"')
        for role in ("client", "vendeur", "livreur", "comptable"):
            with self.subTest(role=role):
                self.customer.profile.role = role
                self.customer.profile.save()
                self.client.force_login(self.customer)
                self.assertEqual(self.client.get("/dashboard/security/").status_code, 403)
                self.assertEqual(self.client.post("/dashboard/security/", {"action": "review"}).status_code, 403)
                self.assertNotContains(self.client.get("/"), 'href="/dashboard/security/"')

    def test_superuser_can_access_live_security(self):
        self.customer.is_superuser = True
        self.customer.save()
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get("/dashboard/security/").status_code, 200)
