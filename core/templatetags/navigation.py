from urllib.parse import urlsplit
from django import template
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

register = template.Library()


@register.inclusion_tag("_back_navigation.html", takes_context=True)
def back_navigation(context):
    request = context.get("request")
    if request is None:
        return {"show_back": False}
    path = request.path
    show = path.startswith(("/products/", "/categories/", "/cart/", "/orders/", "/dashboard/")) and path != reverse("create_order")
    fallback = "home"
    if path.startswith("/products/") and path != reverse("product_list"):
        fallback = "product_list"
    elif path.startswith("/categories/") and path != reverse("category_list"):
        fallback = "category_list"
    elif path.startswith("/cart/"):
        fallback = "product_list"
    elif path.startswith("/orders/") and path != reverse("my_orders"):
        fallback = "my_orders"
    target = reverse(fallback)
    referer = request.META.get("HTTP_REFERER", "")
    if referer and url_has_allowed_host_and_scheme(referer, {request.get_host()}, require_https=request.is_secure()):
        parts = urlsplit(referer)
        if parts.path != request.path and not parts.path.startswith(("/accounts/", "/payments/")):
            target = parts.path + ("?" + parts.query if parts.query else "")
    return {"show_back": show, "back_url": target}
