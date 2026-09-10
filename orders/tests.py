from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from categories.models import Category
from cart.models import Cart, CartItem
from products.models import Product
from .models import Order


class CheckoutFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("client", password="secret123")
        self.category = Category.objects.create(nom="Maison")
        self.product = Product.objects.create(categorie=self.category, nom="Lampe", prix=1000, stock=3)
        cart = Cart.objects.create(utilisateur=self.user)
        CartItem.objects.create(panier=cart, produit=self.product, prix=1000, quantite=1)
        self.client.login(username="client", password="secret123")

    def checkout(self):
        return self.client.post(reverse("create_order"), {"finalize": "1", "adresse": "Rue 1", "ville": "Bamako", "code_postal": "0000", "mode_livraison": "standard", "methode": "orange_money"})

    def test_checkout_creates_order_payment_and_reduces_stock(self):
        response = self.checkout()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.filter(utilisateur=self.user).count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 2)
        self.assertEqual(Order.objects.get(utilisateur=self.user).payment.statut, "paye")

    def test_double_checkout_does_not_create_second_order(self):
        self.checkout()
        response = self.checkout()
        self.assertEqual(Order.objects.filter(utilisateur=self.user).count(), 1)
        self.assertEqual(response.status_code, 302)

    def test_checkout_rejects_insufficient_stock(self):
        item = CartItem.objects.get()
        item.quantite = 99
        item.save()
        response = self.checkout()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Stock insuffisant")
        self.assertFalse(Order.objects.filter(utilisateur=self.user).exists())
