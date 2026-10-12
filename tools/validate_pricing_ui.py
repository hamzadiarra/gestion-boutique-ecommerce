"""Audit navigateur des tarifs, base de test uniquement."""
import os
import tempfile
from pathlib import Path
from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from playwright.sync_api import sync_playwright


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PricingBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        self.driver = User.objects.create_user("pricing-courier")
        self.driver.profile.role = "livreur"
        self.driver.profile.save()
        self.admin = User.objects.create_user("pricing-admin", is_superuser=True)
        self.sessions = {}
        for name, user in [("livreur", self.driver), ("administrateur", self.admin)]:
            client = Client()
            client.force_login(user)
            self.sessions[name] = client.session.session_key

    def test_roles_header_footer_and_mobile_layout(self):
        output = Path(tempfile.gettempdir()) / "gestion-boutique-pricing-audit"
        output.mkdir(exist_ok=True)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel=os.getenv("PLAYWRIGHT_CHANNEL", "msedge"), headless=True)
            try:
                for role in self.sessions:
                    for width in (1366, 390):
                        context = browser.new_context(viewport={"width": width, "height": 900}, service_workers="block")
                        context.add_cookies([{"name": "sessionid", "value": self.sessions[role], "url": self.live_server_url}])
                        page = context.new_page()
                        response = page.goto(self.live_server_url+"/orders/livraisons/tarifs/", wait_until="networkidle")
                        self.assertEqual(response.status, 200)
                        self.assertEqual(page.locator("header.site-header").count(), 1)
                        self.assertEqual(page.locator("footer.site-footer").count(), 1)
                        self.assertEqual(page.locator("header.site-header:visible").count(), 1)
                        self.assertEqual(page.locator("footer.site-footer:visible").count(), 1)
                        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"))
                        forms = page.locator('main.delivery-shell form[method="post"]')
                        self.assertEqual(forms.count(), 1 if role == "livreur" else 0)
                        page.screenshot(path=str(output / f"{role}-{width}.png"), full_page=True)
                        print(f"BROWSER {role} {width}px: one header, one footer; proposal forms={forms.count()}; screenshot={output / f'{role}-{width}.png'}")
                        context.close()
            finally:
                browser.close()

    def test_propose_approve_refuse_and_read_history(self):
        from orders.pricing_models import TarifLivreur
        from playwright.sync_api import expect
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel=os.getenv("PLAYWRIGHT_CHANNEL", "msedge"), headless=True)
            try:
                context = browser.new_context(viewport={"width": 390, "height": 900}, service_workers="block")
                context.add_cookies([{"name": "sessionid", "value": self.sessions["livreur"], "url": self.live_server_url}])
                page = context.new_page()
                page.goto(self.live_server_url+"/orders/livraisons/tarifs/", wait_until="networkidle")
                for mode, amount in [("standard", "1200"), ("express", "2500")]:
                    page.get_by_role("link", name="Proposer un tarif", exact=True).click()
                    page.locator('#id_mode').select_option(mode)
                    page.locator('#id_zone').fill("Bamako")
                    page.locator('#id_montant').fill(amount)
                    with page.expect_navigation():
                        page.get_by_role("button", name="Soumettre à l’administration").click()
                    expect(page.get_by_text("Votre proposition a été envoyée", exact=False)).to_be_visible()
                context.clear_cookies()
                context.add_cookies([{"name": "sessionid", "value": self.sessions["administrateur"], "url": self.live_server_url}])
                page.goto(self.live_server_url+"/orders/livraisons/tarifs/", wait_until="networkidle")
                offer_ids = sorted(int(value.removeprefix("tarif-")) for value in page.locator(".pricing-offer").evaluate_all("items => items.map(e => e.id)"))
                for offer_id, action, reason in [(offer_ids[0], "Approuver", "Tarif conforme au secteur"), (offer_ids[1], "Refuser", "Montant express à réexaminer")]:
                    card = page.locator(f'#tarif-{offer_id}')
                    card.get_by_label("Motif de la décision").fill(reason)
                    with page.expect_navigation():
                        card.get_by_role("button", name=action, exact=True).click()
                    card = page.locator(f'#tarif-{offer_id}')
                    card.locator('summary').click()
                    expect(card.get_by_text(reason, exact=True)).to_be_visible()
                    expect(card.locator('.pricing-history')).to_contain_text("pricing-admin")
                output = Path(tempfile.gettempdir()) / "gestion-boutique-pricing-audit"
                output.mkdir(exist_ok=True)
                for width in (320,375,390,430,768,820,1024,1280,1440,1920):
                    page.set_viewport_size({"width": width, "height": 900})
                    self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), str(width))
                    page.screenshot(path=str(output / f"decisions-{width}.png"), full_page=True)
            finally:
                browser.close()
        # L'ORM synchrone s'utilise une fois la boucle Playwright arrêtée.
        for offer, status in zip(TarifLivreur.objects.order_by("pk"), ("approuve", "refuse")):
            self.assertEqual(offer.statut, status)
            self.assertEqual(offer.historique.get(statut=status).acteur, self.admin)
