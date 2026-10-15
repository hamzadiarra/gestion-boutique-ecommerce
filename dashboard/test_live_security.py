"""Live Security workflows use synthetic users and Django's isolated test DB."""
from datetime import timedelta
from io import StringIO

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.sessions.backends.db import SessionStore
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.security_models import AccountSuspension, SecurityEvent


@override_settings(
    DEBUG=True,
    LIVE_SECURITY_ENABLED=True,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class LiveSecurityWorkflowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("demo-security-admin")
        self.admin.profile.role = "admin"
        self.admin.profile.save(update_fields=["role"])
        self.customer = User.objects.create_user("demo-customer", password="Synthetic-only-482!")
        self.client.force_login(self.admin)
        self.url = reverse("security_dashboard")
        self.event = SecurityEvent.objects.create(
            kind="login_failed", subject=self.customer, alert=True,
            reviewed_by=self.admin, reviewed_at=timezone.now(),
        )

    def suspend(self, **changes):
        data = {
            "action": "suspend", "user_id": self.customer.pk,
            "event_id": self.event.pk, "hours": 1,
            "reason": "Vérification manuelle du compte de démonstration",
        }
        data.update(changes)
        return self.client.post(self.url, data)

    def suspension(self, *, expired=False):
        return AccountSuspension.objects.create(
            user=self.customer, actor=self.admin, event=self.event,
            reason="Suspension de démonstration",
            until=timezone.now() + timedelta(hours=-1 if expired else 1),
        )

    def reactivate(self):
        return self.client.post(self.url, {
            "action": "reactivate", "user_id": self.customer.pk,
            "reason": "Identité vérifiée dans la démonstration",
        })

    def test_maximum_reason_keeps_complete_record_and_valid_audit_detail(self):
        reason = "R" * 500
        self.assertEqual(self.suspend(reason=reason).status_code, 302)
        suspension = AccountSuspension.objects.get(user=self.customer)
        self.assertEqual(suspension.reason, reason)
        event = SecurityEvent.objects.get(kind="account_suspended")
        event.full_clean()
        self.assertIn(str(suspension.pk), event.detail)
        self.assertIn(suspension.until.isoformat(), event.detail)
        self.assertEqual(event.actor, self.admin)
        self.assertEqual(event.subject, self.customer)

    def test_expired_suspension_cannot_claim_manual_reactivation(self):
        suspension = self.suspension(expired=True)
        self.assertEqual(self.reactivate().status_code, 400)
        suspension.refresh_from_db()
        self.assertIsNone(suspension.revoked_at)
        self.assertFalse(SecurityEvent.objects.filter(kind="account_reactivated").exists())

    def test_expiration_cleanup_is_not_attributed_to_new_admin_action(self):
        old = self.suspension(expired=True)
        fresh = SecurityEvent.objects.create(
            kind="login_failed", subject=self.customer, alert=True,
            reviewed_by=self.admin, reviewed_at=timezone.now(),
        )
        self.assertEqual(self.suspend(event_id=fresh.pk).status_code, 302)
        old.refresh_from_db()
        self.assertEqual(old.revoked_at, old.until)
        self.assertIsNone(old.revoked_by)
        self.assertEqual(AccountSuspension.objects.filter(user=self.customer).count(), 2)

    def test_promoted_account_can_have_previous_suspension_lifted(self):
        suspension = self.suspension()
        self.customer.is_staff = True
        self.customer.save(update_fields=["is_staff"])
        self.customer.profile.role = "admin"
        self.customer.profile.save(update_fields=["role"])
        self.assertEqual(self.reactivate().status_code, 302)
        suspension.refresh_from_db()
        self.assertEqual(suspension.revoked_by, self.admin)
        self.assertIsNotNone(authenticate(username=self.customer.username, password="Synthetic-only-482!"))

    def test_malformed_session_user_ids_do_not_break_dashboard(self):
        for user_id in ("invalid", [1], {"id": 1}, "9" * 100, -1, True):
            session = SessionStore()
            session["_auth_user_id"] = user_id
            session.create()
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_review_options_exclude_spent_alerts_and_protected_accounts(self):
        self.suspension(expired=True)
        protected = SecurityEvent.objects.create(
            kind="login_failed", subject=self.admin, alert=True,
            reviewed_by=self.admin, reviewed_at=timezone.now(),
        )
        eligible = SecurityEvent.objects.create(
            kind="login_failed", subject=self.customer, alert=True,
            reviewed_by=self.admin, reviewed_at=timezone.now(),
        )
        response = self.client.get(self.url)
        self.assertEqual(list(response.context["reviewed_alerts"]), [eligible])
        self.assertNotContains(response, f'<option value="{protected.pk}"')

    def test_protected_targets_are_rejected_with_otherwise_valid_request(self):
        for protection in ("staff", "superuser", "admin", "self"):
            with self.subTest(protection=protection):
                target = self.admin if protection == "self" else User.objects.create_user("protected-" + protection)
                if protection in ("staff", "superuser"):
                    setattr(target, "is_" + protection, True)
                    target.save()
                if protection == "admin":
                    target.profile.role = "admin"
                    target.profile.save()
                alert = SecurityEvent.objects.create(
                    kind="login_failed", subject=target, alert=True,
                    reviewed_by=self.admin, reviewed_at=timezone.now(),
                )
                self.assertEqual(self.suspend(user_id=target.pk, event_id=alert.pk).status_code, 400)
                self.assertFalse(AccountSuspension.objects.filter(user=target).exists())

    def test_get_and_missing_csrf_cannot_mutate_any_security_action(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        csrf_client.get(self.url)
        count = SecurityEvent.objects.count()
        for action in ("review", "suspend", "reactivate"):
            with self.subTest(action=action):
                data = {"action": action, "user_id": self.customer.pk,
                        "event_id": self.event.pk, "hours": 1, "reason": "Motif valide"}
                self.assertEqual(self.client.get(self.url, data).status_code, 200)
                self.assertEqual(csrf_client.post(self.url, data).status_code, 403)
        self.assertEqual(SecurityEvent.objects.count(), count)
        self.assertFalse(AccountSuspension.objects.exists())
        token = csrf_client.cookies["csrftoken"].value
        response = csrf_client.post(self.url, {"action": "review", "event_id": self.event.pk}, HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SecurityEvent.objects.filter(kind="alert_reviewed").count(), 1)

    @override_settings(LIVE_SECURITY_ENABLED=False)
    def test_suspension_and_expiry_remain_effective_with_dashboard_off(self):
        target = Client()
        target.force_login(self.customer)
        suspension = self.suspension()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertIsNone(authenticate(username=self.customer.username, password="Synthetic-only-482!"))
        self.assertEqual(target.get(reverse("profile")).status_code, 302)
        self.assertNotIn("_auth_user_id", target.session)
        suspension.until = timezone.now() - timedelta(seconds=1)
        suspension.save(update_fields=["until"])
        self.assertIsNotNone(authenticate(username=self.customer.username, password="Synthetic-only-482!"))
        self.assertEqual(target.get(reverse("profile")).status_code, 302)

    def test_reactivation_does_not_enable_independently_inactive_account(self):
        self.suspension()
        self.customer.is_active = False
        self.customer.save(update_fields=["is_active"])
        self.assertEqual(self.reactivate().status_code, 302)
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)
        self.assertIsNone(authenticate(username=self.customer.username, password="Synthetic-only-482!"))
        self.assertEqual(self.reactivate().status_code, 400)
        self.assertEqual(SecurityEvent.objects.filter(kind="account_reactivated").count(), 1)

    def test_reused_alert_and_duplicate_suspension_leave_audit_unchanged(self):
        self.assertEqual(self.suspend().status_code, 302)
        self.assertEqual(self.suspend().status_code, 400)
        self.assertEqual(self.reactivate().status_code, 302)
        self.assertEqual(self.suspend().status_code, 400)
        self.assertEqual(AccountSuspension.objects.count(), 1)
        self.assertEqual(SecurityEvent.objects.filter(kind="account_suspended").count(), 1)

    def test_purge_retains_old_suspension_evidence_and_admin_audit(self):
        self.assertEqual(self.suspend().status_code, 302)
        self.assertEqual(self.reactivate().status_code, 302)
        old = timezone.now() - timedelta(days=100)
        SecurityEvent.objects.update(created_at=old)
        unrelated = SecurityEvent.objects.create(kind="login_failed", detail="Ancien événement synthétique")
        SecurityEvent.objects.filter(pk=unrelated.pk).update(created_at=old)
        call_command("purge_security_events", execute=True, stdout=StringIO())
        self.assertFalse(SecurityEvent.objects.filter(pk=unrelated.pk).exists())
        self.assertTrue(SecurityEvent.objects.filter(pk=self.event.pk).exists())
        self.assertTrue(SecurityEvent.objects.filter(kind="account_suspended").exists())
        self.assertTrue(SecurityEvent.objects.filter(kind="account_reactivated").exists())
