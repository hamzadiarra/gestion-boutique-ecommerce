"""Cross-application journeys, using only Django's isolated test database."""
import html
import re
from decimal import Decimal
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from cart.models import Cart, CartItem
from categories.models import Category
from dashboard.models import BoutiqueSettings, JournalActivite, Vente
from orders.models import Order, OrderItem
from payments.models import Payment
from payments.views import _confirm_wave_payment
from products.models import Product


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class StabilisationE2ETests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {}
        for role in ("client", "vendeur", "comptable", "admin"):
            user = User.objects.create_user(role, password="E2ePassword!42", email=f"{role}@example.com")
            user.profile.role = role
            user.profile.save()
            cls.users[role] = user
        cls.owner = cls.users["client"]
        cls.other = User.objects.create_user("other", password="E2ePassword!42")
        cls.staff = User.objects.create_user("staff-client", is_staff=True)
        cls.other_seller = User.objects.create_user("other-seller")
        cls.other_seller.profile.role = "vendeur"
        cls.other_seller.profile.save()
        cls.category = Category.objects.create(nom="E2E category")
        cls.product = Product.objects.create(
            categorie=cls.category, nom="E2E product", prix=1000,
            prix_promotion=800, stock=10,
        )
        cls.shop = BoutiqueSettings.objects.create(
            nom="Boutique E2E", logo="boutique/e2e-logo.png", telephone="76001234",
            adresse="Adresse boutique E2E", devise="XOF", message_recu="Merci E2E",
        )

    def _order(self, owner=None, paid=False):
        order = Order.objects.create(
            utilisateur=owner or self.owner, frais_livraison=2500,
            statut="confirmee" if paid else "en_attente",
        )
        OrderItem.objects.create(commande=order, produit=self.product, prix=800, quantite=2)
        Payment.objects.create(
            commande=order, montant=4100, methode="orange_money",
            statut="paye" if paid else "en_attente",
            date_paiement=timezone.now() if paid else None,
        )
        return order

    def _checkout(self, user=None, method="orange_money", delivery="express"):
        self.client.force_login(user or self.owner)
        self.client.post(reverse("add_to_cart", args=[self.product.pk]), {"quantity": 2})
        return self.client.post(reverse("create_order"), {
            "finalize": "1", "adresse": "Rue E2E", "ville": "Bamako",
            "mode_livraison": delivery, "methode": method,
        })

    def _assert_shop(self, response):
        for value in (self.shop.nom, self.shop.telephone, self.shop.adresse,
                      self.shop.devise, self.shop.message_recu, self.shop.logo.url):
            self.assertContains(response, value)

    def test_client_registration_to_paid_receipt_and_idempotent_confirmation(self):
        response = self.client.post(reverse("register"), {
            "email": "e2e-customer@example.com", "first_name": "Awa", "last_name": "Test",
            "birth_day": "1", "birth_month": "1", "birth_year": "1995", "genre": "femme",
            "password1": "E2ePassword!42", "password2": "E2ePassword!42", "accept_terms": "on",
        })
        self.assertRedirects(response, reverse("profile"))
        buyer = User.objects.get(email="e2e-customer@example.com")
        self.client.get(reverse("logout"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertRedirects(self.client.post(reverse("login"), {
            "username": buyer.username, "password": "E2ePassword!42",
        }), reverse("home"))
        for name, args in (("product_list", []), ("category_list", []),
                           ("category_detail", [self.category.slug]),
                           ("product_detail", [self.product.slug])):
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)
        self.assertRedirects(self.client.post(reverse("add_to_cart", args=[self.product.pk]), {
            "quantity": 2,
        }), reverse("cart_detail"))
        self.assertEqual(self.client.get(reverse("cart_detail")).context["total"], 1600)
        checkout = self.client.get(reverse("create_order"))
        self.assertContains(checkout, "(1600.00+fee)")
        response = self.client.post(reverse("create_order"), {
            "finalize": "1", "adresse": "Rue E2E", "ville": "Bamako",
            "mode_livraison": "express", "methode": "orange_money",
        })
        self.assertEqual(response.status_code, 200)
        order = Order.objects.get(utilisateur=buyer)
        payment = order.payment
        self.assertEqual(order.statut, "en_attente")
        self.assertEqual(payment.statut, "en_attente")
        self.assertIsNone(payment.date_paiement)
        self.assertEqual(order.frais_livraison, 2500)
        self.assertEqual(order.total(), 4100)
        self.assertEqual(payment.montant, order.total())
        self.assertEqual(payment.commande_id, order.pk)
        self.assertFalse(buyer.cart.items.exists())
        self.product.refresh_from_db()
        self.assertEqual((self.product.stock, self.product.quantite_vendue), (8, 2))
        self.assertContains(self.client.get(reverse("my_orders")), str(order.pk))
        self.assertEqual(self.client.get(reverse("order_detail", args=[order.pk])).status_code, 200)
        self.assertRedirects(self.client.get(reverse("order_receipt", args=[order.pk])), reverse("order_detail", args=[order.pk]))
        self.client.force_login(self.users["vendeur"])
        confirm = reverse("confirmer_commande", args=[order.pk])
        self.assertRedirects(self.client.post(confirm, {"action": "confirmer"}), reverse("order_receipt", args=[order.pk]))
        payment.refresh_from_db(); order.refresh_from_db()
        self.assertEqual(payment.statut, "paye")
        self.assertEqual(order.statut, "confirmee")
        self.assertIsNotNone(payment.date_paiement)
        self.assertIsNotNone(order.date_confirmation)
        paid_at = payment.date_paiement
        notification_count = buyer.notifications.count()
        activity_count = JournalActivite.objects.count()
        self.client.post(confirm, {"action": "confirmer"})
        self.product.refresh_from_db(); payment.refresh_from_db()
        self.assertEqual((self.product.stock, self.product.quantite_vendue), (8, 2))
        self.assertEqual(payment.date_paiement, paid_at)
        self.assertEqual(buyer.notifications.count(), notification_count)
        self.assertEqual(buyer.notifications.filter(type_notification="paiement").count(), 1)
        self.assertEqual(JournalActivite.objects.count(), activity_count)
        self.assertEqual(Payment.objects.filter(commande=order).count(), 1)
        self.assertFalse(Vente.objects.exists())
        self.client.force_login(buyer)
        receipt = self.client.get(reverse("order_receipt", args=[order.pk]))
        self._assert_shop(receipt)
        for value in (f"REC-{order.date_confirmation.year}-{order.pk:06d}", "E2E product", "4100", "2500", "Orange Money"):
            self.assertContains(receipt, value)

    def test_seller_login_sale_history_receipt_and_private_permissions(self):
        self.assertRedirects(self.client.post(reverse("login"), {
            "username": "vendeur", "password": "E2ePassword!42",
        }), reverse("vendeur_dashboard"))
        response = self.client.post(reverse("enregistrer_vente"), {
            "produit": self.product.pk, "quantite": 2, "methode_paiement": "carte",
            "reference_client": "Client comptoir E2E",
        })
        sale = Vente.objects.get()
        self.assertRedirects(response, reverse("vendeur_vente_recu", args=[sale.pk]))
        self.assertEqual((sale.vendeur_id, sale.produit_id), (self.users["vendeur"].pk, self.product.pk))
        self.assertEqual((sale.quantite, sale.prix_unitaire, sale.montant_total), (2, 800, 1600))
        self.assertEqual(sale.methode_paiement, "carte")
        self.product.refresh_from_db()
        self.assertEqual((self.product.stock, self.product.quantite_vendue), (8, 2))
        receipt = self.client.get(reverse("vendeur_vente_recu", args=[sale.pk]))
        self._assert_shop(receipt)
        self.assertContains(receipt, f"VTE-{sale.date_vente.year}-{sale.pk:06d}")
        self.assertContains(receipt, "Carte bancaire")
        history = self.client.get(reverse("historique_ventes"), {"q": "Client comptoir E2E", "methode": "carte"})
        self.assertEqual(history.context["page_obj"].paginator.count, 1)
        self.assertContains(history, reverse("vendeur_vente_recu", args=[sale.pk]))
        self.client.force_login(self.other_seller)
        self.assertEqual(self.client.get(reverse("vendeur_vente_recu", args=[sale.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("historique_ventes")).context["page_obj"].paginator.count, 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)

    def test_order_payment_receipt_and_cart_ownership_including_staff_client(self):
        order = self._order(paid=True)
        cart = Cart.objects.create(utilisateur=self.owner)
        item = CartItem.objects.create(panier=cart, produit=self.product, prix=800)
        for user in (self.other, self.staff, self.users["comptable"]):
            self.client.force_login(user)
            for name in ("order_detail", "payment_form"):
                with self.subTest(user=user.username, route=name):
                    self.assertEqual(self.client.get(reverse(name, args=[order.pk])).status_code, 404)
            self.assertRedirects(self.client.get(reverse("order_receipt", args=[order.pk])), reverse("home"))
            for name in ("increase_quantity", "decrease_quantity", "remove_from_cart"):
                self.assertEqual(self.client.post(reverse(name, args=[item.pk])).status_code, 404)
        item.refresh_from_db()
        self.assertEqual(item.quantite, 1)
        for role in ("admin", "vendeur"):
            self.client.force_login(self.users[role])
            self.assertEqual(self.client.get(reverse("order_detail", args=[order.pk])).status_code, 200)

    def test_receipt_refuses_unpaid_or_missing_payment_even_if_order_confirmed(self):
        order = self._order()
        Order.objects.filter(pk=order.pk).update(statut="confirmee")
        self.client.force_login(self.owner)
        self.assertRedirects(self.client.get(reverse("order_receipt", args=[order.pk])), reverse("order_detail", args=[order.pk]))
        empty = Order.objects.create(utilisateur=self.owner, statut="confirmee")
        self.assertRedirects(self.client.get(reverse("order_receipt", args=[empty.pk])), reverse("order_detail", args=[empty.pk]))

    def test_admin_payment_confirmation_is_complete_idempotent_and_cannot_regress(self):
        self._checkout()
        order = Order.objects.get()
        payment = order.payment
        self.client.force_login(self.users["admin"])
        url = reverse("admin_paiement_statut", args=[payment.pk])
        self.assertRedirects(self.client.post(url, {"statut": "paye"}), reverse("admin_paiements"))
        order.refresh_from_db(); payment.refresh_from_db()
        self.assertEqual((order.statut, payment.statut), ("confirmee", "paye"))
        self.assertIsNotNone(payment.date_paiement)
        paid_at = payment.date_paiement
        notifications = self.owner.notifications.count()
        self.client.post(url, {"statut": "paye"})
        for status in ("en_attente", "echoue", "annule"):
            self.client.post(url, {"statut": status})
        payment.refresh_from_db(); self.product.refresh_from_db()
        self.assertEqual((payment.statut, payment.date_paiement), ("paye", paid_at))
        self.assertEqual(self.owner.notifications.count(), notifications)
        self.assertEqual(self.product.stock, 8)
        self.client.force_login(self.users["comptable"])
        self.assertEqual(self.client.get(reverse("comptable_dashboard")).context["total_jour"], 4100)

    def test_admin_order_transitions_use_existing_cycle_and_cancellation_restocks_once(self):
        self._checkout()
        order = Order.objects.get()
        self.client.force_login(self.users["admin"])
        url = reverse("admin_commande_statut", args=[order.pk])
        self.client.post(url, {"statut": "livree"})
        order.refresh_from_db()
        self.assertEqual(order.statut, "en_attente")
        self.client.post(url, {"statut": "confirmee"})
        order.refresh_from_db()
        self.assertEqual(order.payment.statut, "paye")
        self.assertIsNotNone(order.payment.date_paiement)
        self.client.post(url, {"statut": "expediee"})
        order.refresh_from_db()
        self.assertIsNotNone(order.date_expedition)
        self.client.post(url, {"statut": "annulee"})
        self.client.post(url, {"statut": "annulee"})
        self.client.post(url, {"statut": "en_attente"})
        order.refresh_from_db(); self.product.refresh_from_db()
        self.assertEqual(order.statut, "annulee")
        self.assertIsNotNone(order.date_annulation)
        self.assertEqual((self.product.stock, self.product.quantite_vendue), (10, 0))
        self.assertEqual(order.payment.statut, "paye")

    def test_admin_cancel_pending_payment_cancels_order_and_restocks_once(self):
        self._checkout()
        order = Order.objects.get()
        self.client.force_login(self.users["admin"])
        url = reverse("admin_paiement_statut", args=[order.payment.pk])
        self.client.post(url, {"statut": "annule"})
        self.client.post(url, {"statut": "annule"})
        order.refresh_from_db(); self.product.refresh_from_db()
        self.assertEqual((order.statut, order.payment.statut), ("annulee", "annule"))
        self.assertEqual(self.product.stock, 10)

    def test_confirmation_refuses_mismatched_amount(self):
        order = self._order()
        Payment.objects.filter(commande=order).update(montant=1)
        self.client.force_login(self.users["vendeur"])
        self.client.post(reverse("confirmer_commande", args=[order.pk]), {"action": "confirmer"})
        order.refresh_from_db()
        self.assertEqual((order.statut, order.payment.statut), ("en_attente", "en_attente"))

    def test_stale_payment_form_cannot_undo_a_confirmation(self):
        order = self._order()
        stale_order = Order.objects.select_related("payment").get(pk=order.pk)
        self.client.force_login(self.users["vendeur"])
        self.client.post(reverse("confirmer_commande", args=[order.pk]), {"action": "confirmer"})
        paid_at = Payment.objects.get(commande=order).date_paiement
        self.client.force_login(self.owner)
        with patch("payments.views.get_object_or_404", return_value=stale_order):
            response = self.client.post(reverse("payment_form", args=[order.pk]), {"methode": "especes"})
        self.assertEqual(response.status_code, 200)
        payment = Payment.objects.get(commande=order)
        self.assertEqual((payment.statut, payment.methode, payment.date_paiement), ("paye", "orange_money", paid_at))

    @patch("payments.views._wave_api_key", return_value="")
    def test_all_five_web_methods_remain_pending_and_show_truthful_status(self, _key):
        # Le moyen online ajouté porte le catalogue à six méthodes.
        self.product.stock = 12
        self.product.save(update_fields=["stock"])
        for method, label in Payment.METHODES:
            with self.subTest(method=method):
                response = self._checkout(method=method, delivery="standard")
                self.assertContains(response, "en attente de confirmation")
                order = Order.objects.latest("pk")
                response = self.client.post(reverse("payment_form", args=[order.pk]), {"methode": method})
                self.assertEqual(response.status_code, 200)
                payment = Payment.objects.get(commande=order)
                self.assertEqual((payment.statut, payment.methode, payment.montant), ("en_attente", method, 1600))
                self.assertIsNone(payment.date_paiement)
                self.assertEqual(order.frais_livraison, 0)
                self.assertNotIn("paiement sim" + "ul", response.content.decode().lower())
                self.assertNotContains(response, "simulation" + "_result")
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)

    @patch("payments.views._wave_api_key", return_value="private-test-key")
    @patch("payments.views._wave_request")
    def test_existing_wave_checkout_has_valid_return_urls_without_network(self, wave_request, _key):
        order = self._order()
        wave_request.return_value = {"id": "cos-e2e", "wave_launch_url": "https://pay.wave.com/e2e"}
        self.client.force_login(self.owner)
        response = self.client.post(reverse("payment_form", args=[order.pk]), {"methode": "wave"})
        self.assertEqual((response.status_code, response.url), (302, "https://pay.wave.com/e2e"))
        payload = wave_request.call_args.kwargs["payload"]
        self.assertTrue(payload["success_url"].endswith(reverse("wave_payment_success", args=[order.pk])))
        self.assertTrue(payload["error_url"].endswith(reverse("wave_payment_error", args=[order.pk])))
        self.assertEqual(payload["amount"], "4100")
        self.assertNotIn("private-test-key", response.content.decode())
        self.assertEqual(Payment.objects.get(commande=order).statut, "en_attente")

    @patch("payments.views._wave_get_checkout")
    def test_wave_return_requires_server_confirmation_and_is_idempotent(self, get_checkout):
        self._checkout(method="wave")
        order = Order.objects.get()
        Payment.objects.filter(commande=order).update(reference="cos-e2e")
        url = reverse("wave_payment_success", args=[order.pk])
        get_checkout.return_value = {"payment_status": "pending"}
        self.client.get(url, {"status": "paye"})
        self.assertEqual(Payment.objects.get(commande=order).statut, "en_attente")
        get_checkout.return_value = {
            "payment_status": "succeeded", "checkout_status": "complete",
            "client_reference": f"ORDER-{order.pk}", "amount": "4100", "currency": "XOF",
        }
        self.assertEqual(self.client.get(url).status_code, 200)
        count = self.owner.notifications.count()
        self.client.get(url)
        order.refresh_from_db(); self.product.refresh_from_db()
        self.assertEqual((order.statut, order.payment.statut, self.product.stock), ("confirmee", "paye", 8))
        self.assertEqual(self.owner.notifications.count(), count)
        self.assertEqual(self.client.get(reverse("order_receipt", args=[order.pk])).status_code, 200)
        self.client.force_login(self.other)
        for route in ("wave_payment_success", "wave_payment_error"):
            self.assertEqual(self.client.get(reverse(route, args=[order.pk])).status_code, 404)

    def test_wave_rejects_wrong_order_method_amount_and_cancelled_order(self):
        order = self._order()
        other_order = self._order(owner=self.other)
        payment = order.payment
        with self.assertRaises(ValueError):
            _confirm_wave_payment(other_order, payment, {})
        with self.assertRaises(ValueError):
            _confirm_wave_payment(order, payment, {})
        Payment.objects.filter(pk=payment.pk).update(methode="wave")
        data = {"payment_status": "succeeded", "checkout_status": "complete", "client_reference": f"ORDER-{order.pk}"}
        for amount in ("bad", "NaN", "Infinity", "0", "4101"):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                _confirm_wave_payment(order, payment, {**data, "amount": amount})
        Order.objects.filter(pk=order.pk).update(statut="annulee")
        with self.assertRaises(ValueError):
            _confirm_wave_payment(order, payment, {**data, "amount": "4100"})
        self.assertEqual(Payment.objects.get(pk=payment.pk).statut, "en_attente")

    def test_role_matrix_for_professional_pages(self):
        groups = {
            "admin": ("admin_dashboard", "admin_utilisateurs", "admin_vendeurs", "admin_vendeurs_performance", "admin_produits", "admin_categories", "admin_commandes", "admin_paiements", "admin_clients", "admin_alertes", "admin_activites", "admin_parametres"),
            "vendeur": ("vendeur_dashboard", "historique_ventes", "vendeur_stock", "vendeur_commandes", "vendeur_liste_produits", "vendeur_ajouter_produit", "vendeur_paniers"),
            "comptable": ("comptable_dashboard", "comptable_transactions", "comptable_export_csv", "comptable_calculs"),
        }
        for role, user in {**self.users, "staff-client": self.staff}.items():
            self.client.force_login(user)
            for space, routes in groups.items():
                for route in routes:
                    with self.subTest(role=role, route=route):
                        response = self.client.get(reverse(route))
                        if role == "admin" or role == space:
                            self.assertEqual(response.status_code, 200)
                        else:
                            self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)

    def test_sensitive_mutations_refuse_cross_role_access(self):
        order = self._order()
        targets = (
            ("admin_commande_statut", [order.pk], {"statut": "confirmee"}, {"admin"}),
            ("admin_paiement_statut", [order.payment.pk], {"statut": "paye"}, {"admin"}),
            ("changer_role_utilisateur", [self.owner.profile.pk], {"role": "admin"}, {"admin"}),
            ("confirmer_commande", [order.pk], {"action": "confirmer"}, {"admin", "vendeur"}),
            ("enregistrer_vente", [], {"produit": self.product.pk, "quantite": 1}, {"admin", "vendeur"}),
            ("vendeur_toggle_produit", [self.product.pk], {}, {"admin", "vendeur"}),
            ("vendeur_modifier_produit", [self.product.pk], {"nom": "changed"}, {"admin", "vendeur"}),
            ("vendeur_ajouter_categorie", [], {"nom_categorie": "forbidden"}, {"admin", "vendeur"}),
        )
        for role, user in {**self.users, "staff-client": self.staff}.items():
            self.client.force_login(user)
            for route, args, data, allowed in targets:
                if role in allowed:
                    continue
                with self.subTest(role=role, route=route):
                    self.assertRedirects(self.client.post(reverse(route, args=args), data), reverse("home"), fetch_redirect_response=False)
        order.refresh_from_db(); self.product.refresh_from_db(); self.owner.profile.refresh_from_db()
        self.assertEqual((order.statut, order.payment.statut), ("en_attente", "en_attente"))
        self.assertEqual(self.owner.profile.role, "client")
        self.assertEqual(self.product.stock, 10)
        self.assertTrue(self.product.actif)
        self.assertFalse(Vente.objects.exists())

    def test_sensitive_detail_permissions(self):
        order = self._order(paid=True)
        sale = Vente.objects.create(vendeur=self.users["vendeur"], produit=self.product, quantite=1, prix_unitaire=800, montant_total=800)
        for role in ("client", "vendeur", "comptable", "admin"):
            self.client.force_login(self.users[role])
            for route, args, allowed in (
                ("vendeur_commande_detail", [order.pk], {"vendeur", "admin"}),
                ("admin_utilisateur_detail", [self.owner.profile.pk], {"admin"}),
                ("admin_vendeur_performance_detail", [self.users["vendeur"].profile.pk], {"admin"}),
                ("comptable_transaction_detail", [f"V-{sale.pk}"], {"comptable", "admin"}),
                ("comptable_transaction_detail", [f"P-{order.payment.pk}"], {"comptable", "admin"}),
            ):
                with self.subTest(role=role, route=route):
                    response = self.client.get(reverse(route, args=args))
                    self.assertEqual(response.status_code, 200 if role in allowed else 302)

    def test_invalid_catalogue_filters_do_not_raise_500(self):
        for query in ({"categorie": "abc"}, {"categorie": "9" * 30}, {"prix_min": "abc"}, {"prix_max": "NaN"}):
            with self.subTest(query=query):
                self.assertEqual(self.client.get(reverse("product_list"), query).status_code, 200)

    def test_invalid_professional_filters_do_not_raise_500(self):
        self.client.force_login(self.users["admin"])
        for route in ("admin_commandes", "admin_paiements", "admin_activites", "historique_ventes"):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(route), {"date_debut": "2026-99-99", "date_fin": "bad", "page": "bad"}).status_code, 200)
        self.assertEqual(self.client.get(reverse("vendeur_liste_produits"), {"categorie": "abc"}).status_code, 200)

    def test_invalid_counter_sale_creates_nothing_and_keeps_stock(self):
        self.client.force_login(self.users["vendeur"])
        for data in ({"produit": "abc", "quantite": 1}, {"produit": self.product.pk, "quantite": 1, "methode_paiement": "invalid"}, {"produit": self.product.pk, "quantite": 11}):
            with self.subTest(data=data):
                self.assertRedirects(self.client.post(reverse("enregistrer_vente"), data), reverse("vendeur_dashboard"))
        self.assertFalse(Vente.objects.exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)

    def test_checkout_refuses_inactive_product_and_combined_excess_quantity(self):
        cart = Cart.objects.create(utilisateur=self.owner)
        CartItem.objects.create(panier=cart, produit=self.product, prix=800, quantite=6)
        CartItem.objects.create(panier=cart, produit=self.product, prix=800, quantite=6)
        self.client.force_login(self.owner)
        data = {"finalize": "1", "adresse": "Rue", "ville": "Bamako", "mode_livraison": "standard", "methode": "especes"}
        self.assertEqual(self.client.post(reverse("create_order"), data).status_code, 200)
        self.assertFalse(Order.objects.exists())
        cart.items.update(quantite=1)
        Product.objects.filter(pk=self.product.pk).update(actif=False)
        self.assertEqual(self.client.post(reverse("create_order"), data).status_code, 200)
        self.assertFalse(Order.objects.exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)

    def test_admin_pagination_retains_all_payment_filters(self):
        for _ in range(16):
            self._order()
        self.client.force_login(self.users["admin"])
        filters = {"methode": "orange_money", "statut": "en_attente", "q": self.owner.username, "date_debut": timezone.localdate().isoformat()}
        response = self.client.get(reverse("admin_paiements"), filters)
        links = [html.unescape(link) for link in re.findall(r'href="([^"]+)"', response.content.decode())]
        next_page = next(link for link in links if parse_qs(urlsplit(link).query).get("page") == ["2"])
        query = parse_qs(urlsplit(next_page).query)
        for key, value in filters.items():
            self.assertEqual(query[key], [value])
        second = self.client.get(reverse("admin_paiements") + next_page)
        self.assertEqual(second.context["page_obj"].number, 2)
        self.assertEqual(second.context["page_obj"].paginator.count, 16)

    def test_seller_product_category_create_edit_toggle_and_navigation(self):
        self.client.force_login(self.users["vendeur"])
        self.assertEqual(self.client.post(reverse("vendeur_ajouter_categorie"), {"nom_categorie": "Seller E2E"}).status_code, 302)
        category = Category.objects.get(nom="Seller E2E")
        data = {"nom": "Seller product", "prix": "1200", "prix_promotion": "1100", "stock": "3", "categorie": category.pk, "actif": "on"}
        self.assertRedirects(self.client.post(reverse("vendeur_ajouter_produit"), data), reverse("vendeur_liste_produits"))
        product = Product.objects.get(nom="Seller product")
        self.assertEqual(self.client.get(reverse("product_detail", args=[product.slug])).status_code, 200)
        data["prix"] = "1300"
        self.assertRedirects(self.client.post(reverse("vendeur_modifier_produit", args=[product.pk]), data), reverse("vendeur_liste_produits"))
        product.refresh_from_db()
        self.assertEqual(product.prix, Decimal("1300"))
        self.client.post(reverse("vendeur_toggle_produit", args=[product.pk]))
        self.assertEqual(self.client.get(reverse("product_detail", args=[product.slug])).status_code, 404)
        self.client.post(reverse("vendeur_toggle_produit", args=[product.pk]))
        self.assertEqual(self.client.get(reverse("product_detail", args=[product.slug])).status_code, 200)

    def test_offline_sync_keeps_orders_and_notifications_private(self):
        order = self._order()
        self._order(owner=self.other)
        self.client.force_login(self.owner)
        response = self.client.get("/offline/sync/")
        self.assertEqual(response.status_code, 200)
        data = response.json()["payload"]
        self.assertEqual([row["id"] for row in data["orders"]], [order.pk])
        self.assertEqual({row["id"] for row in data["notifications"]}, set(self.owner.notifications.values_list("pk", flat=True)))
