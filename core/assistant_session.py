"""Bounded, private conversation state and verified browser page hints."""
import hashlib
import json
import re
from time import time
from urllib.parse import urlsplit
from uuid import uuid4
from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.urls import resolve, Resolver404
from django.utils.crypto import salted_hmac
from django.utils.translation import get_language
from .assistant import INTENTS

MEMORY_SECONDS = 900
MAX_TURNS = 12


def localized(fr, en):
    return en if str(get_language()).startswith("en") else fr


def clean_state(value):
    if not isinstance(value, dict) or value.get("intent") not in INTENTS:
        return {}
    result = {"intent": value["intent"]}
    for key, limit in (("step", 40), ("search_query", 100)):
        if isinstance(value.get(key), str):
            result[key] = value[key][:limit]
    def valid_id(item):
        return type(item) is int and 0 < item <= 9223372036854775807
    if isinstance(value.get("product_ids"), list):
        result["product_ids"] = [item for item in value["product_ids"][:5] if valid_id(item)]
    for key in ("category_id", "selected_product_id"):
        if valid_id(value.get(key)):
            result[key] = value[key]
    return result


def page_context(value, user):
    """The hint supplies navigation context, never permission or trusted IDs."""
    if not isinstance(value, str) or len(value) > 256 or not value.startswith("/") or "\\" in value:
        return None, "unknown"
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None, "unknown"
    if parsed.scheme or parsed.netloc or parsed.fragment:
        return None, "unknown"
    try:
        match = resolve(parsed.path)
    except Resolver404:
        return None, "unknown"
    routes = {"home":"home", "product_list":"catalogue", "product_detail":"product", "cart_detail":"cart", "create_order":"checkout", "my_orders":"orders", "order_detail":"order", "category_detail":"catalogue"}
    kind = routes.get(match.url_name)
    if not kind or (kind in {"cart", "checkout", "orders", "order"} and not user.is_authenticated):
        return None, "unknown"
    if kind == "product":
        from products.models import Product
        if not Product.objects.filter(slug=match.kwargs.get("slug"), actif=True, categorie__active=True).exists():
            return None, "unknown"
    if match.url_name == "category_detail":
        from categories.models import Category
        if not Category.objects.filter(slug=match.kwargs.get("slug"), active=True).exists():
            return None, "unknown"
    if kind == "order":
        from orders.models import Order
        if not Order.objects.filter(pk=match.kwargs.get("id"), utilisateur=user).exists():
            return None, "unknown"
    return parsed.path, kind


def conversation_response(request, payload, answer):
    message = payload["message"]
    request_id = payload.get("request_id")
    if request_id is not None and (not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id)):
        return JsonResponse({"error":localized("Identifiant de requête invalide.", "Invalid request identifier.")}, status=400)
    # Resolve authentication before replacing the session store below.
    authenticated = request.user.is_authenticated
    if not request.session.session_key:
        request.session.create()
    session_key = request.session.session_key
    identity = salted_hmac("assistant.conversation", session_key, algorithm="sha256").hexdigest()
    lock_key = "assistant-lock:" + identity
    replay_key = "assistant-replay:" + identity
    token = uuid4().hex
    if not cache.add(lock_key, token, timeout=30):
        response = JsonResponse({"error":localized("Une réponse est déjà en préparation. Réessayez dans un instant.", "A reply is already being prepared. Please try again shortly.")}, status=409)
        response["Retry-After"] = "1"
        return response
    try:
        # Load again while holding the lock: a concurrent request may have loaded
        # the old state in AuthenticationMiddleware before it reached this view.
        request.session = request.session.__class__(session_key=session_key)
        now = time()
        meta = request.session.get("assistant_meta", {})
        fresh = isinstance(meta, dict) and type(meta.get("updated_at")) in (int, float) and 0 <= now-meta["updated_at"] < MEMORY_SECONDS and type(meta.get("turns")) is int and 0 <= meta["turns"] < MAX_TURNS
        state = clean_state(request.session.get("assistant_state")) if fresh else {}
        context, kind = page_context(payload.get("context"), request.user)
        language = get_language()
        fingerprint = hashlib.sha256(json.dumps([message, payload.get("context"), language], ensure_ascii=False).encode()).hexdigest()
        previous = cache.get(replay_key) if request_id else None
        replay = isinstance(previous, dict) and previous.get("id") == request_id
        if replay and previous.get("fingerprint") != fingerprint:
            return JsonResponse({"error":localized("Cet identifiant correspond à une autre question.", "That identifier belongs to another question.")}, status=409)
        prior_state = clean_state(previous.get("prior_state")) if replay else state
        result = answer(message, language, authenticated, context=context, state=prior_state, request=request)
        result["state"] = clean_state(result.get("state"))
        result["page_context"] = kind
        if not fresh and not replay:
            request.session.pop("assistant_failures", None)
        if not replay:
            if result["state"]:
                request.session["assistant_state"] = result["state"]
            else:
                request.session.pop("assistant_state", None)
        if result["intent"] == "AIDE_GENERALE":
            failures = min(3, int(request.session.get("assistant_failures", 0)) + (0 if replay else 1))
            if not replay:
                request.session["assistant_failures"] = failures
            if failures >= 3:
                result["answer"] = localized("Je n'arrive pas à résoudre votre demande automatiquement. Contactez la boutique avec les coordonnées affichées.", "I cannot resolve your request automatically. Please contact the shop using the displayed contact details.")
                from dashboard.models import BoutiqueSettings
                boutique = BoutiqueSettings.objects.first()
                if boutique and boutique.email:
                    result["actions"] = [{"label":localized("Contacter le support", "Contact support"), "url":"mailto:"+boutique.email}]
                elif boutique and boutique.whatsapp:
                    result["actions"] = [{"label":localized("Contacter le support", "Contact support"), "url":"https://api.whatsapp.com/send?phone="+boutique.whatsapp}]
        elif not replay:
            request.session.pop("assistant_failures", None)
        if replay:
            # Recompute current catalog data and preserve support escalation,
            # without advancing conversation state or failure counters.
            return JsonResponse(result)
        request.session["assistant_meta"] = {"updated_at":now, "turns":meta["turns"]+1 if fresh else 1}
        # Save before releasing the lock; middleware must not overwrite a newer
        # reply with this already-persisted state after another request starts.
        request.session.save()
        # A newly created/rotated anonymous session still needs its cookie.
        request.session.modified = request.COOKIES.get(settings.SESSION_COOKIE_NAME) != request.session.session_key
        if request_id:
            cache.set(replay_key, {"id":request_id, "fingerprint":fingerprint, "prior_state":state}, timeout=MEMORY_SECONDS)
        return JsonResponse(result)
    finally:
        if cache.get(lock_key) == token:
            cache.delete(lock_key)
