from django.contrib import admin
from django.utils import timezone

from django_admin_listfilter_dropdown.filters import RelatedDropdownFilter
from admin_auto_filters.filters import AutocompleteFilter

from apps.telegram_adv.models import Campaign


class ReadOnlyAdmin(admin.ModelAdmin):
    super_user_can = False

    def _super_user_can(self, request):
        return request.user.is_superuser and self.super_user_can

    def has_add_permission(self, request):
        return self._super_user_can(request)

    def has_delete_permission(self, request, obj=None):
        return self._super_user_can(request)

    def has_change_permission(self, request, obj=None):
        return self._super_user_can(request)

    def get_list_display_links(self, request, list_display):
        if self._super_user_can(request):
            return super().get_list_display_links(request, list_display)
        else:
            return None

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not self._super_user_can(request) and 'delete_selected' in actions:
            del actions['delete_selected']
        return actions


class ReadOnlyEveryOneAdmin(admin.ModelAdmin):
    list_display_links = None

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return obj is None

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions


class ReadOnlyTabularInline(admin.TabularInline):

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class CampaignFilter(AutocompleteFilter):
    title = 'Campaign'
    field_name = 'campaign'
