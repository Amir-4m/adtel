from django.urls import path
from django.conf import settings

from .views import web_hook

webhook_prefix = settings.TELEGRAM_BOT.get('WEBHOOK_PREFIX', '')

urlpatterns = [
    path(f"{webhook_prefix}<str:token>", web_hook, name='telegram-webhook'),
]
