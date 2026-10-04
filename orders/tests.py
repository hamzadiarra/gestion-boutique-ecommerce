from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from cart.models import Cart, CartItem
from categories.models import Category
from products.models import Product
from .services import BusinessRuleError, change_order_status, create_order_from_cart


class OrderServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="client", password="test")
        self.category = Category.objects.create(nom="Téléphones")
        self.product = Product.objects.create(
            categorie=self.category,
            nom="Produit test",
            prix=Decimal("1000"),
            stock=5,
            actif=True,
        )

    def test_create_order_from_cart_updates_stock_once(self):
        cart = Cart.objects.create(utilisateur=self.user)
        CartItem.objects.create(
            panier=cart,
            produit=self.product,
            quantite=2,
            prix=self.product.prix_effectif,
        )

        order = create_order_from_cart(self.user)

        self.product.refresh_from_db()
        self.assertEqual(order.total(), Decimal("2000"))
        self.assertEqual(self.product.stock, 3)
        self.assertEqual(self.product.quantite_vendue, 2)
        self.assertFalse(cart.items.exists())

    def test_create_order_rejects_insufficient_stock(self):
        cart = Cart.objects.create(utilisateur=self.user)
        CartItem.objects.create(
            panier=cart,
            produit=self.product,
            quantite=6,
            prix=self.product.prix_effectif,
        )

        with self.assertRaises(BusinessRuleError):
            create_order_from_cart(self.user)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)
        self.assertEqual(self.product.quantite_vendue, 0)

    def test_cancel_pending_order_restores_stock(self):
        cart = Cart.objects.create(utilisateur=self.user)
        CartItem.objects.create(
            panier=cart,
            produit=self.product,
            quantite=2,
            prix=self.product.prix_effectif,
        )
        order = create_order_from_cart(self.user)

        change_order_status(order, "annuler", user=self.user)

        self.product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(order.statut, "annulee")
        self.assertEqual(self.product.stock, 5)
        self.assertEqual(self.product.quantite_vendue, 0)
