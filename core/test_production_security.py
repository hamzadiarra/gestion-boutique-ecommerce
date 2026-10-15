"""Offline checks: no production connections or credentials."""
import os
import secrets
import subprocess
import sys
from pathlib import Path
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase
from core.security_middleware import ResponseSecurityMiddleware


class ProductionSecurityTests(SimpleTestCase):
    def run_profile(self, changes=None, code="import config.production"):
        env = {key: value for key, value in os.environ.items() if not key.startswith("DJANGO_")}
        env.pop("DATABASE_URL", None)
        env.update(DJANGO_SECRET_KEY=secrets.token_urlsafe(64), DJANGO_ALLOWED_HOSTS="shop.example.invalid")
        for key, value in (changes or {}).items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        return subprocess.run([sys.executable, "-B", "-c", code], env=env,
                              cwd=Path(__file__).resolve().parent.parent,
                              capture_output=True, text=True, timeout=30)

    def test_profile_rejects_missing_secret_and_wildcard_hosts(self):
        for changes in ({"DJANGO_SECRET_KEY": None}, {"DJANGO_SECRET_KEY": "short"},
                        {"DJANGO_ALLOWED_HOSTS": None}, {"DJANGO_ALLOWED_HOSTS": "*"},
                        {"DJANGO_CSRF_TRUSTED_ORIGINS": "http://shop.example.invalid"}):
            with self.subTest(changes=tuple(changes)):
                result = self.run_profile(changes)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ImproperlyConfigured", result.stderr)

    def test_https_profile_passes_deployment_checks(self):
        result = self.run_profile(code="import os; os.environ['DJANGO_SETTINGS_MODULE']='config.production'; import django; django.setup(); from django.core.management import call_command; call_command('check', deploy=True)")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("security.W021", result.stderr)
        self.assertIn("1 issue", result.stderr)

    def test_optional_redis_backend_can_build_client_without_network(self):
        result = self.run_profile({"DJANGO_REDIS_CACHE_URL": "redis://127.0.0.1:6379/15"},
            code="import os; os.environ['DJANGO_SETTINGS_MODULE']='config.production'; import django; django.setup(); from django.core.cache import cache; client=cache._cache.get_client(); assert client.connection_pool")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_csp_preserves_stronger_view_policy(self):
        request = RequestFactory().get("/")
        response = ResponseSecurityMiddleware(lambda request: HttpResponse())(request)
        self.assertIn("frame-ancestors 'none'", response["Content-Security-Policy"])
        def private_view(request):
            return HttpResponse(headers={"Content-Security-Policy": "sandbox; default-src 'none'"})
        response = ResponseSecurityMiddleware(private_view)(request)
        self.assertEqual(response["Content-Security-Policy"], "sandbox; default-src 'none'")
