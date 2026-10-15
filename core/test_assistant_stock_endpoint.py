from django.test import TestCase, Client
from django.urls import reverse
from django.core.cache import cache
from categories.models import Category
from products.models import Product


class StockEndpointTests(TestCase):
    def setUp(self):
        cache.clear(); self.addCleanup(cache.clear)
        self.category = Category.objects.create(nom="Chaussures", nom_en="Shoes")
        self.first = Product.objects.create(nom="Nike Alpha", marque="Nike", categorie=self.category, prix=12000, stock=3)
        self.second = Product.objects.create(nom="Nike Beta", marque="Nike", categorie=self.category, prix=18000, prix_promotion=15000, stock=2)

    def ask(self, text, **extra):
        return self.client.post(reverse("assistant_ask"), {"message":text, **extra}, content_type="application/json")

    def test_anonymous_stock_selection_then_real_price_uses_same_product(self):
        self.ask("Je cherche des chaussures Nike")
        response=self.ask("Le deuxième est-il en stock ?").json()
        self.assertEqual(response["availability"], "available")
        self.assertEqual(response["results"][0]["id"], self.second.pk)
        price=self.ask("Et combien coûte-t-il ?").json()
        self.assertEqual(price["results"][0]["id"], self.second.pk)
        self.assertEqual(price["results"][0]["price"], "15000.00")
        self.assertEqual(list(Product.objects.order_by("pk").values_list("stock",flat=True)),[3,2])

    def test_retry_rechecks_stock_and_hidden_products(self):
        hint=reverse("product_detail",args=[self.first.slug])
        first=self.ask("Ce produit est-il disponible ?",context=hint,request_id="stock-retry")
        self.assertEqual(first.json()["availability"],"available")
        Product.objects.filter(pk=self.first.pk).update(stock=0)
        retry=self.ask("Ce produit est-il disponible ?",context=hint,request_id="stock-retry")
        self.assertEqual(retry.json()["availability"],"out_of_stock")
        Product.objects.filter(pk=self.first.pk).update(actif=False)
        hidden=self.ask("Ce produit est-il disponible ?",context=hint,request_id="stock-retry").json()
        self.assertNotIn(self.first.nom,str(hidden))
        self.assertNotIn(hint,str(hidden))

    def test_stock_requests_retain_csrf_and_ignore_supplied_stock(self):
        client=Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse("assistant_ask"),{"message":"Nike Alpha en stock ?"},content_type="application/json").status_code,403)
        response=self.ask("Nike Alpha en stock ?",stock=999,state={"selected_product_id":self.second.pk}).json()
        self.assertEqual(response["results"][0]["stock"],3)
        self.assertEqual(response["results"][0]["id"],self.first.pk)
