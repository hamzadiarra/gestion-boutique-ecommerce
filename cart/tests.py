from django.contrib.auth.models import User
from django.test import TestCase
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
