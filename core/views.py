from django.shortcuts import render
from products.models import Product
from categories.models import Category


def home(request):
    produits_vedette = Product.objects.filter(actif=True, vedette=True)[:6]
    categories = Category.objects.filter(active=True)[:4]

    context = {
        "produits_vedette": produits_vedette,
        "categories": categories,
    }
    return render(request, 'home.html', context)