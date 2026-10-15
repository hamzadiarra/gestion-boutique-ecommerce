from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from categories.models import Category
from products.models import Product
from .models import Cart, CartItem


class CartFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("client", password="secret123")
        category = Category.objects.create(nom="Maison")
        self.product = Product.objects.create(categorie=category, nom="Tasse", prix=500, stock=2)
        self.client.login(username="client", password="secret123")

    def test_add_to_cart_respects_requested_quantity_and_stock(self):
        self.client.post(reverse("add_to_cart", args=[self.product.id]), {"quantity": 2})
        item = CartItem.objects.get(panier__utilisateur=self.user)
        self.assertEqual(item.quantite, 2)
        response = self.client.post(reverse("add_to_cart", args=[self.product.id]), {"quantity": 1})
        self.assertRedirects(response, reverse("cart_detail"))
        self.assertEqual(CartItem.objects.get(pk=item.pk).quantite, 2)

    def test_cart_is_private(self):
        self.client.logout()
        response = self.client.get(reverse("cart_detail"))
        self.assertEqual(response.status_code, 302)


class CartMutationSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("cart-owner")
        cls.other = User.objects.create_user("cart-other")
        category = Category.objects.create(nom="Security category")
        cls.product = Product.objects.create(categorie=category, nom="Security product", prix=500, stock=5)
        cls.cart = Cart.objects.create(utilisateur=cls.user)
        cls.item = CartItem.objects.create(panier=cls.cart, produit=cls.product, prix=500, quantite=2)

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)

    def routes(self):
        return [("add_to_cart", self.product.pk)] + [
            (name, self.item.pk) for name in
            ("increase_quantity", "decrease_quantity", "remove_from_cart")
        ]

    def snapshot(self):
        return list(CartItem.objects.order_by("pk").values_list("pk", "panier_id", "produit_id", "quantite", "prix"))

    def token(self):
        self.client.get(reverse("cart_detail"))
        return self.client.cookies["csrftoken"].value

    def test_get_and_head_never_mutate_cart(self):
        before = self.snapshot()
        for name, pk in self.routes():
            for method in ("get", "head"):
                with self.subTest(route=name, method=method):
                    response = getattr(self.client, method)(reverse(name, args=[pk]))
                    self.assertEqual(response.status_code, 405)
                    self.assertEqual(self.snapshot(), before)

    def test_post_requires_csrf_for_every_mutation(self):
        before = self.snapshot()
        for name, pk in self.routes():
            with self.subTest(route=name):
                self.assertEqual(self.client.post(reverse(name, args=[pk])).status_code, 403)
                self.assertEqual(self.snapshot(), before)

    def test_valid_csrf_post_supports_all_cart_actions(self):
        token = self.token()
        for name, expected in (("add_to_cart", 3), ("increase_quantity", 4), ("decrease_quantity", 3)):
            pk = self.product.pk if name == "add_to_cart" else self.item.pk
            response = self.client.post(reverse(name, args=[pk]), {"csrfmiddlewaretoken": token})
            self.assertEqual(response.status_code, 302)
            self.item.refresh_from_db()
            self.assertEqual(self.item.quantite, expected)
        self.assertEqual(self.client.post(reverse("remove_from_cart", args=[self.item.pk]),
            {"csrfmiddlewaretoken": token}).status_code, 302)
        self.assertFalse(CartItem.objects.filter(pk=self.item.pk).exists())

    def test_valid_csrf_does_not_grant_access_to_another_cart(self):
        self.client.force_login(self.other)
        token = self.token()
        before = self.snapshot()
        for name in ("increase_quantity", "decrease_quantity", "remove_from_cart"):
            with self.subTest(route=name):
                response = self.client.post(reverse(name, args=[self.item.pk]), {"csrfmiddlewaretoken": token})
                self.assertEqual(response.status_code, 404)
                self.assertEqual(self.snapshot(), before)

    def test_post_prices_are_ignored_through_checkout(self):
        from orders.models import Order
        self.item.delete()
        token = self.token()
        response = self.client.post(reverse("add_to_cart", args=[self.product.pk]), {
            "csrfmiddlewaretoken": token, "quantity": 2, "prix": "0.01", "price": "0.01", "total": "0.02",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CartItem.objects.get(panier=self.cart).prix, 500)
        response = self.client.post(reverse("create_order"), {
            "csrfmiddlewaretoken": token, "finalize": "1", "adresse": "Rue test", "ville": "Bamako",
            "mode_livraison": "express", "methode": "orange_money", "prix": "0.01",
            "montant": "0.01", "total": "0.01", "frais_livraison": "0",
        })
        self.assertEqual(response.status_code, 200)
        order = Order.objects.get(utilisateur=self.user)
        self.assertEqual(order.items.get().prix, 500)
        self.assertEqual(order.frais_livraison, 2500)
        self.assertEqual(order.total(), 3500)
        self.assertEqual(order.payment.montant, 3500)

    def test_cart_and_product_pages_render_post_forms_with_csrf(self):
        import re
        for route, args, actions in (
            ("cart_detail", [], self.routes()[1:]),
            ("product_list", [], [("add_to_cart", self.product.pk)]),
            ("product_detail", [self.product.slug], [("add_to_cart", self.product.pk)]),
        ):
            response = self.client.get(reverse(route, args=args))
            self.assertEqual(response.status_code, 200)
            content = response.content.decode()
            forms = re.findall(r"<form\b[^>]*>.*?</form>", content, re.S)
            for action, pk in actions:
                url = reverse(action, args=[pk])
                matching = [form for form in forms if 'action="' + url + '"' in form]
                self.assertTrue(matching, (route, action))
                for form in matching:
                    self.assertIn('method="post"', form)
                    self.assertIn('name="csrfmiddlewaretoken"', form)
                self.assertNotIn('href="' + url + '"', content)

    def test_anonymous_add_links_return_to_product_after_login(self):
        self.client.logout()
        login_url = reverse("login") + "?next=" + reverse("product_detail", args=[self.product.slug])
        for route, args in (("product_list", []), ("product_detail", [self.product.slug])):
            response = self.client.get(reverse(route, args=args))
            self.assertContains(response, 'href="' + login_url + '"')
            self.assertNotContains(response, 'action="' + reverse("add_to_cart", args=[self.product.pk]) + '"')
