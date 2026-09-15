from decimal import Decimal
from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from categories.models import Category
from products.models import Product
from django.utils import translation

from cart.models import Cart, CartItem
from categories.models import Category
from orders.models import Order
from payments.models import Payment
from products.models import Product


LOCALE = Path(settings.BASE_DIR) / "locale"
EN_COMPILED = (LOCALE / "en/LC_MESSAGES/django.mo").exists()
GETTEXT_REQUIRED = "GNU gettext absent : compiler les catalogues avec compilemessages."


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class InternationalisationTests(TestCase):
    def test_configuration_and_middleware_order(self):
        self.assertEqual(settings.LANGUAGE_CODE, "fr")
        self.assertEqual([code for code, name in settings.LANGUAGES], ["fr", "en"])
        self.assertTrue(settings.USE_I18N)
        middleware = settings.MIDDLEWARE
        self.assertLess(middleware.index("django.contrib.sessions.middleware.SessionMiddleware"), middleware.index("django.middleware.locale.LocaleMiddleware"))
        self.assertLess(middleware.index("django.middleware.locale.LocaleMiddleware"), middleware.index("django.middleware.common.CommonMiddleware"))

    def test_default_french(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.headers["Content-Language"], "fr")
        self.assertContains(response, 'lang="fr"')
        self.assertContains(response, "Connexion")

    def test_set_language_english_cookie_and_current_page(self):
        target = reverse("login") + "?next=/orders/"
        response = self.client.post(reverse("set_language"), {"language": "en", "next": target})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, target)
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, "en")
        self.assertEqual(self.client.get(reverse("login")).headers["Content-Language"], "en")

    def test_existing_urls_have_no_language_prefix(self):
        for name in ("login", "home", "create_order", "comptable_dashboard"):
            self.assertFalse(reverse(name).startswith(("/en/", "/fr/", "/bm/")))

    def test_external_redirect_refused(self):
        response = self.client.post(reverse("set_language"), {"language": "en", "next": "https://example.org/steal"})
        self.assertEqual(response.url, "/")

    def test_language_switch_requires_csrf(self):
        response = Client(enforce_csrf_checks=True).post(reverse("set_language"), {"language": "en"})
        self.assertEqual(response.status_code, 403)

    def test_get_does_not_set_language_cookie(self):
        response = self.client.get(reverse("set_language"), {"language": "en"})
        self.assertNotIn(settings.LANGUAGE_COOKIE_NAME, response.cookies)

    def test_invalid_language_not_persisted(self):
        response = self.client.post(reverse("set_language"), {"language": "invalid"})
        self.assertNotIn(settings.LANGUAGE_COOKIE_NAME, response.cookies)

    def test_selector_and_javascript_translation_bridge(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, reverse("set_language"))
        self.assertNotContains(response, 'value="bm"')
        self.assertNotContains(response, "Appliquer")
        self.assertContains(response, 'id="offline-i18n"')
        self.assertContains(response, "Cette action nécessite une connexion Internet.")

    def test_technical_choices_are_identical_across_locales(self):
        for model in (Order, Payment):
            with translation.override("fr"):
                french = [value for value, label in model._meta.get_field("statut").choices]
            with translation.override("en"):
                english = [value for value, label in model._meta.get_field("statut").choices]
            self.assertEqual(french, english)
        self.assertIn("paye", [value for value, label in Payment._meta.get_field("statut").choices])

    def checkout_for_language(self, language):
        user = User.objects.create_user("client-" + language, password="test-password")
        category = Category.objects.create(nom="Categorie " + language)
        product = Product.objects.create(categorie=category, nom="Produit", prix=Decimal("1000.25"), stock=3)
        cart = Cart.objects.create(utilisateur=user)
        CartItem.objects.create(panier=cart, produit=product, prix=product.prix, quantite=2)
        self.client.force_login(user)
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
        response = self.client.post(reverse("create_order"), {"finalize": "1", "adresse": "Rue 1", "ville": "Bamako", "code_postal": "Pharmacie", "mode_livraison": "standard", "methode": "orange_money"})
        self.assertEqual(response.status_code, 200)
        order = Order.objects.get(utilisateur=user)
        self.assertEqual(order.statut, "en_attente")
        self.assertEqual(order.payment.statut, "en_attente")
        self.assertEqual(order.payment.montant, Decimal("2000.50"))
        self.assertEqual(order.frais_livraison, Decimal("0"))
        product.refresh_from_db()
        self.assertEqual(product.stock, 1)

    def test_checkout_french_amounts_and_stored_statuses(self):
        self.checkout_for_language("fr")

    def test_checkout_english_amounts_and_stored_statuses(self):
        self.checkout_for_language("en")

    def test_dashboard_french_and_english(self):
        user = User.objects.create_user("accountant", password="test-password")
        user.profile.role = "comptable"
        user.profile.save()
        self.client.force_login(user)
        for language in ("fr", "en"):
            with self.subTest(language=language):
                self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
                self.assertEqual(self.client.get(reverse("comptable_dashboard")).status_code, 200)

    def test_language_does_not_grant_accounting_access(self):
        user = User.objects.create_user("ordinary-client", password="test-password", is_staff=True)
        self.client.force_login(user)
        for language in ("fr", "en"):
            self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
            self.assertEqual(self.client.get(reverse("comptable_dashboard")).status_code, 302)

    @skipUnless(EN_COMPILED, GETTEXT_REQUIRED)
    def test_english_login_translation(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        self.assertContains(self.client.get(reverse("login")), "Sign in")

    @skipUnless(EN_COMPILED, GETTEXT_REQUIRED)
    def test_english_navigation_translation(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        self.assertContains(self.client.get(reverse("home")), "My orders" if self.client.session.get("_auth_user_id") else "Create an account")

    @skipUnless(EN_COMPILED, GETTEXT_REQUIRED)
    def test_english_home_body_and_footer_translation(self):
        category = Category.objects.create(nom="Test category")
        Product.objects.create(
            categorie=category,
            nom="Test product",
            prix="1000.00",
            stock=5,
            actif=True,
            vedette=True,
        )
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        response = self.client.get(reverse("home"))
        for text in (
            "Home", "Shop", "Shop Management, home", "Your selection, made simple.",
            "Popular categories", "New arrivals", "Best sellers",
            "Fast delivery", "Secure payment", "Customer support", "Need help?",
            "A simpler shopping experience.", "Contact us on WhatsApp", "Change theme",
        ):
            self.assertContains(response, text)
        for text in (
            "La sélection du moment", "Catégories populaires", "Les nouveautés",
            "Les meilleures ventes", "Livraison rapide", "Paiement sécurisé",
            "Besoin d'aide ?",
        ):
            self.assertNotContains(response, text)

    def test_catalogue_content_localizes_without_changing_source_values(self):
        category = Category.objects.create(nom="Lait", nom_en="Milk", description="Catégorie française", description_en="English category")
        product = Product.objects.create(
            categorie=category,
            nom="Lait en poudre",
            nom_en="Powdered milk",
            description="Description française",
            description_en="English description",
            prix="1000.00",
            stock=3,
        )
        with translation.override("fr"):
            self.assertEqual(product.localized_name, "Lait en poudre")
            self.assertEqual(category.localized_name, "Lait")
        with translation.override("en"):
            self.assertEqual(product.localized_name, "Powdered milk")
            self.assertEqual(product.localized_description, "English description")
            self.assertEqual(category.localized_name, "Milk")
            self.assertEqual(category.localized_description, "English category")
        product.refresh_from_db()
        self.assertEqual(product.nom, "Lait en poudre")
        self.assertEqual(product.prix, Decimal("1000.00"))
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        detail = self.client.get(reverse("product_detail", args=[product.slug]))
        self.assertContains(detail, "Powdered milk")
        self.assertNotContains(detail, "Lait en poudre")
        search = self.client.get(reverse("product_list"), {"q": "Powdered milk"})
        self.assertContains(search, "Powdered milk")

    @skipUnless(EN_COMPILED, GETTEXT_REQUIRED)
    def test_english_payment_label(self):
        with translation.override("en"):
            self.assertEqual(str(dict(Payment._meta.get_field("statut").choices)["paye"]), "Paid")

    def test_bambara_is_archived_but_not_active(self):
        self.assertTrue((LOCALE / "bm/LC_MESSAGES/django.po").exists())
        self.assertNotIn("bm", [code for code, name in settings.LANGUAGES])

    def test_bambara_archive_is_not_advertised(self):
        response = self.client.get(reverse("login"))
        self.assertNotContains(response, 'value="bm"')
        self.assertNotIn("bm", [code for code, name in settings.LANGUAGES])


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class InternalEnglishRenderTests(TestCase):
    def test_profile_dropdown_uses_profile_title_and_real_username_for_all_roles(self):
        for role in ("admin", "vendeur", "livreur", "comptable", "client"):
            with self.subTest(role=role):
                user = User.objects.create_user(f"{role}-header", password="password")
                user.profile.role = role
                user.profile.save(update_fields=["role"])
                self.client.force_login(user)

                for language, title in (("fr", "Mon profil"), ("en", "My profile")):
                    self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
                    response = self.client.get(reverse("home"))
                    self.assertContains(response, title)
                    self.assertContains(response, f"{role}-header")
                    self.assertNotContains(response, "Connecté en tant que")
                    self.assertNotContains(response, "Signed in as")

                self.client.logout()

    def test_categories_cart_and_wishlist_real_pages_use_english_text(self):
        category = Category.objects.create(nom="Lait", nom_en="Milk")
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        categories = self.client.get(reverse("category_list"))
        self.assertContains(categories, "Browse the shop by category and quickly find what suits you.")
        detail = self.client.get(reverse("category_detail", args=[category.slug]))
        self.assertContains(detail, "Milk")

        user = User.objects.create_user("empty-client", password="password")
        self.client.force_login(user)
        cart = self.client.get(reverse("cart_detail"))
        self.assertContains(cart, "Add products from the shop. They will appear here with their quantity and total.")
        wishlist = self.client.get(reverse("wishlist"))
        self.assertContains(wishlist, "Save your favourites to find them easily on your next visit.")
