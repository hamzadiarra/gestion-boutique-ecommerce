from django.db.models import Count
from django.shortcuts import get_object_or_404, render

from .models import Category


def category_list(request):
    categories = Category.objects.filter(active=True).annotate(product_count=Count("products"))
    return render(request, "categories/category_list.html", {"categories": categories})


def category_detail(request, slug):
    categorie = get_object_or_404(Category, slug=slug, active=True)
    produits = categorie.products.filter(actif=True).select_related("categorie")
    return render(request, "categories/category_detail.html", {
        "categorie": categorie,
        "produits": produits,
        "product_count": produits.count(),
    })
