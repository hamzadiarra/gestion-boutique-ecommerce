from datetime import timedelta
from django.contrib.auth import logout
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver
from django.db.models import Q
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.crypto import salted_hmac
from .security_models import AccountSuspension, SecurityEvent


def is_suspended(user):
    return AccountSuspension.objects.filter(user=user, revoked_at__isnull=True, until__gt=timezone.now()).exists()


class SuspensionBackend(ModelBackend):
    def user_can_authenticate(self, user):
        return super().user_can_authenticate(user) and not is_suspended(user)

    def get_user(self, user_id):
        # Le middleware doit pouvoir identifier puis déconnecter une session suspendue.
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
        return user if ModelBackend.user_can_authenticate(self, user) else None


class SuspensionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and is_suspended(request.user):
            logout(request)
            return redirect("login")
        return self.get_response(request)


@receiver(user_logged_in, dispatch_uid="security_login")
def record_login(sender, request, user, **kwargs):
    SecurityEvent.objects.create(kind="login", subject=user, detail="Connexion réussie")


@receiver(user_logged_out, dispatch_uid="security_logout")
def record_logout(sender, request, user, **kwargs):
    if user is not None:
        SecurityEvent.objects.create(kind="logout", subject=user, detail="Déconnexion")


@receiver(user_login_failed, dispatch_uid="security_login_failed")
def record_failed_login(sender, credentials, request, **kwargs):
    identifier = str(credentials.get("username", ""))[:254].casefold()
    identity = salted_hmac("security.identity", identifier, algorithm="sha256").hexdigest()
    address = request.META.get("REMOTE_ADDR", "") if request else ""
    source = salted_hmac("security.source", address, algorithm="sha256").hexdigest() if address else ""
    subject = User.objects.filter(username__iexact=identifier).first() if identifier else None
    recent = SecurityEvent.objects.filter(kind="login_failed", created_at__gte=timezone.now()-timedelta(minutes=15))
    correlation = Q(identity_hash=identity)
    if source:
        correlation |= Q(source_hash=source)
    suspect = recent.filter(correlation).count() >= 4
    SecurityEvent.objects.create(kind="login_failed", subject=subject, identity_hash=identity,
                                 source_hash=source, alert=suspect,
                                 detail="Échecs répétés en 15 minutes : vérifier le contexte avant toute décision." if suspect else "Tentative de connexion refusée")
