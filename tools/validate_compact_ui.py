"""Capture/measure all primary pages on an isolated test database.
UI_AUDIT_PHASE=before records; after additionally fails on layout defects.
Artifacts: %TEMP%/gestion-boutique-compact-ui/{before,after}.
"""
import io
import json
import os
import tempfile
from pathlib import Path
from PIL import Image
from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.files.base import ContentFile
from django.test import Client, override_settings
from django.urls import reverse
from playwright.sync_api import sync_playwright
from categories.models import Category
from products.models import Product
from cart.models import Cart, CartItem
from orders.models import Order, OrderItem
from orders.delivery_services import initialiser_livraison, affecter_livreur
from accounts.security_models import SecurityEvent
from payments.models import Payment


WIDTHS = (320, 375, 390, 430, 768, 820, 1024, 1280, 1440, 1920)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CompactUIBrowserTests(StaticLiveServerTestCase):
    def test_all_primary_pages(self):
        phase = os.getenv("UI_AUDIT_PHASE", "after")
        output = Path(tempfile.gettempdir()) / "gestion-boutique-compact-ui" / phase
        output.mkdir(parents=True, exist_ok=True)
        media = tempfile.TemporaryDirectory(prefix="boutique-ui-fixtures-")
        self.addCleanup(media.cleanup)
        setting = override_settings(MEDIA_ROOT=media.name)
        setting.enable(); self.addCleanup(setting.disable)
        users, sessions = {}, {}
        for role in ("client", "admin", "vendeur", "livreur", "comptable"):
            user = User.objects.create_user("ui-"+role)
            user.profile.role = role; user.profile.save()
            users[role] = user
            client = Client(); client.force_login(user)
            sessions[role] = client.session.session_key
        category = Category.objects.create(nom="Accessoires et maison")
        data = io.BytesIO(); Image.new("RGB", (640, 480), "#b8ccd9").save(data, "JPEG")
        category.image.save("categorie.jpg", ContentFile(data.getvalue()))
        products = []
        for name in ("Lampe de bureau rechargeable", "Casque audio sans fil", "Sac de voyage compact", "Batterie portable 20000 mAh"):
            product = Product.objects.create(categorie=category, nom=name, prix=12500, stock=12, description="Un article pratique au quotidien.")
            product.image.save(f"produit-{product.pk}.jpg", ContentFile(data.getvalue()))
            products.append(product)
        cart = Cart.objects.create(utilisateur=users["client"])
        CartItem.objects.create(panier=cart, produit=products[0], prix=12500, quantite=2)
        order = Order.objects.create(utilisateur=users["client"], statut="confirmee", adresse_livraison="Rue 125, quartier central", ville_livraison="Bamako", frais_livraison=1200)
        OrderItem.objects.create(commande=order, produit=products[0], prix=12500, quantite=2)
        Payment.objects.create(commande=order, montant=26200, methode="wave", statut="en_attente")
        delivery = initialiser_livraison(order, users["admin"])
        affecter_livreur(delivery.pk, users["livreur"].pk, users["admin"])
        SecurityEvent.objects.create(kind="login_failed", subject=users["client"], alert=True, detail="Échecs répétés : vérifier le contexte avant toute décision.")
        routes = [
            ("accueil", "", reverse("home")), ("boutique", "", reverse("product_list")),
            ("categories", "", reverse("category_list")), ("produit", "", reverse("product_detail", args=[products[0].slug])),
            ("connexion", "", reverse("login")), ("inscription", "", reverse("register")),
            ("panier", "client", reverse("cart_detail")), ("checkout", "client", reverse("create_order")),
            ("profil", "client", reverse("profile")), ("commandes", "client", reverse("my_orders")),
            ("livraison", "client", reverse("livraison_detail", args=[delivery.pk])),
            ("livraisons", "admin", reverse("boutique_livraisons")),
            ("tarifs-admin", "admin", reverse("livraison_tarifs")), ("tarifs-livreur", "livreur", reverse("livraison_tarifs")),
            ("preuves", "admin", reverse("livraison_supervision")), ("security", "admin", reverse("security_dashboard")),
            ("dashboard-admin", "admin", reverse("admin_dashboard")), ("dashboard-vendeur", "vendeur", reverse("vendeur_dashboard")),
            ("dashboard-livreur", "livreur", reverse("livreur_dashboard")), ("dashboard-comptable", "comptable", reverse("comptable_dashboard")),
        ]
        selected_pages = set(filter(None, os.getenv("UI_AUDIT_PAGES", "").split(",")))
        if selected_pages:
            routes = [route for route in routes if route[0] in selected_pages]
        report, defects = [], []
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, channel=os.getenv("PLAYWRIGHT_CHANNEL", "msedge"))
            try:
                context = browser.new_context(service_workers="block", reduced_motion="reduce")
                page = context.new_page()
                page.set_default_timeout(15000)
                for width in tuple(map(int, os.getenv("UI_AUDIT_WIDTHS", ",".join(map(str, WIDTHS))).split(","))):
                    page.set_viewport_size({"width": width, "height": 900})
                    for name, role, route in routes:
                        context.clear_cookies()
                        if role:
                            context.add_cookies([{"name": "sessionid", "value": sessions[role], "url": self.live_server_url}])
                        response = page.goto(self.live_server_url+route, wait_until="networkidle")
                        metrics = page.evaluate("""() => {
                            const header=document.querySelector('.site-header'), footer=document.querySelector('.site-footer');
                            const main=document.querySelector('#main-content'), title=main.querySelector('h1,h2');
                            const visible=e=>e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
                            const overflowing=[...main.querySelectorAll('*')].filter(e=>visible(e)&&e.getBoundingClientRect().right>innerWidth+2&&!e.closest('.table-responsive')&&getComputedStyle(e).position!=='absolute').slice(0,8).map(e=>e.tagName+'.'+String(e.className));
                            return {width:innerWidth,scrollWidth:document.documentElement.scrollWidth,headerCount:document.querySelectorAll('header.site-header').length,footerCount:document.querySelectorAll('footer.site-footer').length,headerHeight:header.getBoundingClientRect().height,titleGap:title?Math.round(title.getBoundingClientRect().top-header.getBoundingClientRect().bottom):null,footerGap:Math.round(footer.getBoundingClientRect().top-main.getBoundingClientRect().bottom),pageHeight:document.documentElement.scrollHeight,overflowing};
                        }""")
                        metrics.update(page=name, status=response.status)
                        page.screenshot(path=str(output / f"{name}-{width}.png"), full_page=width in (390,1280))
                        page.evaluate("scrollTo({top:500,behavior:'instant'})")
                        page.wait_for_timeout(80)
                        metrics["scrollY"] = page.evaluate("scrollY")
                        metrics["stickyTop"] = page.locator('.site-header').evaluate('e=>Math.round(e.getBoundingClientRect().top)')
                        if width<1200:
                            page.evaluate("scrollTo({top:0,behavior:'instant'})")
                            toggle=page.locator('.site-menu-toggle')
                            toggle.click()
                            page.wait_for_timeout(400)
                            metrics["menuVisible"] = page.locator('#navbarMenu').is_visible()
                            metrics["menuOverflow"] = page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                            toggle.click();page.wait_for_timeout(400)
                        report.append(metrics)
                        if response.status!=200 or metrics['scrollWidth']>width+1 or metrics['headerCount']!=1 or metrics['footerCount']!=1 or (metrics['scrollY']>100 and abs(metrics['stickyTop'])>1) or metrics.get('menuOverflow') or metrics.get('menuVisible') is False:
                            defects.append(metrics)
                    (output/('metrics-targeted.json' if selected_pages else 'metrics.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                    print(f"{phase.upper()} {width}px: {len(routes)} pages, {len(defects)} layout defects so far",flush=True)
            finally:
                browser.close()
        print(f"ARTIFACTS: {output}",flush=True)
        print('DEFECTS: '+json.dumps(defects,ensure_ascii=False),flush=True)
        if phase == "after":
            self.assertEqual(defects, [], 'See metrics.json and screenshots')

    def test_populated_charts_and_secondary_navigation(self):
        from dashboard.models import Vente
        category = Category.objects.create(nom="Graphiques")
        product = Product.objects.create(categorie=category, nom="Article graphique", prix=1000, stock=10)
        admin = User.objects.create_user("chart-admin", is_superuser=True)
        seller = User.objects.create_user("chart-seller")
        seller.profile.role = "vendeur"; seller.profile.save()
        Vente.objects.create(vendeur=seller, produit=product, quantite=1, prix_unitaire=1000, montant_total=1000)
        accountant = User.objects.create_user("chart-accountant")
        accountant.profile.role = "comptable"; accountant.profile.save()
        sessions = {}
        for role, user in [("admin", admin), ("comptable", accountant)]:
            client = Client(); client.force_login(user); sessions[role] = client.session.session_key
        from playwright.sync_api import expect
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, channel=os.getenv("PLAYWRIGHT_CHANNEL", "msedge"))
            try:
                context = browser.new_context(service_workers="block", reduced_motion="reduce")
                page = context.new_page()
                for role in sessions:
                    context.clear_cookies()
                    context.add_cookies([{"name":"sessionid", "value":sessions[role], "url":self.live_server_url}])
                    for width in WIDTHS:
                        page.set_viewport_size({"width":width, "height":900})
                        page.goto(self.live_server_url+reverse(role+"_dashboard"), wait_until="networkidle")
                        canvases = page.locator('.control-chart-wrap canvas')
                        self.assertGreater(canvases.count(), 0)
                        for canvas in canvases.all():
                            expect(canvas).to_be_visible()
                            self.assertGreater(canvas.bounding_box()["height"], 150)
                        for placeholder in page.locator('.control-chart-empty[hidden]').all():
                            expect(placeholder).to_be_hidden()
                        if role == "comptable":
                            page.locator('.section-navigation summary').click()
                            expect(page.get_by_role('link', name='Journal financier', exact=True)).to_be_visible()
                        self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
            finally:
                browser.close()
