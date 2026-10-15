"""Presentation feature flags; account suspension remains enforced independently."""
import os
from django.conf import settings


def live_security_enabled():
    if not settings.DEBUG:
        return False
    value = getattr(settings, "LIVE_SECURITY_ENABLED", os.getenv("LIVE_SECURITY_ENABLED", "0"))
    return value is True or (isinstance(value, str) and value.strip().lower() in {"1", "true", "yes", "on"})
