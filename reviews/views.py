from django.utils.translation import gettext
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from products.models import Product
from .models import Review
from .forms import ReviewForm


@login_required
def add_review(request, product_id):
    produit = get_object_or_404(Product, id=product_id, actif=True)

    if request.method == "POST":
        form = ReviewForm(request.POST)
        if form.is_valid():
            Review.objects.update_or_create(
                produit=produit,
                utilisateur=request.user,
                defaults={
                    "note": form.cleaned_data["note"],
                    "commentaire": form.cleaned_data["commentaire"]
                }
            )
            messages.success(request, gettext("Votre avis a été enregistré avec succès ! ★"))
        else:
            messages.error(request, gettext("Impossible d'enregistrer l'avis. Données invalides."))

    return redirect("product_detail", slug=produit.slug)
