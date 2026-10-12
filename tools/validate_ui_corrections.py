"""Vérification Edge/Android émulé, base et médias de test uniquement.
python manage.py test tools.validate_ui_corrections --noinput
"""
import io
import os
import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from django.urls import reverse
from PIL import Image
from playwright.sync_api import sync_playwright

from accounts.security_models import SecurityEvent
from categories.models import Category
from products.models import Product


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class UICorrectionBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.addCleanup(self.media.cleanup)
        self.addCleanup(self.settings_override.disable)
        self.category = Category.objects.create(nom="Collection test")
        image = io.BytesIO()
        Image.new("RGB", (480, 320), "navy").save(image, format="PNG")
        self.category.image.save("collection.png", ContentFile(image.getvalue()))
        Product.objects.create(categorie=self.category, nom="Produit test", prix=15000, stock=3)
        self.admin = User.objects.create_user("correction-admin")
        self.admin.profile.role = "admin"
        self.admin.profile.save()
        self.customer = User.objects.create_user("correction-client")
        self.event = SecurityEvent.objects.create(kind="login_failed", subject=self.customer,
            detail="Alerte de test isolée", alert=True)
        client = Client()
        client.force_login(self.admin)
        self.session_key = client.session.session_key
        self.dashboard_url = reverse("admin_dashboard")
        self.playwright = sync_playwright().start()
        self.addCleanup(self.playwright.stop)
        self.browser = self.playwright.chromium.launch(headless=True,
            channel=os.environ.get("PLAYWRIGHT_CHANNEL", "msedge"))
        self.addCleanup(self.browser.close)
        self.context = self.browser.new_context(service_workers="block")
        self.page = self.context.new_page()

    def screenshot(self, name):
        output = Path(tempfile.gettempdir()) / "gestion-boutique-ui-corrections"
        output.mkdir(exist_ok=True)
        self.page.screenshot(path=str(output / name), full_page=False)
        print(f"Capture : {output / name}", flush=True)

    def goto(self, route):
        response = self.page.goto(self.live_server_url + route, wait_until="networkidle")
        self.assertEqual(response.status, 200)

    def test_home_without_photo_badges_desktop_and_android(self):
        android = self.browser.new_context(**self.playwright.devices["Pixel 5"], service_workers="block")
        for page in (self.page, android.new_page()):
            with self.subTest(android=page != self.page):
                page.goto(self.live_server_url, wait_until="networkidle")
                self.assertEqual(page.locator('.shop-hero [class*="floating-"]').count(), 0)
                self.assertEqual(page.locator('.shop-hero .bi-lightning-fill, .shop-hero-eyebrow').count(), 0)
                self.assertTrue(page.locator('.shop-hero-product img').evaluate('e => e.complete && e.naturalWidth > 0'))
                self.assertEqual(page.locator('.shop-hero-actions a').count(), 2)
                self.assertFalse(page.evaluate('document.documentElement.scrollWidth > innerWidth'))
                output = Path(tempfile.gettempdir()) / 'gestion-boutique-ui-corrections'
                output.mkdir(exist_ok=True)
                page.screenshot(path=str(output / ('home-android.png' if page != self.page else 'home-desktop.png')))
                if page != self.page:
                    self.assertTrue(page.locator('.site-menu-toggle').is_visible())
        android.close()

    def test_four_visible_password_levels(self):
        self.goto('/accounts/register/')
        self.page.locator('#id_first_name').fill('Amina')
        self.page.locator('#id_last_name').fill('Diallo')
        self.page.locator('[data-step="1"] .next-step').click()
        self.page.locator('#id_birth_day').select_option('15')
        self.page.locator('#id_birth_month').select_option('6')
        self.page.locator('#id_birth_year').select_option('2000')
        self.page.locator('label[for="genre_homme"]').click()
        self.page.locator('[data-step="2"] .next-step').click()
        meter = self.page.locator('.account-password-meter')
        self.assertTrue(meter.is_visible())
        for value, score, label, color in [
            ('abc', 1, 'Très faible', 'rgb(220, 53, 69)'),
            ('abcdefgh2', 2, 'Moyen', 'rgb(224, 168, 0)'),
            ('MyVaried482!', 3, 'Bon', 'rgb(25, 135, 84)'),
            ('Unique-Secret-482!Long', 4, 'Robuste', 'rgb(13, 110, 253)'),
        ]:
            with self.subTest(level=score):
                self.page.locator('#id_password1').fill(value)
                self.page.wait_for_timeout(250)  # Fin de la transition CSS de 200 ms.
                self.assertEqual(meter.get_attribute('aria-valuenow'), str(score))
                self.assertTrue(self.page.locator('#password-feedback').inner_text().startswith(label + ' —'))
                self.screenshot(f'password-level-{score}.png')
                for index in range(score):
                    self.assertEqual(meter.locator('span').nth(index).evaluate('e => getComputedStyle(e).backgroundColor'), color)
        # Modifier l'identité doit recalculer un mot de passe devenu prévisible.
        self.page.locator('#id_email').fill('unique@example.test')
        self.assertEqual(meter.get_attribute('aria-valuenow'), '1')
        self.page.locator('#id_password1').fill('')
        self.assertEqual(meter.get_attribute('aria-valuenow'), '0')

    def test_category_original_cover_and_breadcrumb(self):
        for width in (390, 1280):
            with self.subTest(width=width):
                self.page.set_viewport_size({'width': width, 'height': 900})
                self.goto('/categories/')
                image = self.page.locator('.shop-category-tile img').first
                self.assertTrue(image.evaluate('e => e.complete && e.naturalWidth > 0'))
                self.assertEqual(image.evaluate('e => getComputedStyle(e).objectFit'), 'cover')
                self.screenshot(f'categories-{width}.png')
                self.goto('/categories/' + self.category.slug + '/')
                self.assertTrue(self.page.locator('.shop-breadcrumb').is_visible())
                self.assertTrue(self.page.locator('.shop-filter-panel').is_visible())
                self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth'))

    def test_security_visible_link_and_review_suspend_reactivate(self):
        self.context.add_cookies([{'name': 'sessionid', 'value': self.session_key, 'url': self.live_server_url}])
        self.goto(self.dashboard_url)
        link = self.page.locator('.control-header').get_by_role('link', name='Live Security')
        self.assertEqual(link.count(), 1)
        self.assertTrue(link.is_visible())
        link.click()
        self.page.wait_for_url('**/dashboard/security/')
        self.screenshot('live-security.png')
        self.page.get_by_role('button', name='Marquer comme examinée').first.click()
        self.page.locator('#security-event').select_option(str(self.event.pk))
        self.assertEqual(self.page.locator('#security-user').input_value(), str(self.customer.pk))
        self.page.locator('#security-reason').fill('Vérification manuelle de test')
        form = self.page.locator('form').filter(has=self.page.locator('input[value="suspend"]'))
        form.locator('button').click()
        reactivate = self.page.locator('form').filter(has=self.page.locator('input[value="reactivate"]'))
        self.assertTrue(reactivate.is_visible())
        reactivate.locator('input[name="reason"]').fill('Identité vérifiée en test')
        reactivate.locator('button').click()
        self.assertEqual(self.page.locator('input[value="reactivate"]').count(), 0)
        self.assertIn('account_reactivated', self.page.locator('#security-events').inner_text())
