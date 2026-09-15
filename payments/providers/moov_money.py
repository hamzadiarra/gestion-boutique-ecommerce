import hashlib
import hmac
from dataclasses import dataclass

from django.conf import settings


def _normalize(value: str | None) -> str:
    return (value or "").strip()


def is_moov_money_configured() -> bool:
    """Vrai si le code marchand Moov Money est présent."""
    return bool(_normalize(settings.MOOV_MONEY_MERCHANT_CODE))


def is_moov_money_api_ready() -> bool:
    """Prêt à appeler une API officielle si elle est branchée ultérieurement."""
    return bool(
        _normalize(settings.MOOV_MONEY_API_BASE_URL)
        and _normalize(settings.MOOV_MONEY_CLIENT_ID)
        and _normalize(settings.MOOV_MONEY_CLIENT_SECRET)
        and _normalize(settings.MOOV_MONEY_MERCHANT_CODE)
    )


def is_moov_money_webhook_secret_configured() -> bool:
    return bool(_normalize(settings.MOOV_MONEY_WEBHOOK_SECRET))


def get_moov_money_merchant_code() -> str:
    return _normalize(settings.MOOV_MONEY_MERCHANT_CODE)


def get_moov_money_instructions() -> str:
    """Retourne le message d'instructions à afficher avant activation réelle."""
    if not is_moov_money_configured():
        return ""
    return f"Effectuez votre paiement Moov Money avec le code marchand {get_moov_money_merchant_code()}."


def verify_moov_money_webhook_signature(
    payload: bytes,
    signature: str,
) -> bool:
    """Valide la signature HMAC-SHA256 du webhook Moov Money."""
    if not is_moov_money_webhook_secret_configured():
        return False

    if not signature:
        return False

    secret = _normalize(settings.MOOV_MONEY_WEBHOOK_SECRET)
    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    normalized_signature = signature.strip()

    if normalized_signature.startswith("sha256="):
        normalized_signature = normalized_signature.split("=", 1)[1].strip()

    return hmac.compare_digest(expected, normalized_signature)


@dataclass(frozen=True)
class MoovMoneyConfigurationError(RuntimeError):
    """Erreur d'activation/paramétrage fournisseur Moov Money."""


def ensure_moov_money_available() -> None:
    """
    Aucune API officielle Mali n'est branchée pour le moment.
    Cette fonction garde la porte ouverte pour valider proprement le prérequis.
    """
    if not is_moov_money_api_ready():
        raise MoovMoneyConfigurationError(
            "La configuration Moov Money n'est pas complète pour l'appel API officiel."
        )


def ensure_moov_money_webhook_configured() -> None:
    if not is_moov_money_webhook_secret_configured():
        raise MoovMoneyConfigurationError(
            "La signature Moov Money (MOOV_MONEY_WEBHOOK_SECRET) n'est pas configurée."
        )
