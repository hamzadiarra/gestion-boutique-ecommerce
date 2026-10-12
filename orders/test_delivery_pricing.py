from decimal import Decimal
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PricingTests(TestCase):
    def setUp(self):
        self.driver = User.objects.create_user("courier")
        self.driver.profile.role = "livreur"
        self.driver.profile.save()
        self.admin = User.objects.create_user("admin", is_superuser=True)
        self.customer = User.objects.create_user("customer")

    def proposal(self, **kwargs):
        from .pricing_services import proposer_tarif
        return proposer_tarif(self.driver, "express", Decimal("1750.00"), **kwargs)

    def test_only_courier_proposes_and_only_admin_decides(self):
        from .pricing_services import proposer_tarif, decider_tarif
        with self.assertRaises(PermissionDenied):
            proposer_tarif(self.customer, "express", Decimal("1750"))
        item = self.proposal()
        self.assertEqual(item.statut, "propose")
        with self.assertRaises(PermissionDenied):
            decider_tarif(item.pk, self.driver, "approuve", "Validé par moi")
        decider_tarif(item.pk, self.admin, "approuve", "Tarif vérifié")
        item.refresh_from_db()
        self.assertEqual(item.statut, "approuve")
        self.assertEqual(item.historique.count(), 2)

    def test_invalid_amounts_and_mode_rejected(self):
        from .pricing_services import proposer_tarif
        for fee in ["-1", "NaN", "Infinity", "0.001", "100000000"]:
            with self.subTest(fee=fee), self.assertRaises(ValidationError):
                proposer_tarif(self.driver, "standard", fee)
        with self.assertRaises(ValidationError):
            proposer_tarif(self.driver, "distance", "100")

    def test_quote_bound_to_customer_zone_and_mode_and_disabled_offer_rejected(self):
        from .pricing_services import decider_tarif, creer_devis, verifier_devis
        item = self.proposal(zone="Bamako")
        with self.assertRaises(ValidationError):
            creer_devis(item.pk, self.customer, "express", "Bamako")
        decider_tarif(item.pk, self.admin, "approuve", "Tarif vérifié")
        token = creer_devis(item.pk, self.customer, "express", "Bamako")
        tarif, fee = verifier_devis(token, self.customer, "express", " BAMAKO ")
        self.assertEqual(fee, Decimal("1750"))
        for user, mode, city in [(self.driver, "express", "Bamako"), (self.customer, "standard", "Bamako"), (self.customer, "express", "Sikasso")]:
            with self.assertRaises(ValidationError):
                verifier_devis(token, user, mode, city)
        with self.assertRaises(ValidationError):
            verifier_devis(token + "x", self.customer, "express", "Bamako")
        decider_tarif(item.pk, self.admin, "desactive", "Offre retirée")
        with self.assertRaises(ValidationError):
            verifier_devis(token, self.customer, "express", "Bamako")

    def checkout_data(self, tarif, token):
        from categories.models import Category
        from products.models import Product
        from cart.models import Cart, CartItem
        category = Category.objects.create(nom="Test")
        product = Product.objects.create(nom="Article", categorie=category, prix=1000, stock=3)
        cart = Cart.objects.create(utilisateur=self.customer)
        CartItem.objects.create(panier=cart, produit=product, prix=1000, quantite=2)
        self.client.force_login(self.customer)
        return {"finalize": "1", "adresse": "Rue 1", "ville": "Bamako", "mode_livraison": "express",
            "methode": "wave", "tarif_livraison": str(tarif.pk), "devis_livraison": token, "frais_livraison": "1"}

    def test_checkout_server_fee_frozen_after_new_approval_and_deactivation(self):
        from .pricing_services import decider_tarif, creer_devis
        from .models import Order
        item = self.proposal()
        decider_tarif(item.pk, self.admin, "approuve", "Tarif vérifié")
        token = creer_devis(item.pk, self.customer, "express", "Bamako")
        response = self.client.post("/orders/create/", self.checkout_data(item, token))
        self.assertEqual(response.status_code, 200)
        order = Order.objects.get(utilisateur=self.customer)
        self.assertEqual(order.frais_livraison, Decimal("1750"))
        self.assertEqual(order.payment.montant, Decimal("3750"))
        decider_tarif(item.pk, self.admin, "desactive", "Nouvelle grille proposée")
        from .pricing_services import proposer_tarif
        replacement = proposer_tarif(self.driver, "express", "3000")
        decider_tarif(replacement.pk, self.admin, "approuve", "Nouveau tarif approuvé")
        order.refresh_from_db()
        self.assertEqual(order.frais_livraison, Decimal("1750"))
        self.assertEqual(order.tarif_livraison_id, item.pk)
        self.assertEqual(order.payment.montant, Decimal("3750"))
        order.frais_livraison = 999
        with self.assertRaises(ValidationError):
            order.save()

    def test_invalid_quote_rolls_back_checkout_stock_and_cart(self):
        from .models import Order
        from products.models import Product
        from cart.models import CartItem
        item = self.proposal()
        response = self.client.post("/orders/create/", self.checkout_data(item, "forged"))
        self.assertEqual(response.status_code, 409)
        self.assertFalse(Order.objects.filter(utilisateur=self.customer).exists())
        self.assertEqual(Product.objects.get().stock, 3)
        self.assertEqual(CartItem.objects.count(), 1)

    def test_pricing_pages_permissions_decisions_and_offers(self):
        from .pricing_services import decider_tarif
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get("/orders/livraisons/tarifs/").status_code, 403)
        self.client.force_login(self.driver)
        self.assertEqual(self.client.get("/orders/livraisons/tarifs/").status_code, 200)
        r = self.client.post("/orders/livraisons/tarifs/", {"mode": "standard", "zone": "Bamako", "montant": "1200"})
        self.assertEqual(r.status_code, 302)
        from .pricing_models import TarifLivreur
        item = TarifLivreur.objects.get()
        self.assertEqual(self.client.post(f"/orders/livraisons/tarifs/{item.pk}/decision/", {"statut": "approuve", "motif": "Fraude"}).status_code, 403)
        decider_tarif(item.pk, self.admin, "approuve", "Tarif vérifié")
        self.client.force_login(self.customer)
        response = self.client.get("/orders/livraisons/offres/", {"mode": "standard", "ville": "Bamako"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["offres"][0]["montant"], "1200.00")
        self.assertIn("no-store", response["Cache-Control"])
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/orders/livraisons/tarifs/").status_code, 200)
