from django.contrib import admin
from django.urls import path
from django.shortcuts import redirect
from django.core.cache import cache

from .models import TelegramSession
from .views import confirm_number
from .tasks import send_confirm_code


@admin.register(TelegramSession)
class TelegramUserAdmin(admin.ModelAdmin):
    list_display = ['number', 'id', 'name', 'api_id', 'api_hash', 'created_time', 'is_enable']

    def get_urls(self):
        return [
                   path('confirm/<api_id>/', self.admin_site.admin_view(confirm_number), name='confirm'),
               ] + super().get_urls()

    def response_change(self, request, obj):
        if '_resend' in request.POST:
            send_confirm_code.delay(obj.api_id, obj.api_hash, obj.number)
            cache.set(f'telegram_userinfo_{obj.api_id}', (obj.api_id, obj.api_hash, obj.number, obj.password))
            return redirect('admin:confirm', obj.api_id)

        return super().response_change(request, obj)

    def response_add(self, request, obj, post_url_continue=None):
        if '_save' in request.POST or '_addanother' in request.POST:
            send_confirm_code.delay(obj.api_id, obj.api_hash, obj.number)
            cache.set(f'telegram_userinfo_{obj.api_id}', (obj.api_id, obj.api_hash, obj.number, obj.password))
            return redirect('admin:confirm', obj.api_id)

        return super().response_add(request, obj, post_url_continue)
