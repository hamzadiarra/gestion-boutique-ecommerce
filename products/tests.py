from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from cart.models import Cart, CartItem
from categories.models import Category

from .models import Product


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ProductLocalizationTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            nom="Lait", nom_en="Milk",
            description="Catégorie française", description_en="English category",
        )
        self.product = Product.objects.create(
            categorie=self.category, nom="Lait en poudre", nom_en="Powdered milk",
            description="Description française", description_en="Best quality",
            prix=Decimal("1000.00"), stock=5, vedette=True,
        )

    def test_localized_name_uses_language_and_falls_back_to_french(self):
        with translation.override("fr"):
            self.assertEqual(self.product.localized_name, "Lait en poudre")
        with translation.override("en"):
            self.assertEqual(self.product.localized_name, "Powdered milk")
            self.product.nom_en = ""
            self.assertEqual(self.product.localized_name, "Lait en poudre")

    def test_localized_description_uses_language_and_falls_back_to_french(self):
        with translation.override("fr"):
            self.assertEqual(self.product.localized_description, "Description française")
        with translation.override("en"):
            self.assertEqual(self.product.localized_description, "Best quality")
            self.product.description_en = ""
            self.assertEqual(self.product.localized_description, "Description française")

    def test_home_catalogue_detail_cart_and_checkout_render_localized_name(self):
        user = User.objects.create_user("catalog-client", password="password")
        cart = Cart.objects.create(utilisateur=user)
        CartItem.objects.create(panier=cart, produit=self.product, prix=self.product.prix, quantite=2)
        self.client.cookies["django_language"] = "fr"
        for url in (reverse("home"), reverse("product_list"), reverse("product_detail", args=[self.product.slug])):
            self.assertContains(self.client.get(url), "Lait en poudre")
        self.client.force_login(user)
        self.assertContains(self.client.get(reverse("cart_detail")), "Lait en poudre")
        self.assertContains(self.client.get(reverse("create_order")), "Lait en poudre")
        self.client.cookies["django_language"] = "en"
        for url in (reverse("home"), reverse("product_list"), reverse("product_detail", args=[self.product.slug])):
            response = self.client.get(url)
            self.assertContains(response, "Powdered milk")
            self.assertNotContains(response, "Lait en poudre")
        detail = self.client.get(reverse("product_detail", args=[self.product.slug]))
        self.assertContains(detail, "Best quality")
        self.assertContains(detail, "Milk")
        self.assertNotContains(detail, "Description française")
        self.assertContains(self.client.get(reverse("cart_detail")), "Powdered milk")
        checkout = self.client.get(reverse("create_order"))
        self.assertContains(checkout, "Powdered milk")
        self.assertNotContains(checkout, "Lait en poudre")

    def test_bilingual_search_finds_french_and_english_names(self):
        self.assertContains(self.client.get(reverse("product_list"), {"q": "Lait"}), "Lait en poudre")
        self.assertContains(self.client.get(reverse("product_list"), {"q": "Powdered"}), "Lait en poudre")

    def test_product_list_english_renders_translated_introduction(self):
        self.client.cookies["django_language"] = "en"
        response = self.client.get(reverse("product_list"))
        self.assertContains(response, "Explore our selection")
        self.assertNotContains(response, "Explorez notre sélection")
