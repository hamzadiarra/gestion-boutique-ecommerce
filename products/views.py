from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Avg, BooleanField, Case, Q, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from categories.models import Category
from reviews.forms import ReviewForm
from .models import Product, Wishlist


def product_list(request):
    produits = Product.objects.filter(actif=True).select_related("categorie").annotate(
        is_new=Case(
            When(date_creation__gte=timezone.now() - timedelta(days=30), then=Value(True)),
            default=Value(False), output_field=BooleanField(),
        )
    )
    recherche = request.GET.get("q", "").strip()
    if recherche:
        produits = produits.filter(
            Q(nom__icontains=recherche)
            | Q(marque__icontains=recherche)
            | Q(description__icontains=recherche)
        )

    categorie_id = request.GET.get("categorie", "")
    if categorie_id:
        produits = produits.filter(categorie_id=categorie_id)

    min_price = request.GET.get("prix_min", "").strip()
    max_price = request.GET.get("prix_max", "").strip()
    if min_price:
        try:
            produits = produits.filter(prix__gte=min_price)
        except (TypeError, ValueError):
            min_price = ""
    if max_price:
        try:
            produits = produits.filter(prix__lte=max_price)
        except (TypeError, ValueError):
            max_price = ""

    disponibilite = request.GET.get("disponibilite", "")
    if disponibilite == "en_stock":
        produits = produits.filter(stock__gt=0)
    elif disponibilite == "rupture":
        produits = produits.filter(stock=0)

    tri = request.GET.get("tri", "pertinence")
    if tri == "prix_croissant":
        produits = produits.order_by("prix", "nom")
    elif tri == "prix_decroissant":
        produits = produits.order_by("-prix", "nom")
    elif tri == "nouveautes":
        produits = produits.order_by("-date_creation", "nom")
    elif tri == "popularite":
        produits = produits.order_by("-quantite_vendue", "-date_creation")
    else:
        produits = produits.order_by("-vedette", "-date_creation", "nom")

    query_params = request.GET.copy()
    query_params.pop("page", None)
    page_obj = Paginator(produits, 12).get_page(request.GET.get("page"))

    return render(request, "products/product_list.html", {
        "page_obj": page_obj,
        "categories": Category.objects.filter(active=True),
        "recherche": recherche,
        "categorie_selectionnee": categorie_id,
        "tri": tri,
        "min_price": min_price,
        "max_price": max_price,
        "disponibilite": disponibilite,
        "query_params": query_params.urlencode(),
    })


def product_detail(request, slug):
    produit = get_object_or_404(Product, slug=slug, actif=True)
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
        messages.info(request, f"« {produit.nom} » a été retiré de votre liste de souhaits.")
    else:
        wishlist.produits.add(produit)
        messages.success(request, f"« {produit.nom} » a été ajouté à votre liste de souhaits.")
    referer = request.META.get("HTTP_REFERER")
    if referer:
        return redirect(referer)
    return redirect("product_detail", slug=produit.slug)


@login_required
def wishlist_view(request):
    wishlist, _ = Wishlist.objects.get_or_create(utilisateur=request.user)
    return render(request, "products/wishlist.html", {"produits": wishlist.produits.filter(actif=True).select_related("categorie")})
