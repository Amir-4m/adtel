from django.urls import path, include

urlpatterns = [
    path('', include("apps.telegram_adv.api.urls")),
]
