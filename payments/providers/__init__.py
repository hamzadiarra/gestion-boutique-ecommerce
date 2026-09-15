from django.conf import settings

from .flutterwave import FlutterwaveProvider
from .cinetpay import CinetPayProvider


def get_payment_provider():
    name = settings.PAYMENT_PROVIDER
    if name == "flutterwave":
        return FlutterwaveProvider()
    if name == "cinetpay":
        return CinetPayProvider()
    raise RuntimeError("Aucun provider de paiement en ligne n'est configuré.")
