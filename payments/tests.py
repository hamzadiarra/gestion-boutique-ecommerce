import hashlib
import hmac
import json
import base64

from django.conf import settings
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase, override_settings
from unittest.mock import patch
from django.urls import reverse
from django.utils import timezone

from cart.models import Cart, CartItem
from categories.models import Category
from orders.models import Order
from products.models import Product
from .models import Payment
from .views import _confirm_wave_payment
from .views import _confirm_online_payment
from .providers import get_payment_provider
from .providers.cinetpay import CinetPayProvider
from .providers.moov_money import get_moov_money_instructions
from .providers.flutterwave import FlutterwaveProvider


class FlutterwaveWebhookSignatureTests(TestCase):
    @override_settings(PAYMENT_SECRET_KEY="test-key", PAYMENT_WEBHOOK_SECRET="webhook-secret")
    def test_current_flutterwave_signature_is_hmac_sha256_base64(self):
        body = b'{"data":{"id":123}}'
        signature = base64.b64encode(hmac.new(b"webhook-secret", body, hashlib.sha256).digest()).decode()
        provider = FlutterwaveProvider()
        self.assertTrue(provider.verify_webhook_signature(body, signature, "flutterwave-signature"))
        self.assertFalse(provider.verify_webhook_signature(body, "wrong", "flutterwave-signature"))

    @override_settings(PAYMENT_SECRET_KEY="test-key", PAYMENT_WEBHOOK_SECRET="legacy-secret")
    def test_v3_verif_hash_remains_supported(self):
        provider = FlutterwaveProvider()
        self.assertTrue(provider.verify_webhook_signature(b"{}", "legacy-secret", "verif-hash"))


class FakeOnlineProvider:
    name = "flutterwave"

    def __init__(self, verified=None):
        self.verified = verified or {}
        self.created = None

    def create_payment(self, request, order, payment):
        self.created = (order.total(), payment.provider_reference)
        return {"checkout_url": "https://sandbox.example/checkout", "payload": {"mode": "test"}}

    def handle_callback(self, request):
        return {"reference": request.GET.get("tx_ref"), "transaction_id": request.GET.get("transaction_id")}

    def verify_payment(self, reference):
        return self.verified

    def verify_webhook_signature(self, body, signature, header_name="verif-hash"):
        return signature == "valid"


class OnlinePaymentFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("online-client", password="secret123", email="client@example.com")
        self.other = User.objects.create_user("other-client", password="secret123")
        self.category = Category.objects.create(nom="Tests online")
        self.product = Product.objects.create(categorie=self.category, nom="Sac", prix=1250, stock=3)
        self.order = Order.objects.create(utilisateur=self.user, frais_livraison=250)
        from orders.models import OrderItem
        OrderItem.objects.create(commande=self.order, produit=self.product, prix=1250, quantite=1)
        self.payment = Payment.objects.create(commande=self.order, montant=self.order.total(), methode="online", provider="flutterwave", provider_reference="ONL-TEST-REF")
        self.client.login(username="online-client", password="secret123")

    def test_owner_starts_online_payment_with_server_amount(self):
        fake = FakeOnlineProvider()
        with patch("payments.views.get_payment_provider", return_value=fake):
            response = self.client.post(reverse("start_online_payment", args=[self.order.id]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(fake.created, (self.order.total(), "ONL-TEST-REF"))
        self.assertEqual(self.product.stock, 3)


class CinetPayProviderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("cinet-client", password="secret123", email="cinet@example.com", first_name="Awa", last_name="Traore")
        self.category = Category.objects.create(nom="CinetPay")
        self.product = Product.objects.create(categorie=self.category, nom="Sac", prix=1250, stock=3)
        self.order = Order.objects.create(utilisateur=self.user, frais_livraison=250, adresse_livraison="Rue 1", ville_livraison="Bamako")
        from orders.models import OrderItem
        OrderItem.objects.create(commande=self.order, produit=self.product, prix=1250, quantite=1)
        self.payment = Payment.objects.create(commande=self.order, montant=self.order.total(), methode="online", provider="cinetpay", provider_reference="ONL-CINET-1")
        self.request = RequestFactory().get("/payments/1/")
        self.request.user = self.user

    @override_settings(PAYMENT_PROVIDER="cinetpay", CINETPAY_API_KEY="api-key", CINETPAY_SITE_ID="12345", CINETPAY_SECRET_KEY="secret")
    @patch("payments.providers.cinetpay.urlopen")
    def test_create_payment_uses_server_amount_and_returns_hosted_url(self, urlopen_mock):
        response = type("Response", (), {"read": lambda self: b'{"code":"201","data":{"payment_token":"token-1","payment_url":"https://checkout.cinetpay.com/payment/token-1"}}', "__enter__": lambda self: self, "__exit__": lambda self, *args: None})()
        urlopen_mock.return_value = response
        result = CinetPayProvider().create_payment(self.request, self.order, self.payment)
        payload = json.loads(urlopen_mock.call_args.args[0].data.decode())
        self.assertEqual(payload["amount"], 1500)
        self.assertEqual(payload["currency"], "XOF")
        self.assertEqual(payload["transaction_id"], "ONL-CINET-1")
        self.assertEqual(result["checkout_url"], "https://checkout.cinetpay.com/payment/token-1")
        self.assertNotIn("secret", json.dumps(result["payload"]).lower())

    @override_settings(PAYMENT_PROVIDER="cinetpay", CINETPAY_API_KEY="", CINETPAY_SITE_ID="", CINETPAY_SECRET_KEY="")
    def test_missing_configuration_is_controlled(self):
        with self.assertRaisesMessage(RuntimeError, "CinetPay n'est pas encore configuré"):
            CinetPayProvider().create_payment(self.request, self.order, self.payment)

    @override_settings(PAYMENT_PROVIDER="cinetpay", CINETPAY_API_KEY="api", CINETPAY_SITE_ID="site", CINETPAY_SECRET_KEY="secret")
    @patch("payments.providers.cinetpay.urlopen")
    def test_verify_maps_cinetpay_statuses(self, urlopen_mock):
        def response_for(status):
            return type("Response", (), {"read": lambda self: json.dumps({"code": "00", "data": {"status": status, "amount": "1500", "currency": "XOF", "operator_id": "OP-1"}}).encode(), "__enter__": lambda self: self, "__exit__": lambda self, *args: None})()
        urlopen_mock.return_value = response_for("ACCEPTED")
        self.assertEqual(CinetPayProvider().verify_payment("ONL-CINET-1")["status"], "successful")
        urlopen_mock.return_value = response_for("REFUSED")
        self.assertEqual(CinetPayProvider().verify_payment("ONL-CINET-1")["status"], "failed")
        urlopen_mock.return_value = response_for("WAITING")
        self.assertEqual(CinetPayProvider().verify_payment("ONL-CINET-1")["status"], "pending")

    @override_settings(PAYMENT_PROVIDER="flutterwave")
    def test_factory_keeps_flutterwave(self):
        self.assertEqual(get_payment_provider().name, "flutterwave")

    @override_settings(PAYMENT_PROVIDER="cinetpay", CINETPAY_API_KEY="api", CINETPAY_SITE_ID="site", CINETPAY_SECRET_KEY="secret")
    def test_factory_selects_cinetpay(self):
        self.assertEqual(get_payment_provider().name, "cinetpay")

    @override_settings(PAYMENT_PROVIDER="unknown")
    def test_factory_rejects_unknown_provider(self):
        with self.assertRaisesMessage(RuntimeError, "Aucun provider"):
            get_payment_provider()

    @override_settings(PAYMENT_PROVIDER="cinetpay", CINETPAY_API_KEY="api", CINETPAY_SITE_ID="site", CINETPAY_SECRET_KEY="secret")
    @patch.object(CinetPayProvider, "verify_payment", return_value={"status": "successful", "provider_status": "ACCEPTED", "amount": "1500", "currency": "XOF", "tx_ref": "ONL-CINET-1", "id": "OP-1", "raw": {"status": "ACCEPTED"}})
    def test_webhook_verifies_success_and_is_idempotent_without_stock_or_double_confirmation(self, verify_mock):
        provider = CinetPayProvider()
        data = {"cpm_site_id": "site", "cpm_trans_id": "ONL-CINET-1", "cpm_trans_date": "2026-09-14 20:00:00", "cpm_amount": "1500", "cpm_currency": "XOF", "signature": "sig", "payment_method": "CARD", "cel_phone_num": "", "cpm_phone_prefixe": "223", "cpm_language": "fr", "cpm_version": "V4", "cpm_payment_config": "Single", "cpm_page_action": "Payment", "cpm_custom": "ORDER-1;PAYMENT-1", "cpm_designation": "Commande 1", "cpm_error_message": ""}
        token = hmac.new(b"secret", "".join(data.values()).encode(), hashlib.sha256).hexdigest()
        self.client.force_login(self.user)
        first = self.client.post(reverse("cinetpay_webhook"), data=data, HTTP_X_TOKEN=token)
        self.assertEqual(first.status_code, 200)
        self.payment.refresh_from_db(); self.order.refresh_from_db()
        self.assertEqual(self.payment.statut, "paye")
        self.assertEqual(self.order.statut, "confirmee")
        self.assertEqual(self.product.refresh_from_db() or self.product.stock, 3)
        second = self.client.post(reverse("cinetpay_webhook"), data=data, HTTP_X_TOKEN=token)
        self.assertEqual(second.json()["already_processed"], True)
        verify_mock.assert_called_once()

class OnlinePaymentRemainingFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("online-client-remaining", password="secret123", email="client@example.com")
        self.other = User.objects.create_user("other-client-remaining", password="secret123")
        self.category = Category.objects.create(nom="Tests online remaining")
        self.product = Product.objects.create(categorie=self.category, nom="Sac", prix=1250, stock=3)
        self.order = Order.objects.create(utilisateur=self.user, frais_livraison=250)
        from orders.models import OrderItem
        OrderItem.objects.create(commande=self.order, produit=self.product, prix=1250, quantite=1)
        self.payment = Payment.objects.create(commande=self.order, montant=self.order.total(), methode="online", provider="flutterwave", provider_reference="ONL-TEST-REF")
        self.client.login(username="online-client-remaining", password="secret123")

    def test_other_user_is_refused(self):
        self.client.logout()
        self.client.login(username=self.other.username, password="secret123")
        with patch("payments.views.get_payment_provider") as provider:
            response = self.client.post(reverse("start_online_payment", args=[self.order.id]))
        self.assertEqual(response.status_code, 404)
        provider.assert_not_called()

    def test_return_verifies_success_and_is_idempotent(self):
        verified = {"status": "successful", "amount": str(self.order.total()), "currency": "XOF", "tx_ref": "ONL-TEST-REF", "id": "TX-99", "raw": {"status": "successful"}}
        fake = FakeOnlineProvider(verified)
        with patch("payments.views.get_payment_provider", return_value=fake):
            response = self.client.get(reverse("online_payment_return") + "?tx_ref=ONL-TEST-REF&transaction_id=99")
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db(); self.order.refresh_from_db()
        self.assertEqual(self.payment.statut, "paye")
        self.assertEqual(self.order.statut, "confirmee")
        self.assertEqual(self.product.stock, 3)
        with patch("payments.views.get_payment_provider", return_value=fake):
            response = self.client.get(reverse("online_payment_return") + "?tx_ref=ONL-TEST-REF&transaction_id=99")
        self.assertEqual(response.status_code, 200)

    def test_wrong_amount_does_not_confirm(self):
        fake = FakeOnlineProvider({"status": "successful", "amount": "1", "currency": "XOF", "tx_ref": "ONL-TEST-REF", "id": "TX-1"})
        with patch("payments.views.get_payment_provider", return_value=fake):
            self.client.get(reverse("online_payment_return") + "?tx_ref=ONL-TEST-REF")
        self.payment.refresh_from_db(); self.order.refresh_from_db()
        self.assertEqual(self.payment.statut, "en_attente")
        self.assertEqual(self.order.statut, "en_attente")

    def test_signed_webhook_confirms_and_invalid_signature_is_rejected(self):
        fake = FakeOnlineProvider({"status": "successful", "amount": str(self.order.total()), "currency": "XOF", "tx_ref": "ONL-TEST-REF", "id": "TX-2"})
        payload = json.dumps({"data": {"id": "TX-2", "tx_ref": "ONL-TEST-REF"}})
        with patch("payments.views.get_payment_provider", return_value=fake):
            bad = self.client.post(reverse("online_payment_webhook"), data=payload, content_type="application/json", HTTP_VERIF_HASH="bad")
            good = self.client.post(reverse("online_payment_webhook"), data=payload, content_type="application/json", HTTP_VERIF_HASH="valid")
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(good.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.statut, "paye")


class PaymentFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("client", password="secret123")
        self.order = Order.objects.create(utilisateur=self.user)
        self.client.login(username="client", password="secret123")

    def test_payment_success_is_idempotent_for_notification(self):
        payment = Payment.objects.create(commande=self.order, montant=0, methode="wave", statut="en_attente")
        wave_data = {
            "payment_status": "succeeded",
            "checkout_status": "complete",
            "client_reference": f"ORDER-{self.order.id}",
            "amount": "0",
        }
        _confirm_wave_payment(self.order, payment, wave_data)
        payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(payment.statut, "paye")
        self.assertEqual(self.order.statut, "confirmee")
        self.assertIsNotNone(payment.date_paiement)
        count = self.user.notifications.filter(type_notification="paiement").count()
        _confirm_wave_payment(self.order, payment, wave_data)
        self.assertEqual(self.user.notifications.filter(type_notification="paiement").count(), count)

    def test_already_paid_payment_does_not_regress(self):
        payment = Payment.objects.create(commande=self.order, montant=0, methode="wave", statut="paye", date_paiement=timezone.now())
        count_before = self.user.notifications.filter(type_notification="paiement").count()
        _confirm_wave_payment(self.order, payment, {})
        payment.refresh_from_db()
        self.assertEqual(payment.statut, "paye")
        self.assertEqual(self.user.notifications.filter(type_notification="paiement").count(), count_before)

    def test_invalid_payment_method_is_rejected(self):
        response = self.client.post(reverse("payment_form", args=[self.order.id]), {"methode": "unknown"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "moyen de paiement valide")


class MoovMoneyFlowValidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("client-moov", password="secret123")
        self.order = Order.objects.create(utilisateur=self.user)
        self.client.login(username="client-moov", password="secret123")

        self.category = Category.objects.create(nom="Vêtements")
        self.product = Product.objects.create(
            categorie=self.category,
            nom="T-shirt",
            prix=100,
            stock=5,
        )

    def _post_moov_webhook(self, order, status="confirmed", custom_payload=None, signature=None):
        payload = custom_payload or {
            "order_id": order.id,
            "status": status,
        }
        body = json.dumps(payload)
        headers = {}
        if signature is None:
            signature = hmac.new(
                settings.MOOV_MONEY_WEBHOOK_SECRET.encode("utf-8"),
                body.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            headers["HTTP_X_MOOV_MONEY_SIGNATURE"] = f"sha256={signature}"
        else:
            headers["HTTP_X_MOOV_MONEY_SIGNATURE"] = signature

        return self.client.post(
            reverse("moov_money_webhook"),
            data=body,
            content_type="application/json",
            **headers,
        )

    @override_settings(MOOV_MONEY_API_BASE_URL="", MOOV_MONEY_CLIENT_ID="", MOOV_MONEY_CLIENT_SECRET="", MOOV_MONEY_MERCHANT_CODE="")
    def test_checkout_with_moov_money_keeps_payment_en_attente(self):
        response = self.client.post(
            reverse("payment_form", args=[self.order.id]),
            {"methode": "moov_money"},
        )
        self.assertEqual(response.status_code, 200)
        payment = Payment.objects.get(commande=self.order)
        self.assertEqual(payment.statut, "en_attente")
        self.assertEqual(payment.methode, "moov_money")

    @override_settings(MOOV_MONEY_API_BASE_URL="", MOOV_MONEY_CLIENT_ID="", MOOV_MONEY_CLIENT_SECRET="", MOOV_MONEY_MERCHANT_CODE="")
    def test_absence_config_api_is_not_an_error(self):
        response = self.client.post(
            reverse("payment_form", args=[self.order.id]),
            {"methode": "moov_money"},
        )
        self.assertEqual(response.status_code, 200)

    @override_settings(MOOV_MONEY_MERCHANT_CODE="")
    def test_absence_merchant_code_is_not_an_error(self):
        response = self.client.post(
            reverse("payment_form", args=[self.order.id]),
            {"methode": "moov_money"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "code marchand")

    def test_moov_money_callback_without_config_refuses(self):
        response = self.client.post(
            reverse("moov_money_callback", args=[self.order.id]),
        )
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, "n'est pas encore configurée", status_code=503)

    @override_settings(MOOV_MONEY_WEBHOOK_SECRET="")
    def test_moov_money_webhook_without_signature_or_secret_refuses(self):
        Payment.objects.create(commande=self.order, montant=self.order.total(), methode="moov_money", statut="en_attente")
        response = self.client.post(
            reverse("moov_money_webhook"),
            data=json.dumps({"order_id": self.order.id, "status": "confirmed"}),
            content_type="application/json",
            **{"HTTP_X_MOOV_MONEY_SIGNATURE": "sha256=test"},
        )
        self.assertEqual(response.status_code, 400)

    @override_settings(
        MOOV_MONEY_WEBHOOK_SECRET="supersecret",
        MOOV_MONEY_MERCHANT_CODE="M123",
    )
    def test_invalid_moov_money_webhook_does_not_mark_payment_paid(self):
        payment = Payment.objects.create(
            commande=self.order,
            montant=self.order.total(),
            methode="moov_money",
            statut="en_attente",
        )
        response = self._post_moov_webhook(self.order, status="failed")
        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(payment.statut, "en_attente")
        self.assertEqual(self.order.statut, "en_attente")

    @override_settings(
        MOOV_MONEY_WEBHOOK_SECRET="supersecret",
        MOOV_MONEY_MERCHANT_CODE="M123",
    )
    def test_order_stays_en_attente_if_payment_not_confirmed(self):
        Payment.objects.create(
            commande=self.order,
            montant=self.order.total(),
            methode="moov_money",
            statut="en_attente",
        )
        response = self._post_moov_webhook(self.order, status="failed")
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.statut, "en_attente")

    def _build_order_and_decrement_stock_once(self):
        cart = Cart.objects.create(utilisateur=self.user)
        CartItem.objects.create(panier=cart, produit=self.product, quantite=1, prix=self.product.prix)

        response = self.client.post(
            reverse("create_order"),
            {
                "finalize": "1",
                "adresse": "Rue 1",
                "ville": "Bamako",
                "mode_livraison": "standard",
                "note": "",
                "methode": "moov_money",
            },
        )

        self.assertEqual(response.status_code, 200)
        order = Order.objects.filter(utilisateur=self.user).latest("id")
        self.product.refresh_from_db()
        return order

    def test_stock_is_decremented_once(self):
        order = self._build_order_and_decrement_stock_once()
        self.assertEqual(self.product.stock, 4)

        payment = Payment.objects.get(commande=order)
        response = self._post_moov_webhook(
            order,
            status="failed",
            custom_payload={"order_id": order.id, "status": "failed"},
            signature=(
                "sha256="
                + hmac.new(
                    settings.MOOV_MONEY_WEBHOOK_SECRET.encode("utf-8"),
                    json.dumps({"order_id": order.id, "status": "failed"}).encode("utf-8"),
                    hashlib.sha256,
                ).hexdigest()
            ),
        )
        self.assertEqual(response.status_code, 400)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 4)
        payment.refresh_from_db()
        self.assertEqual(payment.statut, "en_attente")

    @override_settings(
        MOOV_MONEY_WEBHOOK_SECRET="supersecret",
        MOOV_MONEY_MERCHANT_CODE="M123",
    )
    def test_moov_money_confirmation_is_idempotent(self):
        payment = Payment.objects.create(
            commande=self.order,
            montant=self.order.total(),
            methode="moov_money",
            statut="paye",
            date_paiement=timezone.now(),
        )
        self.order.statut = "confirmee"
        self.order.save(update_fields=["statut"])

        response = self._post_moov_webhook(self.order, status="confirmed")
        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.statut, "paye")
        self.assertEqual(response.json().get("already_processed"), True)

    @override_settings(
        MOOV_MONEY_MERCHANT_CODE="CODECONF",
        MOOV_MONEY_API_BASE_URL="",
        MOOV_MONEY_CLIENT_ID="",
        MOOV_MONEY_CLIENT_SECRET="",
    )
    def test_merchant_code_is_only_read_from_settings(self):
        Payment.objects.create(
            commande=self.order,
            montant=self.order.total(),
            methode="moov_money",
            statut="en_attente",
        )
        self.assertEqual(get_moov_money_instructions(), "Effectuez votre paiement Moov Money avec le code marchand CODECONF.")
