from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from products.views import product_list
from .models import Category


def category_list(request):
    categories = Category.objects.filter(active=True).annotate(product_count=Count("products", filter=Q(products__actif=True)))
    return render(request, "categories/category_list.html", {"categories": categories})


def category_detail(request, slug):
    return product_list(request, category=get_object_or_404(Category, slug=slug, active=True))
