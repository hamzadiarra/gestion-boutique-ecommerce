from django.shortcuts import render
from django.db.models import BooleanField, Case, Count, Value, When
from django.utils import timezone
from datetime import timedelta
from products.models import Product
from categories.models import Category
from notifications.models import Notification
from orders.models import Order
from django.http import JsonResponse
from django.views.decorators.http import require_POST
import json
from .assistant import MAX_MESSAGE_LENGTH, answer_question
from django.utils.timezone import localtime


def _safe_image_url(request, field):
    if not field:
        return None
    try:
        return request.build_absolute_uri(field.url)
    except Exception:
        return None


@require_POST
def assistant_ask(request):
    """Return a safe, local guide answer; it never performs a business action."""
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"error": "Message invalide."}, status=400)
    message = payload.get("message", "") if isinstance(payload, dict) else ""
    if not isinstance(message, str) or not message.strip() or len(message) > MAX_MESSAGE_LENGTH:
        return JsonResponse({"error": "La question doit contenir entre 1 et 500 caractères."}, status=400)
    from django.utils.translation import get_language
    state = request.session.get("assistant_state", {})
    result = answer_question(message, get_language(), request.user.is_authenticated, context=request.path, state=state, request=request)
    if result.get("state"):
        request.session["assistant_state"] = result["state"]
    else:
        request.session.pop("assistant_state", None)
    if result["intent"] == "AIDE_GENERALE":
        failures = request.session.get("assistant_failures", 0) + 1
        request.session["assistant_failures"] = failures
        if failures >= 3:
            result["answer"] = "Je n'arrive pas à résoudre votre demande automatiquement. Contactez la boutique avec les coordonnées affichées." if get_language() != "en" else "I cannot resolve your request automatically. Please contact the shop using the displayed contact details."
            from dashboard.models import BoutiqueSettings
            boutique = BoutiqueSettings.objects.first()
            if boutique and boutique.email:
                result["actions"] = [{"label": "Contacter le support" if get_language() != "en" else "Contact support", "url": "mailto:" + boutique.email}]
            elif boutique and boutique.whatsapp:
                result["actions"] = [{"label": "Contacter le support" if get_language() != "en" else "Contact support", "url": "https://api.whatsapp.com/send?phone=" + boutique.whatsapp}]
    else:
        request.session.pop("assistant_failures", None)
    request.session.modified = True
    return JsonResponse(result)


def _serialize_category(request, categorie):
    return {
        "id": categorie.id,
        "nom": categorie.nom,
        "slug": categorie.slug,
        "description": categorie.description,
        "active": categorie.active,
        "image": _safe_image_url(request, categorie.image),
        "product_count": getattr(categorie, "product_count", 0),
    }


def _serialize_product(request, produit):
    return {
        "id": produit.id,
        "nom": produit.nom,
        "slug": produit.slug,
        "description": produit.description,
        "prix": float(produit.prix),
        "prix_promotion": float(produit.prix_promotion) if produit.prix_promotion is not None else None,
        "stock": produit.stock,
        "marque": produit.marque,
        "actif": produit.actif,
        "vedette": produit.vedette,
        "categorie_id": produit.categorie_id,
        "categorie_nom": produit.categorie.nom if produit.categorie_id else None,
        "categorie_slug": produit.categorie.slug if produit.categorie_id else None,
        "image": _safe_image_url(request, produit.image),
        "date_creation": timezone.localtime(produit.date_creation).isoformat() if timezone.is_aware(produit.date_creation) else produit.date_creation.isoformat(),
        "date_modification": timezone.localtime(produit.date_modification).isoformat() if timezone.is_aware(produit.date_modification) else produit.date_modification.isoformat(),
    }


def _serialize_order(order):
    return {
        "id": order.id,
        "statut": order.statut,
        "date_creation": localtime(order.date_creation).isoformat() if hasattr(order, "date_creation") else None,
        "adresse_livraison": order.adresse_livraison,
        "ville_livraison": order.ville_livraison,
        "code_postal_livraison": order.code_postal_livraison,
        "mode_livraison": order.mode_livraison,
        "frais_livraison": float(order.frais_livraison),
        "total": float(order.total()),
        "articles": [
            {
                "produit_id": item.produit_id,
                "produit_nom": item.produit.nom,
                "quantite": item.quantite,
                "prix": float(item.prix),
                "sous_total": float(item.sous_total()),
            }
            for item in order.items.all()
        ],
    }


def _serialize_notification(notification):
    return {
        "id": notification.id,
        "titre": notification.titre,
        "type_notification": notification.type_notification,
        "message": notification.message,
        "lien": notification.lien,
        "lu": notification.lu,
        "date_creation": notification.date_creation.isoformat(),
    }


def home(request):
    produits_actifs = Product.objects.filter(actif=True).select_related("categorie").annotate(
        is_new=Case(
            When(date_creation__gte=timezone.now() - timedelta(days=30), then=Value(True)),
            default=Value(False), output_field=BooleanField(),
        )
    )
    produits_vedette = produits_actifs.filter(vedette=True)[:6]
    categories = Category.objects.filter(active=True).annotate(product_count=Count("products"))[:6]
    nouveautes = produits_actifs.order_by("-date_creation")[:4]
    meilleures_ventes = produits_actifs.order_by("-quantite_vendue", "-date_creation")[:4]
    promotions = produits_actifs.filter(prix_promotion__isnull=False).order_by("-date_creation")[:4]

    context = {
        "produits_vedette": produits_vedette,
        "categories": categories,
        "nouveautes": nouveautes,
        "meilleures_ventes": meilleures_ventes,
        "promotions": promotions,
    }
    return render(request, 'home.html', context)


def offline_sync_payload(request):
    user = request.user if request.user.is_authenticated else None
    categories = list(
        Category.objects.filter(active=True)
        .annotate(product_count=Count("products"))
        .order_by("nom")[:200]
    )
    products = list(
        Product.objects.filter(actif=True)
        .select_related("categorie")
        .order_by("-date_modification")[:500]
    )

    data = {
        "version": "1",
        "scope": "public",
        "updated_at": localtime(timezone.now()).isoformat(),
        "categories": [_serialize_category(request, c) for c in categories],
        "products": [_serialize_product(request, p) for p in products],
    }

    if user and user.is_authenticated:
        profile = getattr(user, "profile", None)
        role = getattr(profile, "role", "client") if profile else "client"

        orders = list(
            Order.objects.filter(utilisateur=user)
            .select_related("payment")
            .prefetch_related("items__produit")
            .order_by("-date_creation")[:80]
        )

        notifications = list(
            Notification.objects.filter(utilisateur=user)
            .order_by("-date_creation")[:120]
        )

        seller_orders = (
            Order.objects.filter(vendeur_confirmateur=user)
            .order_by("-date_creation")[:60]
            if role in {"vendeur", "admin"}
            else []
        )

        data.update({
            "scope": "authenticated",
            "user": {
                "id": user.id,
                "username": user.username,
                "role": role,
            },
            "orders": [_serialize_order(order) for order in orders],
            "notifications": [_serialize_notification(notification) for notification in notifications],
            "seller_orders": [_serialize_order(order) for order in seller_orders],
        })

    return JsonResponse({"ok": True, "payload": data})
