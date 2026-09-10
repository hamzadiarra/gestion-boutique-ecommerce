from django.shortcuts import render
from django.db.models import BooleanField, Case, Count, Value, When
from django.utils import timezone
from datetime import timedelta
from products.models import Product
from categories.models import Category


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
