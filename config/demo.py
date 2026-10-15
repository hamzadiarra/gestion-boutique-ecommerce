"""Explicit local demo profile: runserver 127.0.0.1:8001 --settings=config.demo."""
from .settings import *  # noqa: F403
from django.core.exceptions import ImproperlyConfigured

if not DEBUG or DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3":
    raise ImproperlyConfigured("The demo profile requires local SQLite and DEBUG=True.")
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
LIVE_SECURITY_ENABLED = env_bool("LIVE_SECURITY_ENABLED", True)
LIVE_SECURITY_DEMO = True
