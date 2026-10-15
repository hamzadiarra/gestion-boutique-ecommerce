import os
import secrets
import subprocess
import sys
from pathlib import Path
from django.test import SimpleTestCase, override_settings
from core.security_flags import live_security_enabled


class DemoSecurityTests(SimpleTestCase):
    @override_settings(DEBUG=False, LIVE_SECURITY_ENABLED=True)
    def test_flag_never_enables_dashboard_when_debug_is_false(self):
        self.assertFalse(live_security_enabled())

    def profile(self, module, **changes):
        env={k:v for k,v in os.environ.items() if not k.startswith("DJANGO_") and k not in {"DATABASE_URL","LIVE_SECURITY_ENABLED"}}
        env.update(DJANGO_SECRET_KEY=secrets.token_urlsafe(64),DJANGO_ALLOWED_HOSTS="shop.example.invalid")
        env.update(changes)
        code="import os; os.environ['DJANGO_SETTINGS_MODULE']='"+module+"'; import django; django.setup(); from django.conf import settings; from core.security_flags import live_security_enabled; print(live_security_enabled()); print(settings.ALLOWED_HOSTS)"
        return subprocess.run([sys.executable,"-B","-c",code],env=env,cwd=Path(__file__).resolve().parent.parent,capture_output=True,text=True,timeout=30)

    def test_demo_explicitly_enables_flag_and_limits_hosts(self):
        result=self.profile("config.demo")
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("True",result.stdout)
        self.assertNotIn("shop.example.invalid",result.stdout)
        self.assertIn("127.0.0.1",result.stdout)
        disabled=self.profile("config.demo",LIVE_SECURITY_ENABLED="0")
        self.assertIn("False",disabled.stdout)

    def test_demo_refuses_nonlocal_database_or_disabled_debug(self):
        for changes in ({"DATABASE_URL":"postgresql://demo:demo@db.invalid/demo"},{"DJANGO_DEBUG":"0"}):
            result=self.profile("config.demo",**changes)
            self.assertNotEqual(result.returncode,0)
            self.assertIn("ImproperlyConfigured",result.stderr)

    def test_production_stays_disabled_even_with_environment_flag(self):
        result=self.profile("config.production",LIVE_SECURITY_ENABLED="1")
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("False",result.stdout)
