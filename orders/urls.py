from django.urls import path
from . import views


urlpatterns = [

    path(
        "create/",
        views.create_order,
        name="create_order"
    ),


    path(
        "my-orders/",
        views.my_orders,
        name="my_orders"
    ),


    path(
        "<int:id>/",
        views.order_detail,
        name="order_detail"
    ),

]