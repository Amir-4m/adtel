from django.contrib import admin
from django.utils import timezone

from django_admin_listfilter_dropdown.filters import RelatedDropdownFilter

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


class CampaignFilter(RelatedDropdownFilter):
    def field_choices(self, field, request, model_admin):
        ordering = ()
        related_admin = model_admin.admin_site._registry.get(field.remote_field.model)
        if related_admin is not None:
            ordering = related_admin.get_ordering(request)
        return field.get_choices(
            include_blank=False,
            ordering=ordering,
            limit_choices_to={
                'status__in': [Campaign.STATUS_APPROVED, Campaign.STATUS_CLOSE],
                'created_time__gt': timezone.now() - timezone.timedelta(days=31),
            }
        )