from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from categories.models import Category
from products.models import Product
from orders.services import BusinessRuleError
from .models import Vente
from .services import create_direct_sale


class DirectSaleServiceTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(username="vendeur", password="test")
        self.category = Category.objects.create(nom="Ordinateurs")
        self.product = Product.objects.create(
            categorie=self.category,
            nom="Laptop",
            prix=Decimal("300000"),
            prix_promotion=Decimal("280000"),
            stock=4,
            actif=True,
        )

    def test_direct_sale_uses_effective_price_and_updates_stock(self):
        sale = create_direct_sale(
            vendeur=self.seller,
            produit=self.product,
            quantite=2,
            methode_paiement="especes",
        )

        self.product.refresh_from_db()
        self.assertEqual(sale.prix_unitaire, Decimal("280000"))
        self.assertEqual(sale.montant_total, Decimal("560000"))
        self.assertEqual(self.product.stock, 2)
        self.assertEqual(self.product.quantite_vendue, 2)

    def test_direct_sale_rejects_invalid_quantity(self):
        with self.assertRaises(BusinessRuleError):
            create_direct_sale(
                vendeur=self.seller,
                produit=self.product,
                quantite=0,
                methode_paiement="especes",
            )

        self.assertEqual(Vente.objects.count(), 0)
