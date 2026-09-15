import json
from pathlib import Path

from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from categories.models import Category
from products.models import Product


class HomeHeroTests(TestCase):
    def test_home_uses_dedicated_static_marketing_asset(self):
        category = Category.objects.create(nom="Mode")
        Product.objects.create(categorie=category, nom="Produit image", prix=1000, stock=1, vedette=True, image="products/profile-looking.jpg")
        response = self.client.get(reverse("home"))
        self.assertContains(response, "/static/images/boutique_hero_bg.png")
        hero = response.content.decode().split('<section class="shop-hero"', 1)[1].split('</section>', 1)[0]
        self.assertNotIn("products/profile-looking.jpg", hero)
        self.assertNotContains(response, "hero_product")

    def test_profile_photo_cannot_change_home_hero(self):
        user = User.objects.create_user("ousby", password="secret123")
        user.profile.photo = "profiles/avatar.png"
        user.profile.save()
        response = self.client.get(reverse("home"))
        self.assertContains(response, "/static/images/boutique_hero_bg.png")
        self.assertNotContains(response, "profiles/avatar.png")


class OfflinePwaTests(TestCase):
    def test_manifest_accessible(self):
        manifest_path = Path("static/manifest.webmanifest")
        self.assertTrue(manifest_path.exists())
        content = manifest_path.read_text(encoding="utf-8")
        self.assertIn("Gestion Boutique", content)
        self.assertIn('"short_name"', content)

    def test_service_worker_accessible(self):
        sw_path = Path("static/service-worker.js")
        self.assertTrue(sw_path.exists())
        content = sw_path.read_text(encoding="utf-8")
        self.assertIn("CACHE_NAME", content)
        self.assertIn("caches.open", content)

    def test_base_has_offline_manager_script(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "/static/js/offline-manager.js")
        self.assertContains(response, "offline-manager")

    def test_offline_payload_for_anonymous_user(self):
        response = self.client.get(reverse("offline_sync_payload"), HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertTrue(body.get("ok"))
        payload = body.get("payload")
        self.assertEqual(payload.get("scope"), "public")
        self.assertNotIn("user", payload)
        self.assertEqual(payload.get("version"), "1")

    def test_offline_payload_for_authenticated_user(self):
        user = User.objects.create_user("client", password="secret123")
        self.client.login(username="client", password="secret123")

        category = Category.objects.create(nom="Mode")
        Product.objects.create(categorie=category, nom="Produit", prix=1000, stock=10, actif=True, vedette=True)
        response = self.client.get(reverse("offline_sync_payload"), HTTP_ACCEPT="application/json")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        payload = body.get("payload") or {}

        self.assertEqual(payload.get("scope"), "authenticated")
        self.assertIn("user", payload)
        self.assertEqual(payload["user"].get("id"), user.id)
        self.assertEqual(payload["user"].get("role"), "client")

        # Vérifier que les données métiers essentielles sont présentes et propres
        self.assertTrue(payload.get("categories"))
        self.assertTrue(payload.get("products"))
        self.assertNotIn("password", json.dumps(payload))
        self.assertNotIn("secret", json.dumps(payload).lower())

    def test_offline_sync_last_sync_field_present(self):
        response = self.client.get(reverse("offline_sync_payload"), HTTP_ACCEPT="application/json")
        body = response.json()
        payload = body.get("payload")
        self.assertIn("updated_at", payload)
