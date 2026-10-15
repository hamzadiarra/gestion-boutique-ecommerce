"""Presentation feature flags; account suspension remains enforced independently."""
import os
from django.conf import settings


def live_security_enabled():
    return getattr(settings, "LIVE_SECURITY_ENABLED", os.getenv("LIVE_SECURITY_ENABLED", "0").lower() in {"1", "true", "yes", "on"})
