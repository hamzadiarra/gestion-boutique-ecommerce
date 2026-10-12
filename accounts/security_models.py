"""Journal minimal de sécurité ; aucune capture d'écran ni secret utilisateur."""
from django.conf import settings
from django.db import models
from django.db.models import Q


class SecurityEvent(models.Model):
    kind = models.CharField(max_length=40)
    subject = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="security_events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="security_actions")
    detail = models.CharField(max_length=500, blank=True)
    identity_hash = models.CharField(max_length=64, blank=True, db_index=True)
    source_hash = models.CharField(max_length=64, blank=True, db_index=True)
    alert = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_security_events")
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["kind", "created_at"], name="security_kind_created")]


class AccountSuspension(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="suspensions")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="issued_suspensions")
    event = models.ForeignKey(SecurityEvent, null=True, on_delete=models.SET_NULL)
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    until = models.DateTimeField(db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="revoked_suspensions")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user"], condition=Q(revoked_at__isnull=True), name="one_open_suspension_per_user")]
