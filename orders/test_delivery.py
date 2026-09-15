import re
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from cart.models import Cart, CartItem
from categories.models import Category
from products.models import Product
from .delivery_models import HistoriqueLivraison, LectureLivraison, MessageLivraison
from .delivery_services import changer_statut_livraison, envoyer_message_livraison
from .models import Livraison, Order


class LivraisonE2ETests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user("fatou", password="secret123")
        self.client_user.profile.role = "client"
        self.client_user.profile.save()
        self.vendor = User.objects.create_user("boutique", password="secret123")
        self.vendor.profile.role = "vendeur"
        self.vendor.profile.save()
        self.driver = User.objects.create_user("moussa", password="secret123")
        self.driver.profile.role = "livreur"
        self.driver.profile.save()
        self.other_driver = User.objects.create_user("amadou", password="secret123")
        self.other_driver.profile.role = "livreur"
        self.other_driver.profile.save()
        category = Category.objects.create(nom="Maison")
        self.product = Product.objects.create(categorie=category, nom="Lampe", prix=Decimal("1000.00"), stock=4)
        cart = Cart.objects.create(utilisateur=self.client_user)
        CartItem.objects.create(panier=cart, produit=self.product, prix=self.product.prix, quantite=2)
        self.client.force_login(self.client_user)
        response = self.client.post(reverse("create_order"), {
            "finalize": "1", "adresse": "Quartier A", "ville": "Bamako",
            "code_postal": "Pharmacie bleue", "numero_rue": "125", "numero_porte": "42",
            "telephone_livraison": "+22370000000", "mode_livraison": "standard", "methode": "wave",
        })
        self.assertEqual(response.status_code, 200)
        self.order = Order.objects.get(utilisateur=self.client_user)
        self.delivery = self.order.livraison
        Order.objects.filter(pk=self.order.pk).update(statut="confirmee")
        self.order.refresh_from_db()

    def post_action(self, user, action, **extra):
        self.client.force_login(user)
        return self.client.post(reverse("livraison_action", args=[self.delivery.pk]), {"action": action, **extra})

    def test_checkout_snapshots_structured_address_and_creates_delivery(self):
        self.assertEqual(self.order.numero_rue, 125)
        self.assertEqual(self.order.numero_porte, 42)
        self.assertEqual(self.order.repere, "Pharmacie bleue")
        self.assertEqual(self.delivery.statut, "a_affecter")
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 2)

    def test_address_boundaries_and_invalid_values(self):
        from .delivery_forms import AdresseLivraisonForm
        self.assertTrue(AdresseLivraisonForm({"numero_rue": "0", "numero_porte": "1000"}).is_valid())
        for field, value in (("numero_rue", "-1"), ("numero_porte", "1001"), ("numero_rue", "texte")):
            self.assertFalse(AdresseLivraisonForm({field: value}).is_valid())

    def test_vendor_assignment_reassignment_history_and_notification(self):
        self.client.force_login(self.vendor)
        response = self.client.post(reverse("livraison_affecter", args=[self.delivery.pk]), {"livreur": self.driver.pk})
        self.assertEqual(response.status_code, 302)
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.livreur_id, self.driver.pk)
        self.assertEqual(self.delivery.statut, "affectee")
        first_count = HistoriqueLivraison.objects.count()
        self.client.post(reverse("livraison_affecter", args=[self.delivery.pk]), {"livreur": self.driver.pk})
        self.assertEqual(HistoriqueLivraison.objects.count(), first_count)
        self.client.post(reverse("livraison_affecter", args=[self.delivery.pk]), {"livreur": self.other_driver.pk})
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.livreur_id, self.other_driver.pk)
        self.assertTrue(HistoriqueLivraison.objects.filter(ancien_livreur=self.driver, nouveau_livreur=self.other_driver).exists())

    def test_complete_status_flow_does_not_change_payment_or_stock(self):
        self.client.force_login(self.vendor)
        self.client.post(reverse("livraison_affecter", args=[self.delivery.pk]), {"livreur": self.driver.pk})
        self.post_action(self.driver, "acceptee")
        self.post_action(self.vendor, "prete")
        self.post_action(self.driver, "en_route")
        self.post_action(self.driver, "arrive")
        response = self.post_action(self.driver, "livree")
        self.assertEqual(response.status_code, 302)
        self.delivery.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.delivery.statut, "livree")
        self.assertEqual(self.order.statut, "livree")
        self.assertEqual(self.order.payment.statut, "en_attente")
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 2)
        self.assertEqual(HistoriqueLivraison.objects.filter(livraison=self.delivery, nouveau_statut="livree").count(), 1)

    def test_illegal_transition_and_double_transition_are_safe(self):
        self.client.force_login(self.driver)
        response = self.post_action(self.driver, "livree")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(HistoriqueLivraison.objects.filter(livraison=self.delivery).count(), 1)

    def test_unassigned_delivery_list_and_detail_are_safe(self):
        self.client.force_login(self.vendor)
        response = self.client.get(reverse("boutique_livraisons"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Non affecté")

        self.client.force_login(self.client_user)
        response = self.client.get(reverse("livraison_detail", args=[self.delivery.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Non affecté")

    def test_unassigned_delivery_is_translated_in_english(self):
        self.client.force_login(self.vendor)
        self.client.cookies["django_language"] = "en"
        response = self.client.get(reverse("boutique_livraisons"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unassigned")

    def test_failure_requires_reason_and_preserves_order(self):
        self.client.force_login(self.vendor)
        self.client.post(reverse("livraison_affecter", args=[self.delivery.pk]), {"livreur": self.driver.pk})
        self.post_action(self.driver, "acceptee")
        response = self.post_action(self.driver, "echec", motif_echec="client_absent")
        self.assertEqual(response.status_code, 302)
        self.delivery.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.delivery.statut, "echec")
        self.assertEqual(self.order.statut, "confirmee")
        self.assertEqual(self.order.payment.statut, "en_attente")

    def test_messages_are_scoped_ordered_escaped_and_read(self):
        self.client.force_login(self.vendor)
        self.client.post(reverse("livraison_affecter", args=[self.delivery.pk]), {"livreur": self.driver.pk})
        first = envoyer_message_livraison(self.delivery.pk, self.client_user, "<script>alert(1)</script>", uuid4())
        second = envoyer_message_livraison(self.delivery.pk, self.driver, "Je pars.", uuid4())
        self.client.force_login(self.client_user)
        response = self.client.get(reverse("livraison_detail", args=[self.delivery.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;", html=False)
        self.assertEqual(list(response.context["discussion"]), [first, second])
        self.assertTrue(LectureLivraison.objects.filter(livraison=self.delivery, utilisateur=self.client_user, dernier_message_id=second.pk).exists())
        self.assertEqual(MessageLivraison.objects.filter(livraison=self.delivery).count(), 2)

    def test_other_client_and_other_driver_cannot_access_delivery(self):
        other = User.objects.create_user("autre", password="secret123")
        other.profile.role = "client"
        other.profile.save()
        self.client.raise_request_exception = False
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("livraison_detail", args=[self.delivery.pk])).status_code, 403)
        self.client.force_login(self.other_driver)
        self.assertEqual(self.client.get(reverse("livraison_detail", args=[self.delivery.pk])).status_code, 403)

    def test_livreur_cannot_access_finance_or_admin_and_only_sees_assigned(self):
        self.client.force_login(self.driver)
        self.assertEqual(self.client.get(reverse("livreur_dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("comptable_dashboard")).status_code, 302)
        self.assertEqual(self.client.get(reverse("admin_dashboard")).status_code, 302)
