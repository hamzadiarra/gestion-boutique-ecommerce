from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from orders.models import Order
from .models import Payment


class PaymentFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("client", password="secret123")
        self.order = Order.objects.create(utilisateur=self.user)
        self.client.login(username="client", password="secret123")

    def test_payment_success_is_idempotent_for_notification(self):
        response = self.client.post(reverse("payment_form", args=[self.order.id]), {"methode": "wave", "simulation_result": "paye"})
        self.assertEqual(response.status_code, 200)
        payment = Payment.objects.get(commande=self.order)
        self.assertEqual(payment.statut, "paye")
        count = self.user.notifications.filter(type_notification="paiement").count()
        payment.save()
        self.assertEqual(self.user.notifications.filter(type_notification="paiement").count(), count)

    def test_invalid_payment_method_is_rejected(self):
        response = self.client.post(reverse("payment_form", args=[self.order.id]), {"methode": "unknown", "simulation_result": "paye"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "moyen de paiement valide")
