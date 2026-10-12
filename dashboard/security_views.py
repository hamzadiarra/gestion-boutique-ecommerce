from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from accounts.security_models import AccountSuspension, SecurityEvent


def authorized(user):
    return user.is_authenticated and user.is_active and (user.is_superuser or getattr(getattr(user, "profile", None), "role", None) == "admin")


def revoke_sessions(user):
    # Inclut les sessions créées avant l'installation de ce module ; clés jamais rendues.
    for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator(chunk_size=200):
        if str(session.get_decoded().get("_auth_user_id")) == str(user.pk):
            session.delete()


def security_action(request):
    action = request.POST.get("action")
    now = timezone.now()
    try:
        with transaction.atomic():
            if action == "review":
                event = SecurityEvent.objects.select_for_update().get(pk=int(request.POST.get("event_id", "0")), alert=True)
                event.reviewed_by = request.user
                event.reviewed_at = now
                event.save(update_fields=["reviewed_by", "reviewed_at"])
                SecurityEvent.objects.create(kind="alert_reviewed", actor=request.user, subject=event.subject, detail=f"Alerte #{event.pk} consultée ; aucune sanction automatique")
            elif action in {"suspend", "reactivate"}:
                reason = request.POST.get("reason", "").strip()
                if not 5 <= len(reason) <= 500:
                    raise ValueError("Un motif de 5 à 500 caractères est obligatoire.")
                user = User.objects.select_for_update().get(pk=int(request.POST.get("user_id", "0")))
                if authorized(user) or user.is_staff or user.pk == request.user.pk:
                    raise ValueError("Les comptes administratifs sont protégés contre la suspension depuis cet espace.")
                if action == "suspend":
                    if not user.is_active:
                        raise ValueError("Ce compte est déjà désactivé indépendamment de ce module.")
                    hours = int(request.POST.get("hours", "0"))
                    if hours not in (1, 6, 24, 72, 168):
                        raise ValueError("Durée non autorisée.")
                    event = SecurityEvent.objects.select_for_update().get(pk=int(request.POST.get("event_id", "0")), subject=user, alert=True,
                                                                        reviewed_by=request.user, reviewed_at__gte=now-timedelta(hours=24))
                    if AccountSuspension.objects.filter(event=event).exists():
                        raise ValueError("Cette alerte a déjà motivé une suspension.")
                    if AccountSuspension.objects.filter(user=user, revoked_at__isnull=True, until__gt=now).exists():
                        raise ValueError("Une suspension est déjà en cours.")
                    AccountSuspension.objects.filter(user=user, revoked_at__isnull=True).update(revoked_at=now, revoked_by=request.user)
                    suspension = AccountSuspension.objects.create(user=user, actor=request.user, event=event, reason=reason, until=now+timedelta(hours=hours))
                    revoke_sessions(user)
                    SecurityEvent.objects.create(kind="account_suspended", subject=user, actor=request.user, detail=f"{reason} — jusqu'au {suspension.until.isoformat()}")
                else:
                    updated = AccountSuspension.objects.filter(user=user, revoked_at__isnull=True).update(revoked_at=now, revoked_by=request.user)
                    if not updated:
                        raise ValueError("Aucune suspension à révoquer.")
                    SecurityEvent.objects.create(kind="account_reactivated", subject=user, actor=request.user, detail=reason)
            else:
                raise ValueError("Action inconnue.")
    except (ValueError, TypeError, OverflowError, User.DoesNotExist, SecurityEvent.DoesNotExist) as error:
        return HttpResponseBadRequest(str(error) if isinstance(error, ValueError) else "Compte ou alerte examinée introuvable.")
    messages.success(request, "Action enregistrée dans le journal de sécurité.")
    return redirect("security_dashboard")


@never_cache
@require_http_methods(["GET", "POST"])
def security_dashboard(request):
    if not authorized(request.user):
        return HttpResponseForbidden("Espace réservé aux administrateurs autorisés.")
    if request.method == "POST":
        return security_action(request)
    events = SecurityEvent.objects.select_related("subject", "actor", "reviewed_by")
    if request.GET.get("alerts") == "1":
        events = events.filter(alert=True)
    page = Paginator(events, 30).get_page(request.GET.get("page"))
    # Les sessions non expirées ne prouvent pas une présence en ligne actuelle.
    sessions = []
    for session in Session.objects.filter(expire_date__gt=timezone.now()).order_by("-expire_date")[:100]:
        user_id = session.get_decoded().get("_auth_user_id")
        if user_id:
            sessions.append({"user_id": user_id, "expires": session.expire_date})
    users = User.objects.in_bulk([s["user_id"] for s in sessions])
    sessions = [{"username": users[int(s["user_id"])].username, "expires": s["expires"]} for s in sessions if int(s["user_id"]) in users]
    return render(request, "dashboard/security.html", {
        "events": page, "sessions": sessions,
        "reviewed_alerts": SecurityEvent.objects.filter(alert=True, reviewed_by=request.user, reviewed_at__gte=timezone.now()-timedelta(hours=24), subject__isnull=False).select_related("subject")[:50],
        "suspensions": AccountSuspension.objects.filter(revoked_at__isnull=True, until__gt=timezone.now()).select_related("user", "actor"),
    })
