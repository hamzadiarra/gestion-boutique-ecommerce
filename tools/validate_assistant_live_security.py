"""Edge validation on isolated test data; never modifies the local development DB."""
import json
import tempfile
from pathlib import Path
from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache
from django.test import Client, override_settings
from playwright.sync_api import sync_playwright
from accounts.security_models import SecurityEvent
from categories.models import Category
from products.models import Product

OUTPUT = Path(tempfile.gettempdir()) / "gestion-boutique-assistant-live-security"
WIDTHS = (320, 390, 768, 1280, 1920)


@override_settings(DEBUG=True, LIVE_SECURITY_ENABLED=True, PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AssistantLiveSecurityBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        cache.clear(); self.addCleanup(cache.clear)
        OUTPUT.mkdir(parents=True, exist_ok=True)
        self.category = Category.objects.create(nom="Chaussures", nom_en="Shoes")
        self.first = Product.objects.create(nom="Nike Alpha", marque="Nike", categorie=self.category, prix=12000, stock=3)
        self.second = Product.objects.create(nom="Nike Beta", marque="Nike", categorie=self.category, prix=18000, prix_promotion=15000, stock=2)
        Product.objects.create(nom="Nike masquée", marque="Nike", categorie=self.category, prix=1, actif=False)
        self.admin = User.objects.create_user("demo-admin", is_superuser=True)
        self.customer = User.objects.create_user("demo-client")
        self.cookies = {}
        for user in (self.admin, self.customer):
            client=Client(); client.force_login(user); self.cookies[user.pk]=client.session.session_key

    def assert_layout(self, page, width, panel=False):
        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), width+1)
        if panel:
            rect=page.locator('#shopAssistantPanel').bounding_box()
            self.assertGreaterEqual(rect['x'],0)
            self.assertLessEqual(rect['x']+rect['width'],width+1)
            self.assertGreaterEqual(rect['y'], page.locator('.site-header').bounding_box()['height'])
            self.assertLessEqual(rect['y']+rect['height'],1001)
        self.assertEqual(page.locator('.site-header').evaluate("e=>getComputedStyle(e).position"), 'sticky')

    def ask(self, page, question):
        page.locator('#shopAssistantInput').fill(question)
        with page.expect_response(lambda response: response.url.endswith('/assistant/ask/') and response.request.method=='POST') as reply:
            page.locator('#shopAssistantForm button[type="submit"]').click()
        response=reply.value
        self.assertEqual(response.status,200)
        page.wait_for_function("document.querySelector('#shopAssistantForm').getAttribute('aria-busy')==='false'")
        return response.json()

    def test_assistant_fr_en_responsive_and_real_product_context(self):
        records=[]
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=True)
            try:
                for language in ('fr','en'):
                    for width in WIDTHS:
                        with self.subTest(language=language,width=width):
                            context=browser.new_context(viewport={'width':width,'height':1000},service_workers='block',reduced_motion='reduce')
                            context.add_cookies([{'name':'django_language','value':language,'url':self.live_server_url}])
                            page=context.new_page(); errors=[]
                            page.on('pageerror',lambda error: errors.append(str(error)))
                            page.goto(self.live_server_url+'/',wait_until='networkidle')
                            self.assertTrue(page.locator('#shopAssistantPanel').is_hidden())
                            page.locator('#shopAssistantToggle').click()
                            first=self.ask(page,'Je cherche des chaussures' if language=='fr' else 'I am looking for shoes')
                            self.assertEqual(first['intent'],'RECHERCHER_PRODUIT')
                            second=self.ask(page,'Nike')
                            self.assertEqual([item['name'] for item in second['results']],['Nike Alpha','Nike Beta'])
                            result=self.ask(page,'Combien coûte le deuxième ?' if language=='fr' else 'How much is the second?')
                            self.assertEqual(result['results'][0]['id'],self.second.pk)
                            self.assertEqual(result['results'][0]['price'],'15000.00')
                            self.assertEqual(result['page_context'],'home')
                            self.assert_layout(page,width,panel=True)
                            page.screenshot(path=str(OUTPUT/f'assistant-{language}-{width}.png'))
                            page.locator('#shopAssistantInput').press('Escape')
                            self.assertTrue(page.locator('#shopAssistantPanel').is_hidden())
                            self.assertTrue(page.locator('#shopAssistantToggle').evaluate('e=>document.activeElement===e'))
                            page.goto(self.live_server_url+'/products/'+self.first.slug+'/',wait_until='networkidle')
                            page.locator('#shopAssistantToggle').click()
                            price=self.ask(page,'Quel est son prix ?' if language=='fr' else 'What is its price?')
                            self.assertEqual(price['results'][0]['id'],self.first.pk)
                            self.assertEqual(price['page_context'],'product')
                            self.assertEqual(errors,[])
                            records.append({'language':language,'width':width,'price':'15000.00','horizontalOverflow':False,'pageContext':'product'})
                            context.close()
                            print(f'Assistant {language} {width}px OK',flush=True)
            finally:
                browser.close()
        (OUTPUT/'assistant-metrics.json').write_text(json.dumps(records,indent=2),encoding='utf-8')

    def test_browser_serializes_submissions_and_recovers_network_error(self):
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=True)
            try:
                context=browser.new_context(viewport={'width':390,'height':1000},service_workers='block')
                page=context.new_page(); page.goto(self.live_server_url+'/',wait_until='networkidle')
                page.locator('#shopAssistantToggle').click()
                held=[]
                page.route('**/assistant/ask/',lambda route:held.append(route))
                page.locator('#shopAssistantInput').fill('bonjour')
                page.locator('#shopAssistantForm button[type="submit"]').click()
                page.wait_for_function("document.querySelector('#shopAssistantForm').getAttribute('aria-busy')==='true'")
                page.locator('#shopAssistantForm').evaluate('e=>{e.requestSubmit();e.requestSubmit();}')
                self.assertEqual(len(held),1)
                self.assertTrue(page.locator('#shopAssistantStatus').is_visible())
                held[0].abort()
                page.locator('.shop-assistant-retry').wait_for()
                original=held[0].request.post_data_json
                page.unroute('**/assistant/ask/')
                with page.expect_response(lambda response:response.url.endswith('/assistant/ask/')) as retry:
                    page.locator('.shop-assistant-retry').click()
                self.assertEqual(retry.value.status,200)
                self.assertEqual(retry.value.request.post_data_json['request_id'],original['request_id'])
                page.wait_for_function("document.querySelector('#shopAssistantForm').getAttribute('aria-busy')==='false'")
                self.assertEqual(page.locator('.shop-assistant-turn').count(),1)
            finally:
                browser.close()

    def test_security_responsive_review_suspend_reactivate_and_permissions(self):
        SecurityEvent.objects.all().delete()
        event=SecurityEvent.objects.create(kind='login_failed',subject=self.customer,alert=True,detail='Échecs de démonstration synthétiques')
        for index in range(35):
            SecurityEvent.objects.create(kind='login_failed',subject=self.customer,detail=f'Événement de test {index}')
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=True)
            try:
                for width in WIDTHS:
                    context=browser.new_context(viewport={'width':width,'height':1000},service_workers='block',reduced_motion='reduce')
                    context.add_cookies([{'name':'sessionid','value':self.cookies[self.admin.pk],'url':self.live_server_url}])
                    page=context.new_page(); errors=[]; page.on('pageerror',lambda error: errors.append(str(error)))
                    response=page.goto(self.live_server_url+'/dashboard/security/',wait_until='networkidle')
                    self.assertEqual(response.status,200)
                    self.assert_layout(page,width)
                    self.assertEqual(page.locator('#security-events > .security-event').count(),30)
                    link=page.locator('a[href="/dashboard/security/"]')
                    self.assertEqual(link.get_attribute('aria-current'),'page')
                    page.screenshot(path=str(OUTPUT/f'live-security-{width}.png'),full_page=True)
                    if width==1280:
                        page.goto(self.live_server_url+'/dashboard/security/?alerts=1',wait_until='networkidle')
                        with page.expect_navigation():
                            page.locator(f'form:has(input[name="action"][value="review"]):has(input[name="event_id"][value="{event.pk}"]) button').click()
                        page.locator('#security-event').select_option(str(event.pk))
                        page.locator('#security-reason').fill('Vérification locale avec compte de test')
                        with page.expect_navigation():
                            page.locator('form:has(input[name="action"][value="suspend"]) button[type="submit"]').click()
                        reactivate=page.locator('form:has(input[name="action"][value="reactivate"])')
                        self.assertEqual(reactivate.count(),1)
                        page.screenshot(path=str(OUTPUT/'live-security-suspension-1280.png'),full_page=True)
                        reactivate.locator('[name="reason"]').fill('Vérification terminée sur données de test')
                        with page.expect_navigation():
                            reactivate.locator('button').click()
                        self.assertEqual(page.locator('form:has(input[name="action"][value="reactivate"])').count(),0)
                    self.assertEqual(errors,[])
                    context.close(); print(f'Live Security {width}px OK',flush=True)
                customer=browser.new_context(service_workers='block')
                customer.add_cookies([{'name':'sessionid','value':self.cookies[self.customer.pk],'url':self.live_server_url}])
                page=customer.new_page(); page.goto(self.live_server_url+'/',wait_until='networkidle')
                self.assertEqual(page.locator('a[href="/dashboard/security/"]').count(),0)
                self.assertEqual(page.goto(self.live_server_url+'/dashboard/security/').status,403)
            finally:
                browser.close()

    def test_security_empty_state(self):
        SecurityEvent.objects.all().delete()
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=True)
            try:
                context=browser.new_context(viewport={'width':390,'height':1000},service_workers='block')
                context.add_cookies([{'name':'sessionid','value':self.cookies[self.admin.pk],'url':self.live_server_url}])
                page=context.new_page(); page.goto(self.live_server_url+'/dashboard/security/',wait_until='networkidle')
                self.assertIn('Aucun événement enregistré',page.locator('#security-events').inner_text())
                self.assert_layout(page,390)
                page.screenshot(path=str(OUTPUT/'live-security-empty-390.png'),full_page=True)
            finally:
                browser.close()
