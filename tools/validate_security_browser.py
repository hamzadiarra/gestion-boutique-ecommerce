"""Edge smoke test on synthetic data, with real POST forms and CSRF tokens."""
from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse
from playwright.sync_api import sync_playwright
from categories.models import Category
from products.models import Product


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SecurityBrowserTests(StaticLiveServerTestCase):
    def test_login_cart_and_logout_on_mobile_and_desktop(self):
        cache.clear()
        self.addCleanup(cache.clear)
        user = User.objects.create_user("browser-security", password="Synthetic-test-918!")
        category = Category.objects.create(nom="Test sécurité")
        product = Product.objects.create(categorie=category, nom="Article test", prix=1000, stock=8)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="msedge", headless=True)
            try:
                for width in (390, 1280):
                    with self.subTest(width=width):
                        context = browser.new_context(viewport={"width": width, "height": 900}, service_workers="block")
                        page = context.new_page()
                        errors = []
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        page.goto(self.live_server_url + reverse("product_detail", args=[product.slug]), wait_until="networkidle")
                        page.locator("a.shop-buy-button").click()
                        page.locator('[name="username"]').fill(user.username)
                        page.locator('[name="password"]').fill("Synthetic-test-918!")
                        with page.expect_navigation():
                            page.locator('form').filter(has=page.locator('[name="password"]')).locator('button[type="submit"]').click()
                        self.assertTrue(page.url.endswith(reverse("product_detail", args=[product.slug])))
                        with page.expect_navigation():
                            page.locator('.shop-buy-form button[type="submit"]').click()
                        self.assertEqual(page.locator('.shop-quantity-small > span').inner_text(), '1')
                        with page.expect_navigation():
                            page.get_by_role("button", name="Augmenter", exact=True).click()
                        self.assertEqual(page.locator('.shop-quantity-small > span').inner_text(), '2')
                        with page.expect_navigation():
                            page.get_by_role("button", name="Diminuer", exact=True).click()
                        self.assertEqual(page.locator('.shop-quantity-small > span').inner_text(), '1')
                        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), width + 1)
                        with page.expect_navigation():
                            page.locator('button.shop-remove-link').click()
                        self.assertEqual(page.locator('.shop-cart-item').count(), 0)
                        page.wait_for_load_state("networkidle")
                        page.evaluate("""async (scope) => {
                            const db = await new Promise((resolve,reject) => { const r=indexedDB.open('gestion-boutique-offline',1);r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error); });
                            await new Promise((resolve,reject) => {const tx=db.transaction('orders','readwrite');tx.objectStore('orders').put({id:'security-fixture',scopeKey:scope});tx.oncomplete=resolve;tx.onerror=reject;});db.close();
                        }""", str(user.pk))
                        if width < 992:
                            page.locator('[data-bs-target="#navbarMenu"]').click()
                        page.locator('.site-account-link').click()
                        with page.expect_navigation():
                            page.locator('form[action$="/logout/"] button').click()
                        page.wait_for_load_state("networkidle")
                        self.assertEqual(page.locator('body').get_attribute('data-user-authenticated'), '0')
                        count = page.evaluate("""async (scope) => {
                            const db=await new Promise(resolve=>{const r=indexedDB.open('gestion-boutique-offline',1);r.onsuccess=()=>resolve(r.result);});
                            const rows=await new Promise(resolve=>{const r=db.transaction('orders').objectStore('orders').getAll();r.onsuccess=()=>resolve(r.result);});db.close();return rows.filter(r=>r.scopeKey===scope).length;
                        }""", str(user.pk))
                        self.assertEqual(count, 0)
                        self.assertEqual(errors, [])
                        print(f"Edge {width}px: login, CSRF cart POST, logout, private cache purge OK", flush=True)
                        context.close()
            finally:
                browser.close()

    def test_service_worker_install_uses_anonymous_shell(self):
        user = User.objects.create_user("private-shell-marker")
        client = Client(); client.force_login(user)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="msedge", headless=True)
            try:
                context = browser.new_context(service_workers="allow")
                context.add_cookies([{"name": "sessionid", "value": client.session.session_key, "url": self.live_server_url}])
                page = context.new_page()
                page.goto(self.live_server_url + "/", wait_until="networkidle")
                result = page.evaluate("""async () => {
                    const registration=await navigator.serviceWorker.register('/static/service-worker.js');
                    const worker=registration.installing || registration.waiting || registration.active;
                    if(worker.state!=='activated') await new Promise((resolve,reject)=>{
                        const timer=setTimeout(()=>reject(Error('worker timeout')),15000);
                        worker.addEventListener('statechange',()=>{if(worker.state==='activated'){clearTimeout(timer);resolve();}});
                    });
                    const cache=await caches.open('gestion-boutique-shell-v5-private-safe');
                    const shell=await cache.match('/');
                    return {html:shell?await shell.text():null,keys:(await cache.keys()).map(r=>new URL(r.url).pathname)};
                }""")
                self.assertIsNotNone(result["html"])
                self.assertNotIn(user.username, result["html"])
                self.assertIn('data-user-authenticated="0"', result["html"])
                self.assertNotIn("/offline/sync/", result["keys"])
                print("Edge: authenticated install stores anonymous shell only", flush=True)
            finally:
                browser.close()
