"""Real Edge stock conversations on a disposable Django test database."""
import tempfile
from pathlib import Path
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.core.cache import cache
from categories.models import Category
from products.models import Product
from playwright.sync_api import sync_playwright


@override_settings(DEBUG=True)
class StockBrowserTests(StaticLiveServerTestCase):
    def ask(self,page,text):
        page.locator("#shopAssistantInput").fill(text)
        with page.expect_response(lambda r: r.url.endswith("/assistant/ask/") and r.request.method=="POST") as pending:
            page.locator('#shopAssistantForm button[type="submit"]').click()
        response=pending.value
        self.assertEqual(response.status,200)
        page.wait_for_function("document.querySelector('#shopAssistantForm').getAttribute('aria-busy') === 'false'")
        return response.json()

    def test_french_english_stock_conversations(self):
        cache.clear(); self.addCleanup(cache.clear)
        category=Category.objects.create(nom="Chaussures",nom_en="Shoes")
        first=Product.objects.create(nom="Nike Alpha",marque="Nike",categorie=category,prix=12000,stock=4)
        second=Product.objects.create(nom="Nike Beta",marque="Nike",categorie=category,prix=18000,prix_promotion=15000,stock=0)
        Product.objects.create(nom="Nike Hidden",marque="Nike",categorie=category,prix=99,stock=200,actif=False)
        output=Path(tempfile.gettempdir())/"gestion-boutique-assistant-stock"
        output.mkdir(exist_ok=True)
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel="msedge",headless=True)
            try:
                for language,width in (("fr",390),("en",1280)):
                    context=browser.new_context(viewport={"width":width,"height":1000},service_workers="block")
                    context.add_cookies([{"name":"django_language","value":language,"url":self.live_server_url}])
                    page=context.new_page(); errors=[]
                    page.on("pageerror",lambda error: errors.append(str(error)))
                    page.goto(self.live_server_url,wait_until="networkidle")
                    page.locator("#shopAssistantToggle").click()
                    self.ask(page,"Je cherche des chaussures Nike" if language=="fr" else "I am looking for Nike shoes")
                    stock=self.ask(page,"Le deuxième est-il en stock ?" if language=="fr" else "Is the second in stock?")
                    self.assertEqual(stock["availability"],"out_of_stock")
                    self.assertEqual(stock["results"][0]["id"],second.pk)
                    price=self.ask(page,"Et combien coûte-t-il ?" if language=="fr" else "And how much does it cost?")
                    self.assertEqual(price["results"][0]["id"],second.pk)
                    self.assertEqual(price["results"][0]["price"],"15000.00")
                    category_answer=self.ask(page,"Combien de produits sont en stock dans la catégorie chaussures ?" if language=="fr" else "How many products are in stock in the shoes category?")
                    self.assertEqual(category_answer["available_count"],1)
                    self.assertNotIn("Nike Hidden",str(category_answer))
                    self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"),width+1)
                    self.assertEqual(errors,[])
                    page.screenshot(path=str(output/f"stock-{language}-{width}.png"))
                    context.close()
                    print(f"Stock {language} {width}px OK",flush=True)
            finally:
                browser.close()
        first.refresh_from_db();second.refresh_from_db()
        self.assertEqual((first.stock,second.stock),(4,0))
