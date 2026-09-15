import base64
import hashlib
import hmac
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .base import PaymentProvider
from django.conf import settings


class FlutterwaveProvider(PaymentProvider):
    name = "flutterwave"
    base_url = "https://api.flutterwave.com/v3"

    def __init__(self):
        self.secret_key = settings.PAYMENT_SECRET_KEY
        self.webhook_secret = settings.PAYMENT_WEBHOOK_SECRET

    def _request(self, path, method="GET", payload=None):
        if not self.secret_key:
            raise RuntimeError("Le provider de paiement en ligne n'est pas configuré.")
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Authorization": f"Bearer {self.secret_key}", "Accept": "application/json"}
        if body:
            headers["Content-Type"] = "application/json"
        try:
            with urlopen(Request(self.base_url + path, data=body, headers=headers, method=method), timeout=20) as response:
                return json.loads(response.read().decode() or "{}")
        except (HTTPError, URLError, ValueError) as exc:
            raise RuntimeError("Le provider de paiement est momentanément indisponible.") from exc

    def create_payment(self, request, order, payment):
        from django.urls import reverse
        payload = {
            "tx_ref": payment.provider_reference,
            "amount": str(order.total()),
            "currency": "XOF",
            "redirect_url": request.build_absolute_uri(reverse("online_payment_return")),
            "customer": {"email": order.utilisateur.email or f"client-{order.utilisateur_id}@example.invalid", "name": order.utilisateur.get_full_name() or order.utilisateur.username},
            "meta": {"order_id": order.id, "payment_id": payment.id},
            "customizations": {"title": "Gestion Boutique"},
        }
        data = self._request("/payments", method="POST", payload=payload).get("data") or {}
        checkout_url = data.get("link")
        if not checkout_url:
            raise RuntimeError("Le provider n'a pas retourné d'URL de checkout.")
        return {"provider_reference": payment.provider_reference, "checkout_url": checkout_url, "payload": data}

    def verify_payment(self, reference):
        data = self._request(f"/transactions/{reference}/verify").get("data") or {}
        return {"status": data.get("status"), "amount": data.get("amount"), "currency": data.get("currency"), "tx_ref": data.get("tx_ref"), "id": data.get("id"), "raw": data}

    def handle_callback(self, request):
        return {"reference": request.GET.get("tx_ref"), "transaction_id": request.GET.get("transaction_id"), "status": request.GET.get("status")}

    def verify_webhook_signature(self, raw_body, signature, header_name="verif-hash"):
        if not self.webhook_secret or not signature:
            return False
        signature = signature.strip()
        if header_name.lower() == "flutterwave-signature":
            expected = base64.b64encode(hmac.new(self.webhook_secret.encode(), raw_body, hashlib.sha256).digest()).decode()
            return hmac.compare_digest(expected, signature)
        return hmac.compare_digest(self.webhook_secret, signature)
