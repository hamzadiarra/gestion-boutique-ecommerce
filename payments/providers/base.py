from abc import ABC, abstractmethod


class PaymentProvider(ABC):
    """Contrat minimal commun aux checkouts externes."""

    name = ""

    @abstractmethod
    def create_payment(self, request, order, payment):
        """Retourne au minimum {provider_reference, checkout_url}."""

    @abstractmethod
    def verify_payment(self, reference):
        """Retourne les données vérifiées du provider."""

    @abstractmethod
    def handle_callback(self, request):
        """Interprète le retour provider sans le considérer comme une preuve."""
