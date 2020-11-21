from django.contrib import admin
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _
from django.utils.safestring import mark_safe
from django.conf import settings

from .models import TelegramUser


@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
    list_display = ['id', 'user_id', 'first_name', 'username', 'get_report_url']
    filter_horizontal = ['agents']
    search_fields = ['username', 'first_name', 'last_name', 'user_id']



    def get_report_url(self, obj):
        return mark_safe(
            '<a href={} target="_blank"><img src="{}" style="width: 15px;"></a>'.format(
                settings.BASE_REPORT_URL + reverse('publisher-report', args=[obj.url_encode()]),
                settings.STATIC_URL + "admin/icons/report.svg"
            )
        )
    get_report_url.short_description = _('report')
