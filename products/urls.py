from django.urls import path
from . import views

urlpatterns = [
    path("", views.product_list, name="product_list"),
    path("wishlist/", views.wishlist_view, name="wishlist"),
    path("wishlist/toggle/<int:product_id>/", views.toggle_wishlist, name="toggle_wishlist"),
    
    path("<slug:slug>/", views.product_detail, name="product_detail"),
]