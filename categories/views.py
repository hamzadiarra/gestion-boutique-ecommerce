from django.shortcuts import render, get_object_or_404
from .models import Category


def category_list(request):
    categories = Category.objects.filter(active=True)

    context = {
        "categories": categories
    }

    return render(request, "categories/category_list.html", context)


def category_detail(request, slug):
    categorie = get_object_or_404(
        Category,
        slug=slug,
        active=True
    )

    produits = categorie.products.filter(actif=True)

    context = {
        "categorie": categorie,
        "produits": produits
    }

    return render(request, "categories/category_detail.html", context)