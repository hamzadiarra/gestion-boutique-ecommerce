from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
    path("admin/", admin.site.urls),

    path("", include("core.urls")),
    path("products/", include("products.urls")),
    path("categories/", include("categories.urls")),
    path("cart/", include("cart.urls")),
    path("orders/", include("orders.urls")),
    path("payments/", include("payments.urls")),
    path("accounts/", include("accounts.urls")),
    path("reviews/", include("reviews.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("notifications/", include("notifications.urls")),
]


if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )
