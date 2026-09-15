from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('offline/sync/', views.offline_sync_payload, name='offline_sync_payload'),
    path('assistant/ask/', views.assistant_ask, name='assistant_ask'),
]
