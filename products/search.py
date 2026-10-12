"""Recherche publique bornée ; les suggestions proviennent exclusivement du catalogue."""
import re
import unicodedata
from difflib import SequenceMatcher
from django.db.models import Q


def normalize(value):
    return "".join(c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c))


def search_products(queryset, query):
    query = query.strip()[:100]
    if not query:
        return queryset
    exact = queryset.filter(Q(nom__icontains=query) | Q(nom_en__icontains=query) |
                            Q(marque__icontains=query) | Q(description__icontains=query) |
                            Q(description_en__icontains=query))
    if exact.exists():
        return exact
    # Repli portable SQLite/PostgreSQL : coût borné, sans charger images/descriptions.
    needle = normalize(query)
    matches = []
    for pk, name, english, brand in queryset.order_by("pk").values_list("pk", "nom", "nom_en", "marque")[:400]:
        tokens = re.findall(r"\w+", normalize(f"{name} {english} {brand}"))
        score = max((1 if needle in token else SequenceMatcher(None, needle, token).ratio()
                     for token in tokens), default=0)
        if score >= .72 and len(needle) >= 3:
            matches.append(pk)
    return queryset.filter(pk__in=matches)
