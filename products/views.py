from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from .models import Product
from categories.models import Category


def product_list(request):

    produits = Product.objects.filter(actif=True)

    # Recherche
    recherche = request.GET.get("q")

    if recherche:
        produits = produits.filter(
            nom__icontains=recherche
        )

    # Filtre par catégorie
    categorie_id = request.GET.get("categorie")

    if categorie_id:
        produits = produits.filter(
            categorie_id=categorie_id
        )

    # Pagination
    paginator = Paginator(produits, 9)

    page_number = request.GET.get("page")

    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "categories": Category.objects.all(),
        "recherche": recherche,
        "categorie_selectionnee": categorie_id,
    }

    return render(
        request,
        "products/product_list.html",
        context
    )


from reviews.forms import ReviewForm
from django.db.models import Avg
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect
from .models import Wishlist


def product_detail(request, slug):

    produit = get_object_or_404(
        Product,
        slug=slug,
        actif=True
    )

    reviews = produit.reviews.all()
    avg_rating = reviews.aggregate(Avg('note'))['note__avg'] or 0
    avg_rating_int = int(round(avg_rating))

    # Formulaire d'avis prérempli si l'utilisateur a déjà donné son avis
    user_review = None
    in_wishlist = False
    if request.user.is_authenticated:
        user_review = reviews.filter(utilisateur=request.user).first()
        in_wishlist = Wishlist.objects.filter(utilisateur=request.user, produits=produit).exists()

    review_form = ReviewForm(instance=user_review) if user_review else ReviewForm()

    # Compter les étoiles pour l'affichage
    stars_filled = range(avg_rating_int)
    stars_empty = range(5 - avg_rating_int)

    context = {
        "produit": produit,
        "reviews": reviews,
        "avg_rating": round(avg_rating, 1),
        "stars_filled": stars_filled,
        "stars_empty": stars_empty,
        "review_form": review_form,
        "already_reviewed": user_review is not None,
        "in_wishlist": in_wishlist,
    }

    return render(
        request,
        "products/product_detail.html",
        context
    )


@login_required
def toggle_wishlist(request, product_id):
    produit = get_object_or_404(Product, id=product_id, actif=True)
    wishlist, created = Wishlist.objects.get_or_create(utilisateur=request.user)

    if wishlist.produits.filter(id=product_id).exists():
        wishlist.produits.remove(produit)
        messages.info(request, f"« {produit.nom} » a été retiré de votre liste de souhaits.")
    else:
        wishlist.produits.add(produit)
        messages.success(request, f"« {produit.nom} » a été ajouté à votre liste de souhaits. ❤️")

    # Redirect to referer if exists, else to product_detail
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect("product_detail", slug=produit.slug)


@login_required
def wishlist_view(request):
    wishlist, created = Wishlist.objects.get_or_create(utilisateur=request.user)
    produits = wishlist.produits.all()

    return render(
        request,
        "products/wishlist.html",
        {
            "produits": produits
        }
    )