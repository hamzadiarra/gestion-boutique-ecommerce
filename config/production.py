"""Opt-in HTTPS deployment profile. Never imported by local HTTP settings."""
from .settings import *  # noqa: F403
from django.core.exceptions import ImproperlyConfigured

DEBUG = False
if not os.getenv("DJANGO_SECRET_KEY") or len(SECRET_KEY) < 50 or SECRET_KEY.startswith("django-insecure-"):
    raise ImproperlyConfigured("Production requires a strong DJANGO_SECRET_KEY supplied outside Git.")
if not os.getenv("DJANGO_ALLOWED_HOSTS") or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("Production requires explicit DJANGO_ALLOWED_HOSTS.")
CSRF_TRUSTED_ORIGINS = [value.strip() for value in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if value.strip()]
if any(not value.startswith("https://") for value in CSRF_TRUSTED_ORIGINS):
    raise ImproperlyConfigured("Production CSRF trusted origins must use HTTPS.")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
MIDDLEWARE = [*MIDDLEWARE, "core.security_middleware.ResponseSecurityMiddleware"]
# Use a shared backend in multiworker production; no credentials are embedded here.
if os.getenv("DJANGO_REDIS_CACHE_URL"):
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": os.environ["DJANGO_REDIS_CACHE_URL"]}}
