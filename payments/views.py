from django.utils.translation import gettext
import uuid
import json
import os
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.contrib import messages
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from orders.models import Order
from .models import Payment
from .providers import get_payment_provider
from .providers.moov_money import (
    get_moov_money_instructions,
    ensure_moov_money_webhook_configured,
    is_moov_money_configured,
    verify_moov_money_webhook_signature,
)


WAVE_BASE_URL = "https://api.wave.com"


# ============================================================
# OUTILS WAVE
# ============================================================

def _wave_api_key():
    """
    Récupère la clé Wave uniquement depuis l'environnement.
    Ne jamais écrire la vraie clé directement dans le code.
    """
    return os.environ.get("WAVE_API_KEY", "").strip()


def _wave_request(path, method="GET", payload=None):
    """
    Effectue une requête serveur -> Wave.
    """

    api_key = _wave_api_key()

    if not api_key:
        raise RuntimeError(
            "La variable d'environnement WAVE_API_KEY n'est pas configurée."
        )

    url = f"{WAVE_BASE_URL}{path}"

    body = None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(
        url=url,
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")

            if not raw:
                return {}

            return json.loads(raw)

    except HTTPError as exc:
        raise RuntimeError(
            f"Wave a refusé la requête ({exc.code}). Veuillez réessayer plus tard."
        ) from exc

    except URLError as exc:
        raise RuntimeError(
            "Impossible de contacter Wave pour le moment."
        ) from exc


def _wave_create_checkout(request, commande, paiement):
    """
    Crée une Checkout Session Wave.
    """

    success_url = request.build_absolute_uri(
        reverse(
            "wave_payment_success",
            kwargs={"order_id": commande.id},
        )
    )

    error_url = request.build_absolute_uri(
        reverse(
            "wave_payment_error",
            kwargs={"order_id": commande.id},
        )
    )

    payload = {
        "amount": str(
            int(
                Decimal(paiement.montant)
            )
        ),
        "currency": "XOF",
        "client_reference": f"ORDER-{commande.id}",
        "success_url": success_url,
        "error_url": error_url,
    }

    return _wave_request(
        "/v1/checkout/sessions",
        method="POST",
        payload=payload,
    )


def _wave_get_checkout(session_id):
    """
    Demande directement à Wave l'état réel d'une session.
    """

    return _wave_request(
        f"/v1/checkout/sessions/{session_id}"
    )


def _confirm_wave_payment(commande, paiement, wave_data):
    """Confirme une session vérifiée en relisant les états sous verrou."""
    with transaction.atomic():
        commande = Order.objects.select_for_update().get(pk=commande.pk)
        paiement = Payment.objects.select_for_update().get(
            pk=paiement.pk
        )
        if paiement.commande_id != commande.pk or paiement.methode != "wave":
            raise ValueError("Le paiement Wave ne correspond pas à cette commande.")
        if paiement.statut == "paye":
            return paiement
        if commande.statut != "en_attente" or paiement.statut != "en_attente":
            raise ValueError("Cette commande ne peut plus être payée.")
        if wave_data.get("payment_status") != "succeeded" or wave_data.get("checkout_status") != "complete":
            return paiement
        if wave_data.get("client_reference") != f"ORDER-{commande.pk}":
            raise ValueError("La référence Wave ne correspond pas à cette commande.")
        try:
            wave_amount = Decimal(str(wave_data.get("amount", "")))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("Le montant Wave est invalide.") from exc
        if not wave_amount.is_finite() or wave_amount != paiement.montant or paiement.montant != commande.total():
            raise ValueError("Le montant Wave ne correspond pas au montant de la commande.")
        if wave_data.get("currency", "XOF") != "XOF":
            raise ValueError("La devise Wave ne correspond pas à cette commande.")
        paiement.statut = "paye"
        paiement.date_paiement = timezone.now()

        # Si Wave fournit une transaction finale,
        # on conserve cette référence.
        transaction_id = wave_data.get("transaction_id")

        if transaction_id:
            paiement.reference = transaction_id

        paiement.save(
            update_fields=[
                "statut",
                "date_paiement",
                "reference",
            ]
        )

        commande.statut = "confirmee"

        # Ici il n'y a PAS de vendeur confirmateur :
        # c'est Wave qui a confirmé le paiement.
        commande.date_confirmation = timezone.now()

        commande.save(
            update_fields=[
                "statut",
                "date_confirmation",
            ]
        )

    return paiement


# ============================================================
# PAIEMENT EN LIGNE — PROVIDER EXTERNE
# ============================================================

def _online_reference():
    return f"ONL-{uuid.uuid4().hex.upper()}"


def _confirm_online_payment(payment, verified):
    """Valide une réponse provider vérifiée, sous verrou et de façon idempotente."""
    with transaction.atomic():
        payment = Payment.objects.select_for_update().select_related("commande").get(pk=payment.pk)
        order = Order.objects.select_for_update().get(pk=payment.commande_id)
        if payment.statut == "paye":
            return payment
        if payment.methode != "online" or order.statut != "en_attente":
            raise ValueError("Ce paiement ne peut plus être confirmé.")
        if str(verified.get("tx_ref")) != payment.provider_reference:
            raise ValueError("La référence du paiement ne correspond pas à la commande.")
        payment.provider_payload = verified.get("raw") or verified
        if verified.get("status") != "successful":
            payment.provider_status = str(verified.get("provider_status") or verified.get("status") or "")
            if verified.get("status") == "failed":
                payment.statut = "echoue"
                payment.save(update_fields=["statut", "provider_status", "provider_payload"])
            else:
                payment.save(update_fields=["provider_status", "provider_payload"])
            return payment
        try:
            amount = Decimal(str(verified.get("amount")))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("Le montant du provider est invalide.") from exc
        if amount != order.total() or amount != payment.montant or verified.get("currency") != "XOF":
            raise ValueError("Le montant ou la devise du paiement ne correspond pas à la commande.")
        payment.statut = "paye"
        payment.date_paiement = timezone.now()
        payment.date_confirmation = payment.date_paiement
        payment.reference = str(verified.get("id") or payment.provider_reference)
        payment.provider_status = "successful"
        payment.provider_payload = verified.get("raw") or verified
        payment.save(update_fields=["statut", "date_paiement", "date_confirmation", "reference", "provider_status", "provider_payload"])
        order.statut = "confirmee"
        order.date_confirmation = payment.date_confirmation
        order.save(update_fields=["statut", "date_confirmation"])
    return payment


@login_required
@require_POST
def start_online_payment(request, order_id):
    order = get_object_or_404(Order, id=order_id, utilisateur=request.user)
    if order.statut != "en_attente":
        return JsonResponse({"error": "Cette commande ne peut plus être payée."}, status=400)
    try:
        provider = get_payment_provider()
    except RuntimeError as exc:
        return render(request, "payments/payment_result.html", {"commande": order, "status": "indisponible", "message": gettext("Configuration sandbox requise.")})
    with transaction.atomic():
        payment = Payment.objects.select_for_update().filter(commande=order).first()
        if payment and payment.statut == "paye":
            return redirect("payment_form", order_id=order.id)
        if payment is None:
            payment = Payment.objects.create(commande=order, montant=order.total(), methode="online", statut="en_attente", provider=provider.name, provider_reference=_online_reference())
        else:
            payment.montant = order.total()
            payment.methode = "online"
            payment.provider = provider.name
            payment.provider_reference = payment.provider_reference or _online_reference()
            payment.save(update_fields=["montant", "methode", "provider", "provider_reference"])
    try:
        result = provider.create_payment(request, order, payment)
    except RuntimeError as exc:
        return render(request, "payments/payment_result.html", {"commande": order, "paiement": payment, "status": "indisponible", "message": str(exc)})
    payment.provider_payload = result.get("payload")
    payment.save(update_fields=["provider_payload"])
    return redirect(result["checkout_url"])


@csrf_exempt
@require_POST
def cinetpay_webhook(request):
    """Receive CinetPay notification, then verify the transaction server-side."""
    try:
        provider = get_payment_provider()
    except RuntimeError as exc:
        return JsonResponse({"received": False, "error": str(exc)}, status=503)
    if provider.name != "cinetpay":
        return JsonResponse({"received": False, "error": "Le provider CinetPay n'est pas actif."}, status=400)
    data = request.POST
    if data.get("cpm_site_id") != provider.site_id:
        return JsonResponse({"received": False, "error": "Site CinetPay invalide."}, status=400)
    if not provider.verify_webhook_signature(data, request.META.get("HTTP_X_TOKEN", "")):
        return JsonResponse({"received": False, "error": "Signature CinetPay invalide."}, status=400)
    reference = data.get("cpm_trans_id", "")
    if not reference:
        return JsonResponse({"received": False, "error": "Référence CinetPay absente."}, status=400)
    try:
        payment = Payment.objects.select_related("commande").get(
            provider="cinetpay", provider_reference=reference, methode="online"
        )
        if payment.statut == "paye":
            return JsonResponse({"received": True, "already_processed": True})
        verified = provider.verify_payment(reference)
        _confirm_online_payment(payment, verified)
    except (ValueError, RuntimeError, Payment.DoesNotExist) as exc:
        return JsonResponse({"received": False, "error": str(exc)}, status=400)
    return JsonResponse({"received": True, "processed": True})


@login_required
def online_payment_return(request):
    try:
        provider = get_payment_provider()
    except RuntimeError as exc:
        return render(request, "payments/payment_result.html", {"status": "indisponible", "message": str(exc)})
    callback = provider.handle_callback(request)
    reference = callback.get("reference")
    payment = Payment.objects.filter(provider_reference=reference, methode="online", commande__utilisateur=request.user).select_related("commande").first()
    if not payment:
        return render(request, "payments/payment_result.html", {"status": "erreur", "message": gettext("Paiement introuvable ou référence invalide.")})
    if payment.statut == "paye":
        return render(request, "payments/payment_success.html", {"commande": payment.commande, "paiement": payment})
    try:
        payment = _confirm_online_payment(payment, provider.verify_payment(callback.get("transaction_id") or reference))
    except (RuntimeError, ValueError) as exc:
        return render(request, "payments/payment_result.html", {"commande": payment.commande, "paiement": payment, "status": "erreur", "message": str(exc)})
    if payment.statut == "paye":
        return render(request, "payments/payment_success.html", {"commande": payment.commande, "paiement": payment})
    return render(request, "payments/payment_result.html", {"commande": payment.commande, "paiement": payment, "status": "en_attente", "message": gettext("Vérification du paiement en cours.")})


@login_required
def online_payment_cancel(request):
    order = get_object_or_404(Order, id=request.GET.get("order_id"), utilisateur=request.user)
    return render(request, "payments/payment_result.html", {"commande": order, "status": "annule", "message": gettext("Paiement annulé. Votre commande est toujours disponible.")})


@csrf_exempt
@require_POST
def online_payment_webhook(request):
    try:
        provider = get_payment_provider()
    except RuntimeError as exc:
        return JsonResponse({"received": False, "error": str(exc)}, status=503)
    signature_header = "flutterwave-signature" if request.META.get("HTTP_FLUTTERWAVE_SIGNATURE") else "verif-hash"
    signature = request.META.get("HTTP_FLUTTERWAVE_SIGNATURE", "") or request.META.get("HTTP_VERIF_HASH", "")
    if not hasattr(provider, "verify_webhook_signature") or not provider.verify_webhook_signature(request.body, signature, signature_header):
        return JsonResponse({"received": False, "error": "Signature webhook invalide."}, status=400)
    try:
        payload = json.loads(request.body.decode())
        data = payload.get("data") or payload
        reference = data.get("tx_ref") or data.get("meta", {}).get("tx_ref")
        payment = Payment.objects.select_related("commande").get(provider_reference=reference, methode="online")
        if payment.statut == "paye":
            return JsonResponse({"received": True, "already_processed": True})
        verified = provider.verify_payment(data.get("id"))
        _confirm_online_payment(payment, verified)
    except (ValueError, UnicodeDecodeError, Payment.DoesNotExist, RuntimeError, KeyError, TypeError) as exc:
        return JsonResponse({"received": False, "error": str(exc)}, status=400)
    return JsonResponse({"received": True, "processed": True})


# ============================================================
# PAGE DE PAIEMENT
# ============================================================

@login_required
def payment_form(request, order_id):

    commande = get_object_or_404(
        Order,
        id=order_id,
        utilisateur=request.user,
    )

    paiement = getattr(
        commande,
        "payment",
        None,
    )

    if paiement and paiement.statut == "paye":
        return render(
            request,
            "payments/payment_success.html",
            {
                "paiement": paiement,
                "already_paid": True,
            },
        )

    if commande.statut == "annulee":
        return render(
            request,
            "payments/payment_result.html",
            {
                "commande": commande,
                "status": "annule",
                "message": (
                    "Cette commande a été annulée "
                    "et ne peut plus être payée."
                ),
            },
        )

    if request.method == "POST":

        methode = request.POST.get(
            "methode",
            ""
        )

        if methode not in dict(Payment.METHODES):

            return render(
                request,
                "payments/payment_form.html",
                {
                    "commande": commande,
                    "paiement": paiement,
                    "errors": [
                        "Choisissez un moyen de paiement valide."
                    ],
                },
            )

        # ====================================================
        # Créer ou remettre à jour le Payment
        # ====================================================

        with transaction.atomic():
            commande = Order.objects.select_for_update().get(pk=commande.pk)
            paiement = Payment.objects.select_for_update().filter(commande=commande).first()
            if paiement and paiement.statut == "paye":
                return render(request, "payments/payment_success.html", {
                    "commande": commande, "paiement": paiement, "already_paid": True,
                })
            if commande.statut == "annulee":
                return redirect("order_detail", id=commande.pk)
            if paiement is None:
                paiement = Payment.objects.create(
                    commande=commande, montant=commande.total(),
                    methode=methode, statut="en_attente",
                )
            else:
                paiement.methode = methode
                paiement.montant = commande.total()
                paiement.statut = "en_attente"
                paiement.date_paiement = None
                paiement.save(update_fields=["methode", "montant", "statut", "date_paiement"])

        # ====================================================
        # WAVE — API RÉELLE
        # ====================================================

        if methode == "online":
            provider_name = settings.PAYMENT_PROVIDER
            configured = (
                bool(settings.CINETPAY_API_KEY and settings.CINETPAY_SITE_ID and settings.CINETPAY_SECRET_KEY)
                if provider_name == "cinetpay"
                else bool(settings.PAYMENT_PROVIDER and settings.PAYMENT_SECRET_KEY)
            )
            unavailable_message = (
                "Le paiement en ligne CinetPay n'est pas encore configuré."
                if provider_name == "cinetpay"
                else "Le paiement en ligne n'est pas encore configuré."
            )
            return render(request, "payments/payment_result.html", {
                "commande": commande,
                "paiement": paiement,
                "status": "en_attente",
                "online_ready": configured,
                "message": gettext("Le paiement en ligne est prêt. Cliquez sur Payer maintenant pour ouvrir le checkout test.") if configured else gettext(unavailable_message),
            })

        if methode == "wave":

            if not _wave_api_key():

                return render(
                    request,
                    "payments/payment_result.html",
                    {
                        "commande": commande,
                        "paiement": paiement,
                        "status": "indisponible",
                        "message": (
                            "Le paiement Wave n'est pas encore "
                            "activé sur cette boutique."
                        ),
                    },
                )

            try:

                wave_session = _wave_create_checkout(
                    request,
                    commande,
                    paiement,
                )

            except RuntimeError as exc:

                return render(
                    request,
                    "payments/payment_result.html",
                    {
                        "commande": commande,
                        "paiement": paiement,
                        "status": "erreur",
                        "message": str(exc),
                    },
                )

            session_id = wave_session.get("id")
            launch_url = wave_session.get(
                "wave_launch_url"
            )

            if not session_id or not launch_url:

                return render(
                    request,
                    "payments/payment_result.html",
                    {
                        "commande": commande,
                        "paiement": paiement,
                        "status": "erreur",
                        "message": (
                            "Wave n'a pas retourné "
                            "une session de paiement valide."
                        ),
                    },
                )

            # On réutilise reference pour mémoriser
            # temporairement l'identifiant de session Wave.
            paiement.reference = session_id

            paiement.save(
                update_fields=["reference"]
            )

            return redirect(launch_url)

        # ====================================================
        # AUTRES MOYENS — EN ATTENTE
        # ====================================================

        if methode == "moov_money" and is_moov_money_configured():
            instructions = get_moov_money_instructions()
        else:
            instructions = ""

        message = (
            "Votre paiement a été enregistré et reste en attente de confirmation."
            if not instructions
            else f"{instructions} La commande reste en attente de confirmation vendeur / administrateur."
        )

        return render(
            request,
            "payments/payment_result.html",
            {
                "paiement": paiement,
                "commande": commande,
                "status": "en_attente",
                "message": message,
            },
        )

    payment_context = {
        "commande": commande,
        "paiement": paiement,
    }
    provider_configured = (
        bool(settings.CINETPAY_API_KEY and settings.CINETPAY_SITE_ID and settings.CINETPAY_SECRET_KEY)
        if settings.PAYMENT_PROVIDER == "cinetpay"
        else bool(settings.PAYMENT_PROVIDER and settings.PAYMENT_SECRET_KEY)
    )
    if paiement and paiement.methode == "online" and not provider_configured:
        unavailable_message = (
            "Le paiement en ligne CinetPay n'est pas encore configuré."
            if settings.PAYMENT_PROVIDER == "cinetpay"
            else "Le paiement en ligne n'est pas encore configuré."
        )
        payment_context.update({
            "status": "indisponible",
            "message": gettext(unavailable_message),
            "errors": [gettext(unavailable_message)],
        })
    return render(request, "payments/payment_form.html", payment_context)


# ============================================================
# RETOUR WAVE — SUCCÈS
# ============================================================

@login_required
def wave_payment_success(request, order_id):
    """
    Le navigateur revient ici après Wave.

    IMPORTANT :
    on ne fait pas confiance au simple retour navigateur.
    On interroge Wave directement pour confirmer le paiement.
    """

    commande = get_object_or_404(
        Order,
        id=order_id,
        utilisateur=request.user,
    )

    paiement = getattr(
        commande,
        "payment",
        None,
    )

    if not paiement:

        return render(
            request,
            "payments/payment_result.html",
            {
                "commande": commande,
                "status": "erreur",
                "message": (
                    "Aucun paiement n'est associé "
                    "à cette commande."
                ),
            },
        )

    if paiement.statut == "paye":

        return render(
            request,
            "payments/payment_success.html",
            {
                "commande": commande,
                "paiement": paiement,
            },
        )

    session_id = paiement.reference

    if (
        not session_id
        or not session_id.startswith("cos-")
    ):

        return render(
            request,
            "payments/payment_result.html",
            {
                "commande": commande,
                "paiement": paiement,
                "status": "erreur",
                "message": (
                    "La référence de paiement Wave "
                    "est invalide."
                ),
            },
        )

    try:

        wave_data = _wave_get_checkout(
            session_id
        )

        paiement = _confirm_wave_payment(
            commande,
            paiement,
            wave_data,
        )

    except (
        RuntimeError,
        ValueError,
    ) as exc:

        return render(
            request,
            "payments/payment_result.html",
            {
                "commande": commande,
                "paiement": paiement,
                "status": "erreur",
                "message": str(exc),
            },
        )

    if paiement.statut == "paye":

        messages.success(
            request,
            gettext("Votre paiement Wave a été confirmé.")
        )

        return render(
            request,
            "payments/payment_success.html",
            {
                "commande": commande,
                "paiement": paiement,
            },
        )

    return render(
        request,
        "payments/payment_result.html",
        {
            "commande": commande,
            "paiement": paiement,
            "status": "en_attente",
            "message": (
                "Wave n'a pas encore confirmé "
                "ce paiement."
            ),
        },
    )


# ============================================================
# RETOUR WAVE — ÉCHEC / ANNULATION
# ============================================================

@login_required
def wave_payment_error(request, order_id):

    commande = get_object_or_404(
        Order,
        id=order_id,
        utilisateur=request.user,
    )

    paiement = getattr(
        commande,
        "payment",
        None,
    )

    # On ne marque PAS automatiquement le paiement échoué.
    # Le retour navigateur seul n'est pas suffisamment fiable.
    return render(
        request,
        "payments/payment_result.html",
        {
            "commande": commande,
            "paiement": paiement,
            "status": "annule",
            "message": (
                "Le paiement Wave n'a pas été finalisé. "
                "Vous pouvez réessayer."
            ),
        },
    )


# ============================================================
# WEBHOOK WAVE
# ============================================================

@csrf_exempt
@require_POST
def wave_webhook(request):
    """
    Webhook Wave.

    IMPORTANT :
    avant la production réelle, configure un secret/signature Wave
    et vérifie systématiquement la signature du webhook.

    Ici, même lorsqu'un événement arrive, nous vérifions encore
    l'état de la session directement auprès de Wave avant de payer
    la commande localement.
    """

    try:
        event = json.loads(
            request.body.decode("utf-8")
        )

    except (ValueError, UnicodeDecodeError):
        return HttpResponseBadRequest(
            "Payload invalide."
        )

    if event.get("type") != "checkout.session.completed":

        return JsonResponse(
            {
                "received": True,
                "ignored": True,
            }
        )

    data = event.get("data") or {}

    session_id = data.get("id")
    client_reference = data.get(
        "client_reference",
        ""
    )

    if not session_id:
        return HttpResponseBadRequest(
            "Session Wave absente."
        )

    if not client_reference.startswith(
        "ORDER-"
    ):
        return HttpResponseBadRequest(
            "Référence commande invalide."
        )

    try:
        order_id = int(
            client_reference.split(
                "-",
                1,
            )[1]
        )

    except (
        IndexError,
        ValueError,
    ):
        return HttpResponseBadRequest(
            "Commande invalide."
        )

    commande = get_object_or_404(
        Order,
        id=order_id,
    )

    paiement = getattr(
        commande,
        "payment",
        None,
    )

    if not paiement:
        return HttpResponseBadRequest(
            "Paiement introuvable."
        )

    if paiement.methode != "wave":
        return HttpResponseBadRequest(
            "Moyen de paiement incorrect."
        )

    # Webhook reçu plusieurs fois :
    # renvoyer simplement OK.
    if paiement.statut == "paye":

        return JsonResponse(
            {
                "received": True,
                "already_processed": True,
            }
        )

    try:

        # Vérification serveur -> serveur.
        wave_data = _wave_get_checkout(
            session_id
        )

        _confirm_wave_payment(
            commande,
            paiement,
            wave_data,
        )

    except (
        RuntimeError,
        ValueError,
    ) as exc:

        return JsonResponse(
            {
                "received": False,
                "error": str(exc),
            },
            status=400,
        )

    return JsonResponse(
        {
            "received": True,
            "processed": True,
        }
    )


# ============================================================
# MOOV MONEY — PRÉPARATION D'ARCHITECTURE
# ============================================================


@require_POST
@csrf_exempt
def moov_money_callback(request, order_id):
    """
    Point de retour client prévu pour l'intégration future
    de l'API officielle Moov Money Mali (SANI / QR marchand).
    """

    _ = order_id

    if not is_moov_money_configured():
        return HttpResponse(
            "L'intégration Moov Money n'est pas encore configurée.",
            status=503,
        )

    return HttpResponse(
        "Moov Money API officielle non activée pour cette version.",
        status=501,
    )


@csrf_exempt
@require_POST
def moov_money_webhook(request):
    """
    Webhook de confirmation Moov Money (prévu pour usage futur).
    En version actuelle, aucune confirmation opérateur réelle n'est consommée.
    """

    payload = request.body
    signature = request.META.get("HTTP_X_MOOV_MONEY_SIGNATURE", "")

    try:
        ensure_moov_money_webhook_configured()
    except Exception as exc:  # pragma: no cover
        return JsonResponse(
            {"received": False, "error": str(exc)},
            status=400,
        )

    try:
        payload_dict = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return HttpResponseBadRequest("Payload invalide.")

    if not verify_moov_money_webhook_signature(payload, signature):
        return JsonResponse(
            {
                "received": False,
                "error": "Signature webhook Moov Money invalide.",
            },
            status=400,
        )

    if not isinstance(payload_dict, dict):
        return HttpResponseBadRequest("Payload invalide.")

    order_id = payload_dict.get("order_id")

    if not order_id:
        return HttpResponseBadRequest("Référence commande invalide.")

    try:
        order_id = int(order_id)
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Référence commande invalide.")

    commande = get_object_or_404(Order, id=order_id)

    paiement = getattr(commande, "payment", None)

    if not paiement:
        return JsonResponse(
            {
                "received": False,
                "error": "Paiement introuvable.",
            },
            status=400,
        )

    if paiement.methode != "moov_money":
        return JsonResponse(
            {
                "received": False,
                "error": "Moyen de paiement Moov Money attendu.",
            },
            status=400,
        )

    if payload_dict.get("status") != "confirmed":
        return JsonResponse(
            {
                "received": True,
                "processed": False,
                "reason": "attente_confirmation_operateur",
            }
        )

    if paiement.statut == "paye":
        return JsonResponse(
            {
                "received": True,
                "already_processed": True,
            }
        )

    return JsonResponse(
        {
            "received": True,
            "status": "not_implemented",
        }
    )
