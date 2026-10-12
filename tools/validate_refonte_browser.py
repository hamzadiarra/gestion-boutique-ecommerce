"""Exécuter : python manage.py test tools.validate_refonte_browser --noinput.
Base Django isolée, produits de test uniquement ; aucune écriture dans la base réelle.
Playwright et Chromium doivent être installés dans l'environnement de validation.
"""
from pathlib import Path
import os
from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from playwright.sync_api import sync_playwright
from categories.models import Category
from products.models import Product
from cart.models import Cart, CartItem


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ResponsiveBrowserTests(StaticLiveServerTestCase):
    def test_responsive_and_interactions(self):
        category = Category.objects.create(nom="Collection test")
        product = Product.objects.create(categorie=category, nom="Samsung Galaxy test", prix=150000, prix_promotion=120000, stock=8)
        user = User.objects.create_user("browser-client", password="Local-test-482!")
        cart = Cart.objects.create(utilisateur=user)
        CartItem.objects.create(panier=cart, produit=product, quantite=2, prix=120000)
        admin = User.objects.create_user("browser-admin", password="Local-test-483!")
        admin.profile.role = "admin"
        admin.profile.save()
        sessions = {}
        for account in (user, admin):
            client = Client(); client.force_login(account)
            sessions[account.pk] = client.session.session_key
        output = Path(os.environ.get("BROWSER_SCREENSHOT_DIR", "docs/validation"))
        output.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel=os.environ.get("PLAYWRIGHT_CHANNEL", "msedge"))
            context = browser.new_context(service_workers="block")
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            # L'affichage public et l'inscription restent anonymes.
            routes = ["/", "/products/", "/categories/", f"/categories/{category.slug}/", f"/products/{product.slug}/", "/accounts/register/"]
            for width in (320, 375, 390, 768, 1024, 1280, 1920):
                page.set_viewport_size({"width": width, "height": 900})
                for route in routes:
                    page.goto(self.live_server_url + route, wait_until="networkidle")
                    self.assertTrue(page.locator(".site-header").is_visible())
                    overflow = page.evaluate("document.documentElement.scrollWidth > innerWidth + 1")
                    details = page.evaluate("[...document.querySelectorAll('body *')].filter(e => e.getBoundingClientRect().right > innerWidth + 2 && getComputedStyle(e).position !== 'absolute').slice(0,8).map(e => e.className)")
                    self.assertFalse(overflow, f"{width}px {route}: {details}")
                    if width < 1200:
                        self.assertTrue(page.locator(".site-menu-toggle").is_visible(), f"Hamburger {width}")
                    page.evaluate("scrollTo({top: 500, behavior: 'instant'})")
                    page.wait_for_function("Math.abs(document.querySelector('.site-header').getBoundingClientRect().top) < 1")
                    if route == "/" and width in (390, 1280):
                        page.evaluate("scrollTo({top: 0, behavior: 'instant'})")
                        page.screenshot(path=str(output / f"home-{width}.png"), full_page=False)
                print(f"PUBLIC {width}px : 6 pages OK", flush=True)
            page.set_viewport_size({"width": 390, "height": 844})
            page.goto(self.live_server_url + "/products/", wait_until="networkidle")
            page.locator(".site-menu-toggle").click()
            self.assertTrue(page.locator("#navbarMenu").is_visible())
            page.locator(".site-menu-toggle").click()
            search = page.locator('.shop-filter-panel input[name="q"]')
            search.fill("samsng")
            page.wait_for_selector(".shop-filter-search .product-suggestion")
            self.assertIn("120", page.locator(".shop-filter-search .product-suggestion").inner_text())
            search.press("ArrowDown")
            search.press("Enter")
            page.wait_for_url("**/products/samsung-galaxy-test/")
            page.locator("[data-history-back]").click()
            page.wait_for_url("**/products/")
            page.emulate_media(reduced_motion="reduce")
            page.goto(self.live_server_url, wait_until="networkidle")
            self.assertEqual(page.locator(".shop-hero-blue-shape").evaluate("e => getComputedStyle(e).animationName"), "none")
            # Formulaire en trois étapes et quatre niveaux de robustesse.
            page.goto(self.live_server_url + "/accounts/register/", wait_until="networkidle")
            for value, score in [("abc", "1"), ("abcdefgh2", "2"), ("MyVaried482!", "3"), ("Unique-Hamza-482!Long", "4")]:
                page.locator("#id_password1").evaluate("(e, value) => { e.value=value; e.dispatchEvent(new Event('input')); }", value)
                self.assertEqual(page.locator(".account-password-meter").get_attribute("aria-valuenow"), score)
            for account, paths in [(user, ["/cart/", "/orders/create/", "/orders/my-orders/"]), (admin, ["/dashboard/security/"])]:
                context.add_cookies([{"name": "sessionid", "value": sessions[account.pk], "url": self.live_server_url}])
                for width in (320, 375, 390, 768, 1024, 1280, 1920):
                    page.set_viewport_size({"width": width, "height": 900})
                    for route in paths:
                        response = page.goto(self.live_server_url + route, wait_until="networkidle")
                        self.assertEqual(response.status, 200, route)
                        self.assertFalse(page.evaluate("document.documentElement.scrollWidth > innerWidth + 1"), f"{width}px {route}")
                        if width >= 1200:
                            for link in page.locator(".site-nav > .nav-item > .nav-link").all():
                                if link.is_visible():
                                    box = link.bounding_box()
                                    self.assertLessEqual(box["x"] + box["width"], width + 1, f"Navigation masquée : {route} {width}")
                        summary = page.locator(".shop-order-summary, .checkout-summary")
                        if summary.count():
                            self.assertEqual(summary.evaluate("e => getComputedStyle(e).position"), "sticky" if width >= 992 else "static")
                        if route == "/orders/create/":
                            self.assertEqual(page.locator("[data-checkout-step]").count(), 5)
                            self.assertEqual(page.locator("#adresse").input_value(), "")
                            self.assertEqual(page.locator("#ville").input_value(), "")
                            if width < 992:
                                self.assertEqual(page.locator(".shop-assistant").evaluate("e => getComputedStyle(e).position"), "relative")
                            else:
                                page.locator(".checkout-main").evaluate("e => { const spacer=document.createElement('div'); spacer.style.height='1400px'; e.append(spacer); }")
                                page.evaluate("scrollTo({top: 500, behavior: 'instant'})")
                                box = summary.bounding_box()
                                header = page.locator(".site-header").bounding_box()
                                self.assertGreaterEqual(box["y"], header["height"])
                                self.assertLessEqual(box["y"], header["height"] + 18)
                            if width == 390:
                                page.screenshot(path=str(output / "checkout-390.png"), full_page=True)
                    print(f"AUTH {account.username} {width}px : OK", flush=True)
            self.assertEqual(errors, [])
            browser.close()
