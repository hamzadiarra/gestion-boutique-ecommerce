from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.db.models import Avg, BooleanField, Case, Q, Value, When, Min, Max, Count, F, DecimalField
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_GET
from .search import search_products

from categories.models import Category
from reviews.forms import ReviewForm
from .models import Product, Wishlist


def public_products():
    return Product.objects.filter(actif=True, categorie__active=True).select_related("categorie").annotate(
        effective_price=Case(
            When(Q(prix_promotion__isnull=False) & ~Q(prix_promotion=0), then=F("prix_promotion")),
            default=F("prix"), output_field=DecimalField(max_digits=10, decimal_places=2),
        ),
        is_new=Case(When(date_creation__gte=timezone.now() - timedelta(days=30), then=Value(True)),
                    default=Value(False), output_field=BooleanField()),
    )


def price_value(raw):
    try:
        value = Decimal(raw)
        return raw if value.is_finite() and 0 <= value <= Decimal("99999999.99") else ""
    except (InvalidOperation, ValueError, TypeError):
        return ""


def product_list(request, category=None):
    recherche = request.GET.get("q", "").strip()[:100]
    produits = public_products()
    categorie_id = str(category.pk) if category else request.GET.get("categorie", "")
    try:
        if categorie_id and not 0 < int(categorie_id) <= 9223372036854775807:
            raise ValueError
    except (TypeError, ValueError):
        categorie_id = ""
    if categorie_id:
        produits = produits.filter(categorie_id=categorie_id)
    produits = search_products(produits, recherche)
    price_bounds = produits.aggregate(minimum=Min("effective_price"), maximum=Max("effective_price"))
    availability = produits.aggregate(in_stock=Count("pk", filter=Q(stock__gt=0)),
                                      out_of_stock=Count("pk", filter=Q(stock=0)))
    min_price = price_value(request.GET.get("prix_min", "").strip())
    max_price = price_value(request.GET.get("prix_max", "").strip())
    if min_price:
        produits = produits.filter(effective_price__gte=min_price)
    if max_price:
        produits = produits.filter(effective_price__lte=max_price)
    disponibilite = request.GET.get("disponibilite", "")
    if disponibilite == "en_stock":
        produits = produits.filter(stock__gt=0)
    elif disponibilite == "rupture":
        produits = produits.filter(stock=0)
    tri = request.GET.get("tri", "pertinence")
    sorting = {"prix_croissant": ("effective_price", "nom"),
               "prix_decroissant": ("-effective_price", "nom"),
               "nouveautes": ("-date_creation", "nom"),
               "popularite": ("-quantite_vendue", "-date_creation")}
    produits = produits.order_by(*sorting.get(tri, ("-vedette", "-date_creation", "nom")), "pk")
    query_params = request.GET.copy()
    query_params.pop("page", None)
    if category:
        query_params["categorie"] = str(category.pk)
    page_obj = Paginator(produits, 12).get_page(request.GET.get("page"))
    return render(request, "categories/category_detail.html" if category else "products/product_list.html", {
        "page_obj": page_obj, "produits": page_obj, "categorie": category,
        "product_count": page_obj.paginator.count,
        "categories": Category.objects.filter(active=True), "recherche": recherche,
        "categorie_selectionnee": categorie_id, "tri": tri, "min_price": min_price,
        "max_price": max_price, "price_bounds": price_bounds, "availability": availability,
        "disponibilite": disponibilite, "query_params": query_params.urlencode(),
    })


@require_GET
def autocomplete(request):
    query = request.GET.get("q", "").strip()[:100]
    products = public_products()
    category = request.GET.get("categorie", "")
    if category:
        if not category.isdecimal() or len(category) > 18:
            products = products.none()
        else:
            products = products.filter(categorie_id=category)
    results = []
    if len(query) >= 2:
        for product in search_products(products, query).order_by("-stock", "nom", "pk")[:8]:
            results.append({"id": product.pk, "name": product.localized_name,
                            "price": format(product.effective_price, ".2f"), "currency": "FCFA",
                            "available": product.stock > 0,
                            "image": product.image.url if product.image_is_product else "",
                            "url": reverse("product_detail", args=[product.slug])})
    response = JsonResponse({"results": results})
    response["Cache-Control"] = "no-store"
    return response


def product_detail(request, slug):
    produit = get_object_or_404(Product, slug=slug, actif=True, categorie__active=True)
    reviews = produit.reviews.all()
    avg_rating = reviews.aggregate(Avg("note"))["note__avg"] or 0
    avg_rating_int = int(round(avg_rating))
    user_review = None
    in_wishlist = False
    if request.user.is_authenticated:
        user_review = reviews.filter(utilisateur=request.user).first()
        in_wishlist = Wishlist.objects.filter(utilisateur=request.user, produits=produit).exists()

    review_stats = [{"note": note, "count": reviews.filter(note=note).count()} for note in range(5, 0, -1)]
    related_products = Product.objects.filter(
        actif=True, categorie=produit.categorie
    ).exclude(id=produit.id).order_by("-vedette", "-quantite_vendue", "-date_creation")[:4]
    context = {
        "produit": produit,
        "reviews": reviews,
        "avg_rating": round(avg_rating, 1),
        "stars_filled": range(avg_rating_int),
        "stars_empty": range(5 - avg_rating_int),
        "review_form": ReviewForm(instance=user_review) if user_review else ReviewForm(),
        "already_reviewed": user_review is not None,
        "in_wishlist": in_wishlist,
        "review_stats": review_stats,
        "related_products": related_products,
        "is_new": produit.date_creation >= timezone.now() - timedelta(days=30),
        "promotion_saving": (produit.prix - produit.prix_promotion) if produit.prix_promotion else None,
    }
    return render(request, "products/product_detail.html", context)


@login_required
def toggle_wishlist(request, product_id):
    produit = get_object_or_404(Product, id=product_id, actif=True)
    wishlist, _ = Wishlist.objects.get_or_create(utilisateur=request.user)
    if wishlist.produits.filter(id=product_id).exists():
        wishlist.produits.remove(produit)
        messages.info(request, gettext("« {name} » a été retiré de votre liste de souhaits.").format(name=produit.nom))
    else:
        wishlist.produits.add(produit)
        messages.success(request, gettext("« {name} » a été ajouté à votre liste de souhaits.").format(name=produit.nom))
    referer = request.META.get("HTTP_REFERER")
    if referer:
        return redirect(referer)
    return redirect("product_detail", slug=produit.slug)


@login_required
def wishlist_view(request):
    wishlist, _ = Wishlist.objects.get_or_create(utilisateur=request.user)
    return render(request, "products/wishlist.html", {"produits": wishlist.produits.filter(actif=True).select_related("categorie")})
