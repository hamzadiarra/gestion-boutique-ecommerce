from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from categories.models import Category
from .models import Product


class CatalogueRefonteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat = Category.objects.create(nom="Téléphones")
        cls.other = Category.objects.create(nom="Vêtements")
        cls.phone = Product.objects.create(categorie=cls.cat, nom="Samsung Galaxy", prix=150000, prix_promotion=120000, stock=4)
        Product.objects.create(categorie=cls.cat, nom="Nokia", prix=20000, stock=0)
        Product.objects.create(categorie=cls.other, nom="Chemise", prix=5000)
        Product.objects.create(categorie=cls.cat, nom="Samsung caché", prix=100, actif=False)

    def test_autocomplete_returns_real_price_and_no_inactive_products(self):
        response = self.client.get("/products/autocomplete/", {"q": "SAMS"})
        self.assertEqual(response.status_code, 200)
        rows = response.json()["results"]
        self.assertEqual([r["name"] for r in rows], ["Samsung Galaxy"])
        self.assertEqual(rows[0]["price"], "120000.00")
        self.assertTrue(rows[0]["available"])
        self.assertEqual(rows[0]["url"], reverse("product_detail", args=[self.phone.slug]))

    def test_typo_finds_product_and_empty_query_is_bounded(self):
        response = self.client.get("/products/autocomplete/", {"q": "samsng"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["id"], self.phone.pk)
        self.assertEqual(self.client.get("/products/autocomplete/", {"q": ""}).json()["results"], [])

    def test_category_price_bounds_and_promotion_filter(self):
        response = self.client.get(reverse("product_list"), {"categorie": self.cat.pk, "prix_max": "125000"})
        self.assertEqual(response.context["price_bounds"], {"minimum": Decimal("20000"), "maximum": Decimal("120000")})
        self.assertEqual(response.context["page_obj"].paginator.count, 2)
        self.assertNotContains(response, "Chemise")

    def test_category_counts_only_published_products(self):
        response = self.client.get(reverse("category_list"))
        category = next(c for c in response.context["categories"] if c.pk == self.cat.pk)
        self.assertEqual(category.product_count, 2)

    def test_category_detail_supports_search_and_filters(self):
        response = self.client.get(reverse("category_detail", args=[self.cat.slug]), {"q": "Nokia"})
        self.assertContains(response, "Nokia")
        self.assertNotContains(response, "Samsung Galaxy")

    def test_inactive_category_and_invalid_prices(self):
        self.cat.active = False
        self.cat.save()
        response = self.client.get("/products/autocomplete/", {"q": "sams"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])
        for price in ("NaN", "Infinity", "-5", "nonsense", "1e999"):
            self.assertEqual(self.client.get(reverse("product_list"), {"prix_min": price}).status_code, 200)

    def test_autocomplete_has_bounded_queries_and_honors_category(self):
        with self.assertNumQueries(2):
            response = self.client.get("/products/autocomplete/", {"q": "sams"})
        self.assertEqual(response.status_code, 200)
        with self.assertNumQueries(3):
            response = self.client.get("/products/autocomplete/", {"q": "samsng"})
        self.assertEqual(response.json()["results"][0]["id"], self.phone.pk)
        self.assertEqual(self.client.get("/products/autocomplete/", {"q": "sams", "categorie": self.other.pk}).json()["results"], [])

    def test_zero_results_and_price_sorting_render(self):
        response = self.client.get(reverse("product_list"), {"q": "zzzzzzz"})
        self.assertContains(response, "Aucun produit trouvé")
        response = self.client.get(reverse("product_list"), {"categorie": self.cat.pk, "tri": "prix_croissant"})
        self.assertEqual([p.nom for p in response.context["page_obj"]], ["Nokia", "Samsung Galaxy"])

    def test_checkout_does_not_show_none_for_an_empty_profile(self):
        from django.contrib.auth.models import User
        from cart.models import Cart, CartItem
        user = User.objects.create_user("empty-profile")
        cart = Cart.objects.create(utilisateur=user)
        CartItem.objects.create(panier=cart, produit=self.phone, prix=self.phone.prix_promotion, quantite=1)
        self.client.force_login(user)
        response = self.client.get(reverse("create_order"))
        self.assertNotContains(response, 'value="None"')
        self.assertNotContains(response, '>None</textarea>')
