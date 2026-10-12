"""Browser checks against a temporary Django test database, never local db.sqlite3.
Run: python manage.py test tools.validate_delivery_proof_browser --noinput
"""
import os
from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from playwright.sync_api import sync_playwright
from orders.models import Order
from orders.delivery_services import initialiser_livraison, affecter_livreur, changer_statut_livraison
from orders.proof_models import PreuveLivraison
from orders.pricing_services import proposer_tarif, decider_tarif


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DeliveryBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        self.customer = User.objects.create_user("browser-customer")
        self.driver = User.objects.create_user("browser-driver")
        self.driver.profile.role = "livreur"
        self.driver.profile.save()
        self.admin = User.objects.create_user("browser-admin", is_superuser=True)
        self.sessions = {}
        for user in (self.customer, self.driver, self.admin):
            client = Client()
            client.force_login(user)
            self.sessions[user.pk] = client.session.session_key

    def start_browser(self):
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(channel=os.getenv("PLAYWRIGHT_CHANNEL", "msedge"), headless=True)
        self.addCleanup(self.stop_browser)

    def stop_browser(self):
        if self.pw is not None:
            self.browser.close()
            self.pw.stop()
            self.pw = None

    def login(self, context, user):
        context.add_cookies([{"name": "sessionid", "value": self.sessions[user.pk], "url": self.live_server_url}])

    def test_canvas_desktop_android_iphone_emulation(self):
        deliveries = []
        for _ in range(3):
            order = Order.objects.create(utilisateur=self.customer, statut="confirmee", adresse_livraison="Rue 1", ville_livraison="Bamako")
            delivery = initialiser_livraison(order, self.admin)
            affecter_livreur(delivery.pk, self.driver.pk, self.admin)
            for state, actor in [("acceptee", self.driver), ("prete", self.admin), ("en_route", self.driver), ("arrive", self.driver), ("attente_signature", self.driver)]:
                changer_statut_livraison(delivery.pk, state, actor)
            deliveries.append(delivery)
        self.start_browser()
        for device, delivery in zip((None, "Pixel 5", "iPhone 13"), deliveries):
            with self.subTest(device=device):
                context = self.browser.new_context(**(self.pw.devices[device] if device else {}), service_workers="block")
                self.login(context, self.driver)
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(self.live_server_url+f"/orders/livraisons/{delivery.pk}/", wait_until="networkidle")
                form = page.locator("#signature-form")
                form.locator('[name="receptionnaire"]').fill("Fatou Test")
                form.locator('[name="information_acceptee"]').check()
                form.locator('button:not([type="button"])').click()
                self.assertIn("doit signer", page.locator("#signature-error").inner_text())
                canvas = page.locator("#signature-canvas")
                if device:
                    canvas.evaluate("""c => {
                        const r=c.getBoundingClientRect();
                        const send=(type,x,y)=>c.dispatchEvent(new PointerEvent(type,{pointerId:1,pointerType:'touch',clientX:r.left+x,clientY:r.top+y,bubbles:true}));
                        // Synthetic capture is not available: temporarily stub capture for synthetic input only.
                        c.setPointerCapture=()=>{};
                        send('pointerdown',30,100);send('pointermove',80,40);send('pointermove',130,140);send('pointermove',200,60);send('pointerup',200,60);
                    }""")
                else:
                    box = canvas.bounding_box()
                    page.mouse.move(box["x"]+30, box["y"]+100)
                    page.mouse.down()
                    page.mouse.move(box["x"]+80, box["y"]+40, steps=5)
                    page.mouse.move(box["x"]+180, box["y"]+140, steps=5)
                    page.mouse.up()
                with page.expect_navigation():
                    form.locator('button:not([type="button"])').click()
                self.assertIn("Preuve de remise", page.locator("body").inner_text())
                self.assertEqual(errors, [])
                self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"))
                context.close()

    def test_checkout_offer_updates_total_and_posts_signed_quote(self):
        from categories.models import Category
        from products.models import Product
        from cart.models import Cart, CartItem
        category = Category.objects.create(nom="Test")
        product = Product.objects.create(categorie=category, nom="Article", prix=1000, stock=3)
        cart = Cart.objects.create(utilisateur=self.customer)
        CartItem.objects.create(panier=cart, produit=product, prix=1000, quantite=1)
        tariff = proposer_tarif(self.driver, "standard", "1200", zone="Bamako")
        decider_tarif(tariff.pk, self.admin, "approuve", "Tarif approuvé")
        self.start_browser()
        context = self.browser.new_context(service_workers="block")
        self.login(context, self.customer)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(self.live_server_url+"/orders/create/", wait_until="networkidle")
        page.locator("#adresse").fill("Rue 1")
        page.locator("#ville").fill("Bamako")
        page.locator('[data-checkout-panel="1"] .checkout-next').click()
        page.locator("#refresh-offers").click()
        page.wait_for_function("document.getElementById('courier-offer').options.length === 2")
        page.locator("#courier-offer").select_option(str(tariff.pk))
        self.assertIn("200", page.locator("#checkout-fee").inner_text())
        self.assertTrue(page.locator("#delivery-quote").input_value())
        for n in (2, 3, 4):
            page.locator(f'[data-checkout-panel="{n}"] .checkout-next').click()
        with page.expect_navigation():
            page.locator('#checkout-form button[type="submit"]').click()
        self.stop_browser()
        order = Order.objects.get(utilisateur=self.customer)
        self.assertEqual(order.frais_livraison, 1200)
        self.assertEqual(order.payment.montant, 2200)
        self.assertEqual(errors, [])
