import hashlib
import hmac
import json
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.urls import reverse
from django.utils.translation import get_language

from .base import PaymentProvider


class CinetPayProvider(PaymentProvider):
    """Hosted CinetPay checkout using the documented v2 API."""

    name = "cinetpay"
    base_url = "https://api-checkout.cinetpay.com/v2"

    def __init__(self):
        self.api_key = settings.CINETPAY_API_KEY
        self.site_id = settings.CINETPAY_SITE_ID
        self.secret_key = settings.CINETPAY_SECRET_KEY

    @property
    def is_configured(self):
        return bool(self.api_key and self.site_id and self.secret_key)

    def _request(self, path, payload):
        if not self.is_configured:
            raise RuntimeError("Le paiement en ligne CinetPay n'est pas encore configuré.")
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            self.base_url + path,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8") or "{}")
        except (HTTPError, URLError, ValueError) as exc:
            raise RuntimeError("Le provider CinetPay est momentanément indisponible.") from exc

    def create_payment(self, request, order, payment):
        try:
            amount = Decimal(str(order.total()))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise RuntimeError("Le montant CinetPay est invalide.") from exc
        if not amount.is_finite() or amount != amount.to_integral_value() or int(amount) < 100 or int(amount) % 5:
            raise RuntimeError("Le montant CinetPay doit être un entier d'au moins 100 FCFA et un multiple de 5.")

        user = order.utilisateur
        profile = getattr(user, "profile", None)
        payload = {
            "apikey": self.api_key,
            "site_id": self.site_id,
            "transaction_id": payment.provider_reference,
            "amount": int(amount),
            "currency": "XOF",
            "description": f"Commande {order.id}",
            "customer_name": user.last_name or user.username,
            "customer_surname": user.first_name or user.username,
            "customer_email": user.email or f"client-{user.id}@example.invalid",
            "customer_phone_number": getattr(profile, "telephone", "") or "",
            "customer_address": order.adresse_livraison or "",
            "customer_city": order.ville_livraison or "",
            "customer_country": "ML",
            "return_url": request.build_absolute_uri(reverse("online_payment_return")),
            "notify_url": request.build_absolute_uri(reverse("cinetpay_webhook")),
            "channels": "ALL",
            "lang": "en" if (get_language() or "fr").startswith("en") else "fr",
            "metadata": f"ORDER-{order.id};PAYMENT-{payment.id}",
        }
        response = self._request("/payment", payload)
        data = response.get("data") or {}
        checkout_url = data.get("payment_url")
        if str(response.get("code")) not in {"00", "201"} or not checkout_url:
            raise RuntimeError(response.get("message") or "CinetPay n'a pas retourné d'URL de paiement.")
        return {
            "provider_reference": payment.provider_reference,
            "checkout_url": checkout_url,
            "payload": data,
        }

    def verify_payment(self, reference):
        response = self._request(
            "/payment/check",
            {"apikey": self.api_key, "site_id": self.site_id, "transaction_id": reference},
        )
        data = response.get("data") or {}
        raw_status = str(data.get("status") or "").upper()
        status = {"ACCEPTED": "successful", "SUCCESS": "successful", "REFUSED": "failed", "FAILED": "failed"}.get(raw_status, "pending")
        return {
            "status": status,
            "provider_status": raw_status,
            "amount": data.get("amount"),
            "currency": data.get("currency"),
            "tx_ref": reference,
            "id": data.get("operator_id") or reference,
            "raw": response,
        }

    def handle_callback(self, request):
        return {
            "reference": request.POST.get("cpm_trans_id") or request.GET.get("cpm_trans_id") or request.GET.get("transaction_id"),
            "transaction_id": request.POST.get("cpm_trans_id") or request.GET.get("cpm_trans_id") or request.GET.get("transaction_id"),
        }

    def verify_webhook_signature(self, data, received_token):
        if not self.secret_key or not received_token:
            return False
        fields = (
            "cpm_site_id", "cpm_trans_id", "cpm_trans_date", "cpm_amount", "cpm_currency",
            "signature", "payment_method", "cel_phone_num", "cpm_phone_prefixe", "cpm_language",
            "cpm_version", "cpm_payment_config", "cpm_page_action", "cpm_custom",
            "cpm_designation", "cpm_error_message",
        )
        message = "".join(str(data.get(field, "")) for field in fields)
        expected = hmac.new(self.secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, received_token.strip())
