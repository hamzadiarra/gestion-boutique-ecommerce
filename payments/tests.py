from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from categories.models import Category
from orders.models import Order, OrderItem
from products.models import Product
from .models import Payment
from .services import pay_order


class PaymentServiceTests(TestCase):
    def test_pay_order_is_idempotent(self):
        user = User.objects.create_user(username="client", password="test")
        category = Category.objects.create(nom="Accessoires")
        product = Product.objects.create(
            categorie=category,
            nom="Chargeur",
            prix=Decimal("2500"),
            stock=10,
            actif=True,
        )
        order = Order.objects.create(utilisateur=user)
        OrderItem.objects.create(
            commande=order,
            produit=product,
            quantite=1,
            prix=product.prix_effectif,
        )

        first_payment = pay_order(order, "especes")
        second_payment = pay_order(order, "wave")

        order.refresh_from_db()
        self.assertEqual(first_payment.id, second_payment.id)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(order.statut, "confirmee")
