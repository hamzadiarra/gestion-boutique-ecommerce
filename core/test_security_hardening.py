import json
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SecurityHardeningTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_assistant_rejects_body_before_parsing(self):
        response=self.client.post(reverse('assistant_ask'),data=json.dumps({'message':'bonjour','padding':'x'*5000}),content_type='application/json')
        self.assertEqual(response.status_code,413)
        self.assertNotIn('assistant_state',self.client.session)

    def test_assistant_deep_json_is_invalid_not_server_error(self):
        response=self.client.post(reverse('assistant_ask'),data='['*1200+'0'+']'*1200,content_type='application/json')
        self.assertEqual(response.status_code,400)

    @override_settings(ASSISTANT_MAX_REQUESTS=2,ASSISTANT_WINDOW_SECONDS=60)
    def test_assistant_rate_limit_survives_session_rotation(self):
        url=reverse('assistant_ask')
        for unused in range(2):
            self.assertEqual(self.client.post(url,{'message':'bonjour'},content_type='application/json').status_code,200)
        self.client.cookies.clear()
        blocked=self.client.post(url,{'message':'bonjour'},content_type='application/json')
        self.assertEqual(blocked.status_code,429)
        self.assertEqual(blocked['Retry-After'],'60')
        self.assertEqual(self.client.post(url,{'message':'bonjour'},content_type='application/json',REMOTE_ADDR='192.0.2.25').status_code,200)

    def test_private_sync_and_assistant_are_not_cached(self):
        user=User.objects.create_user('private-sync')
        self.client.force_login(user)
        for response in [self.client.get(reverse('offline_sync_payload')),self.client.post(reverse('assistant_ask'),{'message':'bonjour'},content_type='application/json')]:
            self.assertIn('no-store',response['Cache-Control'])

    @override_settings(LIVE_SECURITY_ENABLED=False)
    def test_live_security_disabled_for_admin_and_hidden(self):
        user=User.objects.create_user('disabled-admin',is_superuser=True)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('security_dashboard')).status_code,404)
        self.assertEqual(self.client.post(reverse('security_dashboard'),{'action':'review'}).status_code,404)
        self.assertNotContains(self.client.get(reverse('home')),'Live Security')
        self.assertNotContains(self.client.get(reverse('admin_dashboard')),'Live Security')

    @override_settings(LIVE_SECURITY_ENABLED=True)
    def test_live_security_enabled_still_checks_all_roles(self):
        for role in ('client','vendeur','livreur','comptable'):
            user=User.objects.create_user('access-'+role)
            user.profile.role=role;user.profile.save()
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('security_dashboard')).status_code,403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('security_dashboard')).status_code,403)
        admin=User.objects.create_user('enabled-admin',is_superuser=True)
        self.client.force_login(admin)
        self.assertContains(self.client.get(reverse('security_dashboard')),'Live Security')
