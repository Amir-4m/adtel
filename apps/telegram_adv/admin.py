import csv
import logging

from django_admin_listfilter_dropdown.filters import RelatedDropdownFilter
from khayyam import JalaliDate

from django.contrib import admin, messages
from django.db import models
from django import forms
from django.shortcuts import reverse, render, redirect
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.urls import path
from django.utils.translation import ugettext_lazy as _
from django.conf import settings
from django.core.cache import cache
from django.core.paginator import Paginator

from apps.utils.admin import ReadOnlyAdmin, ReadOnlyTabularInline, CampaignFilter
from apps.telegram_bot.tasks import read_campaign_posts_views, get_files_id
from .models import (
    TelegramChannel,
    ShortLink,
    ShortLinkLog,
    ReceiverChannel,
    TelegramAgent,
    BankAccount,
    Campaign,
    CampaignPublisher,
    CampaignContent,
    CampaignUser,
    CampaignPost,
    InlineKeyboard,
    CampaignFile,
    CampaignLink,
    CampaignPostLog
)

from .forms import ImportCampaignUserForm, ImportCampaignContentFilesForm, BankAccountExchangeForm
from .tasks import check_to_calculate_campaign_user, exchange_bank_account_task

logger = logging.getLogger(__name__)


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ['sheba_owner', 'sheba_number']
    search_fields = ['sheba_owner', 'sheba_number']

    def get_urls(self):
        return [
                   path('exchange/', self.admin_site.admin_view(bank_account_exchange), name='exchange_sheba'),
               ] + super().get_urls()


def bank_account_exchange(request):
    form = BankAccountExchangeForm()
    if request.method == "POST":
        form = BankAccountExchangeForm(request.POST)
        if form.is_valid():
            from_bank_account = request.POST.get('from_bank_account')
            to_bank_account = request.POST.get('to_bank_account')
            exchange_bank_account_task.delay(from_bank_account, to_bank_account)
            messages.info(request, "BankAccounts are updating .. ")
            return redirect('admin:telegram_adv_bankaccount_changelist')

    extra = '' if settings.DEBUG else '.min'
    js = [
        'vendor/jquery/jquery%s.js' % extra,
        'jquery.init.js',
        'core.js',
        'admin/RelatedObjectLookups.js'
    ]
    return render(
        request,
        'admin/telegram_adv/bankaccount/sheba_exchange.html',
        {
            'form': form,
            'media': forms.Media(js=['admin/js/%s' % url for url in js]),
            'opts': BankAccount._meta
        }
    )


def make_confirmed(modeladmin, request, queryset):
    queryset.update(status='confirmed')


make_confirmed.short_description = _("Mark selected channels as confirmed")


class HasShebaListFilter(admin.SimpleListFilter):
    title = 'Has Sheba'
    parameter_name = 'has_sheba'

    def lookups(self, request, model_admin):
        return (
            ('1', 'Yes'),
            ('0', 'No'),
        )

    def queryset(self, request, queryset):
        # TODO: change condition to null
        if self.value() == '1':
            return queryset.filter(sheba_id__gt=1)
        if self.value() == '0':
            return queryset.filter(sheba_id=1)


@admin.register(TelegramChannel)
class TelegramChannelAdmin(admin.ModelAdmin):
    list_display = ['tag', 'id', 'view_efficiency', 'updated_time', 'member_no', 'sheba']
    search_fields = ['tag', 'admins__username']
    raw_id_fields = ['sheba']
    filter_horizontal = ['admins']
    list_filter = (
        HasShebaListFilter,
        ('admins', RelatedDropdownFilter),
    )
    actions = [make_confirmed]

    # TODO: display in change form
    def admin(self, obj):
        return "\n".join([user.username for user in obj.admins.all()])

    def sheba(self, obj):
        return f"{obj.sheba.sheba_number} - {obj.sheba.sheba_owner}"


class IsConsumedListFilter(admin.SimpleListFilter):
    title = 'Is Consumed'
    parameter_name = 'is_consumed'

    def lookups(self, request, model_admin):
        return (
            ('1', 'Yes'),
            ('0', 'No'),
        )

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(post__isnull=False)
        if self.value() == '0':
            return queryset.filter(post__isnull=True)


@admin.register(ShortLink)
class ShortLinkAdmin(ReadOnlyAdmin):
    list_display = [
        'link', 'id', 'campaign_link', 'created_time', 'reference_id', 'campaign_post'
    ]
    search_fields = ['link', 'reference_id']
    list_filter = (
        IsConsumedListFilter,
        ('campaign_link', RelatedDropdownFilter),
    )
    ordering = ('-pk',)

    def campaign_post(self, obj):
        return obj.post.id


@admin.register(ShortLinkLog)
class ShortLinkLogAdmin(ReadOnlyAdmin):
    list_display = [
        'short_link', 'id', 'ip_count', 'hit_count',
    ]
    ordering = ('-pk',)


def format_date(date):
    year, month, day = date.split('/')
    jdate = JalaliDate(year=year, month=month, day=day)
    return jdate.todate()


class DummyCountPaginator(Paginator):
    def _get_count(self):
        self.allow_empty_first_page = False
        return 7777777

    count = property(_get_count)


@admin.register(ReceiverChannel)
class ReceiverChannelAdmin(admin.ModelAdmin):
    pass


@admin.register(TelegramAgent)
class TelegramAgentAdmin(admin.ModelAdmin):
    list_display = ['bot_name', 'bot_token', 'specific_mark', 'created_time']


def make_approved(modeladmin, request, queryset):
    queryset.update(status=Campaign.STATUS_APPROVED)


make_approved.short_description = _("Mark selected Campaigns as approved")


class CampaignContentInline(ReadOnlyTabularInline):
    model = CampaignContent
    show_change_link = True
    fields = [
        'display_text', 'view_type', 'mother_channel', 'is_sticker'
    ]


class CampaignPublisherInline(ReadOnlyTabularInline):
    model = CampaignPublisher
    fields = ('publisher', 'tariff')


class CampaignFileInline(admin.TabularInline):
    model = CampaignFile
    fields = ['name', 'file_type', 'telegram_file_hash', 'file']
    extra = 0


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'pk', 'status', 'start_datetime', 'end_datetime',
        'get_report_url', 'publish_count', 'is_enable', 'updated_time'
    ]
    list_filter = ['status', 'is_enable']
    search_fields = ['title']
    filter_horizontal = ['receiver_agents']
    actions = (
        make_approved,
    )
    inlines = [
        CampaignFileInline,
        CampaignContentInline,
        CampaignPublisherInline
    ]

    def publish_count(self, obj):
        if obj.status == Campaign.STATUS_APPROVED:
            return obj.campaignuser_set.count()
        else:
            return '-'

    publish_count.short_description = _('channels')

    def get_report_url(self, obj):
        return mark_safe(
            '<a href={} target="_blank"><img src="{}" style="width: 15px;"></a>'.format(
                obj.report_link,
                settings.STATIC_URL + "admin/icons/report.svg"
            )
        )

    get_report_url.short_description = _('report')


class InlineKeyboardInline(admin.TabularInline):
    model = InlineKeyboard
    fields = ('text', 'row', 'column', 'link', 'has_tracker')
    readonly_fields = ('has_tracker',)
    formfield_overrides = {
        models.CharField: {'widget': forms.TextInput(attrs={'size': '20'})},
    }
    extra = 0

    def has_tracker(self, obj):
        return obj.has_tracker

    has_tracker.boolean = True


class CampaignContentLinkInline(admin.TabularInline):
    model = CampaignLink
    fields = ['link', 'extra_data', 'is_inline']
    readonly_fields = ('is_inline',)
    show_change_link = True
    extra = 0

    def is_inline(self, obj):
        return obj.is_inline()

    is_inline.boolean = True


@admin.register(CampaignContent)
class CampaignContentAdmin(admin.ModelAdmin):
    list_display = [
        'campaign', 'display_text', 'mother_channel',
        'view_type', 'file_count'
    ]
    list_select_related = ['campaign', 'mother_channel']
    raw_id_fields = ['campaign', 'mother_channel']
    search_fields = ['campaign__title', 'display_text']
    inlines = [
        InlineKeyboardInline,
        CampaignFileInline,
        CampaignContentLinkInline
    ]
    list_filter = (
        ('campaign', RelatedDropdownFilter),
        'view_type',
    )

    def _response_post_save(self, request, obj):
        return redirect('admin:telegram_adv_campaign_change', obj.campaign_id)

    def get_inline_instances(self, request, obj=None):
        inline_instances = []
        for inline_class in self.inlines:
            if obj is None and inline_class == CampaignFileInline:
                continue

            inline = inline_class(self.model, self.admin_site)
            if request:
                inline_has_add_permission = inline._has_add_permission(request, obj)
                if not (inline.has_view_or_change_permission(request, obj) or
                        inline_has_add_permission or
                        inline.has_delete_permission(request, obj)):
                    continue
                if not inline_has_add_permission:
                    inline.max_num = 0

            if obj is not None and obj.view_type == CampaignContent.TYPE_VIEW_TOTAL:
                inline.max_num = 1

            inline_instances.append(inline)

        return inline_instances

    def get_urls(self):
        return [
                   path('import_files/?<int:pk>/', self.admin_site.admin_view(campaign_content_import_files),
                        name='import-files'),
               ] + super().get_urls()

    def file_count(self, obj):
        return obj.files.count()


def campaign_content_import_files(request, pk=None):
    if pk:
        cache.set("files_for_content", pk)

    form = ImportCampaignContentFilesForm()
    if request.method == "POST":
        form = ImportCampaignContentFilesForm(request.POST)
        if form.is_valid():
            channel_id = request.POST.get('channel')
            admin_id = request.POST.get('admin')
            file_type = request.POST.get('file_type')
            from_message_id = int(request.POST.get('from_message_id'))
            to_message_id = int(request.POST.get('to_message_id'))

            campaign_content_id = cache.get("files_for_content")

            get_files_id.delay(campaign_content_id, channel_id, admin_id, file_type, from_message_id, to_message_id)

            messages.success(request, "get file id task called")

            return redirect('admin:telegram_adv_campaigncontent_changelist')

    return render(request, 'admin/telegram_adv/campaigncontent/import_files.html', {'form': form})


def export_campaign_user_filter_by_campaign(modeladmin, request, queryset):
    campaign_users = queryset.filter(
        receipt_price__isnull=False,
        receipt_date__isnull=True,
        receipt_code=''
    ).exclude(
        sheba_number=''
    ).exclude(
        sheba_owner=''
    ).values(
        'id', 'receipt_price', 'sheba_owner', 'sheba_number'
    )
    if campaign_users:
        response = render(request, 'admin/telegram_adv/campaignuser/export_csv.html', {
            'campaign_users': campaign_users,
        }, content_type='text/csv; charset=utf-8;')
        response['Content-Disposition'] = 'attachment; filename="payment_export.csv"'
        return response

    messages.warning(request, 'Export failed, check Campaign filter, approve date, price, screen shot, or paid before.')
    return redirect('admin:telegram_adv_campaignuser_changelist')


export_campaign_user_filter_by_campaign.short_description = "Export selected CampaignUser as csv"


class IsPaidListFilter(admin.SimpleListFilter):
    title = 'Is Paid'
    parameter_name = 'is_paid'

    def lookups(self, request, model_admin):
        return (
            ('1', 'Yes'),
            ('0', 'No'),
        )

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(receipt_date__isnull=False)
        if self.value() == '0':
            return queryset.filter(receipt_date__isnull=True)


class CampaignUserPostsInline(admin.TabularInline):
    show_change_link = True
    fields = ['title', 'view', 'screen_preview', 'is_approved', 'is_enable']
    readonly_fields = ['title', 'view', 'screen_preview', 'is_approved', 'is_enable']
    model = CampaignPost
    extra = 0

    def title(self, obj):
        return obj.campaign_content.display_text

    def view(self, obj):
        if obj.views:
            return f"{obj.views:,}"

        return '-'

    def screen_preview(self, obj):
        return obj._screen_preview()

    screen_preview.short_description = _('Screen Shot')

    def is_approved(self, obj):
        return obj._is_approved

    is_approved.boolean = True

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CampaignUser)
class CampaignUserAdmin(ReadOnlyAdmin):
    super_user_can = True

    list_display = [
        'campaign', 'user', 'id', 'channel', 'tariff',
        'sheba_owner', 'is_paid', 'receipt_price',
        'calculated_price', 'statistics'
    ]

    readonly_fields = [
        'sheba_number', 'sheba_owner',
        'receipt_price', 'receipt_date', 'receipt_code',
        'campaign', 'user', 'agent'
    ]

    list_select_related = ['campaign', 'user']
    raw_id_fields = ['campaign', 'user']
    filter_horizontal = ['channels']
    search_fields = ['campaign__title', 'user__username', 'user__user_id']
    list_filter = [
        CampaignFilter
    ]
    actions = (
        export_campaign_user_filter_by_campaign,
    )
    inlines = [CampaignUserPostsInline]

    def get_search_results(self, request, queryset, search_term):
        search_results, _b = super().get_search_results(request, queryset, search_term)
        if search_term.startswith('@'):
            channels = queryset.filter(channels__tag__contains=search_term[1:])
            search_results = (search_results | channels).distinct()
        return search_results, _b

    def channel(self, obj):
        return obj.channel_tags

    channel.short_description = _('channels')

    def is_paid(self, obj):
        return obj.paid

    is_paid.boolean = True

    def get_urls(self):
        return [
                   path('import_csv/', self.admin_site.admin_view(campaign_user_csv_import), name='csv-import'),
               ] + super().get_urls()

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser:
            readonly_fields = [
                'campaign', 'user', 'agent'
            ]
            if obj and obj.paid:
                readonly_fields.extend([
                    'receipt_price', 'receipt_date', 'receipt_code', 'sheba_number', 'sheba_owner'
                ])
        else:
            readonly_fields = self.readonly_fields
        return readonly_fields

    def calculated_price(self, obj):
        return obj.calculate_price()

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser or obj is None or obj.receipt_price is None

    def statistics(self, obj):
        return mark_safe(
            '<a href={} target="_blank"><img src="{}" style="width: 15px;"></a>'.format(
                reverse('campaign-chart', args=[obj.id]),
                settings.STATIC_URL + "admin/icons/report.svg"
            ))


def campaign_user_csv_import(request):
    form = ImportCampaignUserForm()
    if request.method == "POST":
        form = ImportCampaignUserForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                file = request.FILES['file']
                decoded_file = file.read().decode('utf-8').splitlines()
                spamreader = csv.reader(decoded_file)
            except Exception as e:
                messages.error(request, f"Reading file got exception: {e}")
                return redirect('admin:telegram_adv_campaignuser_changelist')

            error_list = []
            for row in spamreader:
                try:
                    date = format_date(row[1])
                    sheba_number = row[2]
                    sheba_owner = row[3]
                    price = int("".join(row[4].split(',')))
                    campaign_user_id = row[7]
                    code = row[9]
                    campaign_user = CampaignUser.objects.get(id=campaign_user_id)
                    if sheba_number.startswith("IR") and campaign_user.sheba_number != sheba_number:
                        campaign_user.sheba_number = sheba_number
                        campaign_user.sheba_owner = sheba_owner
                    campaign_user.receipt_code = code
                    campaign_user.receipt_date = date
                    campaign_user.receipt_price = price
                    campaign_user.save(
                        update_fields=[
                            'updated_time', 'receipt_code', 'receipt_date',
                            'receipt_price', 'sheba_number', 'sheba_owner'
                        ]
                    )
                except CampaignUser.DoesNotExist:
                    logger.error(f"no CampaignUser by id: {campaign_user_id}")
                except IndexError as e:
                    logger.warning(f"IndexError at row:{row} error: {e}")
                except ValueError as e:
                    logger.debug(f"ValueError row: {row} got exception: {e}")
                except Exception as e:
                    error_list.append((row, e))

            if error_list:
                for row, e in error_list:
                    messages.error(request, f"while importing row {row} got exception: {e}")
            else:
                messages.success(request, f"CampaignUsers updated successfully")

            return redirect('admin:telegram_adv_campaignuser_changelist')

    return render(request, 'admin/telegram_adv/campaignuser/upload_csv.html', {'form': form})


class HasScreenShotListFilter(admin.SimpleListFilter):
    title = 'Has Screen Shot'
    parameter_name = 'has_screen_shot'

    def lookups(self, request, model_admin):
        return (
            ('1', 'Yes'),
            ('0', 'No'),
        )

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.exclude(screen_shot='').exclude(screen_shot='no_shot')
        if self.value() == '0':
            return queryset.filter(screen_shot__in=['', 'no_shot'])


class HasTariffPostListFilter(admin.SimpleListFilter):
    title = 'Has Tariff Shot'
    parameter_name = 'has_tariff'

    def lookups(self, request, model_admin):
        return (
            ('1', 'Yes'),
            ('0', 'No'),
        )

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(campaign_content__view_type=CampaignContent.TYPE_VIEW_PARTIAL)
        if self.value() == '0':
            return queryset.filter(campaign_content__view_type=CampaignContent.TYPE_VIEW_TOTAL)


class HasShortLinkListFilter(admin.SimpleListFilter):
    title = 'Has ShortLink'
    parameter_name = 'has_short_link'

    def lookups(self, request, model_admin):
        return (
            ('1', 'Yes'),
            ('0', 'No'),
        )

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(short_link__isnull=False)
        if self.value() == '0':
            return queryset.filter(short_link__isnull=True)


# new models register
def update_campaign_posts_view(modeladmin, request, queryset):
    read_campaign_posts_views.delay(
        list(queryset.values_list('id', flat=True)),
        log_mode=False,
        update_views=True
    )


update_campaign_posts_view.short_description = _("Update Views for selected posts")


def approve_screenshots(modeladmin, request, queryset):
    q = queryset.exclude(
        screen_shot__in=['', 'no_shot']
    ).filter(
        views__isnull=False,
        campaign_content__view_type=CampaignContent.TYPE_VIEW_PARTIAL,
    )
    campaign_users_ids = list(q.values_list('campaign_user_id', flat=True))
    q.update(approve_time=timezone.now())
    if campaign_users_ids:
        check_to_calculate_campaign_user.apply_async(args=[campaign_users_ids], countdown=2)


approve_screenshots.short_description = _("Mark selected Screenshots as approved")


class CampaignPostAdminForm(forms.ModelForm):
    last_log_view = forms.IntegerField(disabled=True)
    user = forms.CharField()

    class Meta:
        model = CampaignPost
        fields = '__all__'


@admin.register(CampaignPost)
class CampaignPostAdmin(ReadOnlyAdmin):
    super_user_can = True
    form = CampaignPostAdminForm
    list_display = [
        'campaign_content', 'id', 'user', 'view_type',
        'has_tariff', 'has_tracker', 'is_enable',
        'is_approved', 'screen_preview', 'message_id', 'views'
    ]
    readonly_fields = [
        'campaign_content', 'campaign_user', 'campaign_file',
        'approve_time', 'screen_time'
    ]
    list_select_related = ['campaign_content', 'campaign_user', 'campaign_file']
    search_fields = ['=campaign_user__user__username']
    actions = [approve_screenshots, update_campaign_posts_view]
    list_filter = (
        HasTariffPostListFilter,
        HasScreenShotListFilter,
        HasShortLinkListFilter,
    )

    list_per_page = 50

    def get_search_results(self, request, queryset, search_term):
        search_results, _b = super().get_search_results(request, queryset, search_term)
        if search_term.startswith('@'):
            channels = queryset.filter(campaign_user__channels__tag__contains=search_term[1:])
            search_results = (search_results | channels).distinct()
        return search_results, _b

    def channels(self, obj):
        return obj.campaign_user.channel_tags

    def view_type(self, obj):
        return obj.campaign_content.view_type

    def last_log_view(self, obj):
        last_log = obj.logs.last()
        if last_log:
            return last_log.banner_views
        return '-'

    def user(self, obj):
        return obj.campaign_user.user

    def screen_preview(self, obj):
        return obj._screen_preview()

    screen_preview.short_description = _('Screen Shot')

    def is_approved(self, obj):
        return obj._is_approved

    is_approved.boolean = True

    def has_tariff(self, obj):
        return obj._has_tariff

    has_tariff.boolean = True

    def has_tracker(self, obj):
        return obj.has_tracker

    has_tracker.boolean = True

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = super().get_readonly_fields(request, obj)
        if request.user.is_superuser:
            readonly_fields = [
                'campaign_content', 'campaign_user', 'campaign_file'
            ]
        readonly_fields.extend(['last_log_view', 'user'])
        return set(readonly_fields)

    def has_change_permission(self, request, obj=None):
        if obj and obj.campaign_user.receipt_price:
            return False
        else:
            return request.user.is_superuser or obj is None or not (
                    obj.campaign_user.approve_time and obj.campaign_user.receipt_code
            )

    def has_add_permission(self, request):
        return request.user.is_superuser


@admin.register(CampaignPostLog)
class CampaignPostLogAdmin(ReadOnlyAdmin):
    list_display = ['campaign_post', 'campaign', 'created_time', 'banner_views']
    list_select_related = ['campaign_post']
    list_filter = [
        ('campaign_post__campaign_content__campaign', RelatedDropdownFilter),
    ]
    search_fields = ['=campaign_post__id']
    paginator = DummyCountPaginator

    def campaign_user(self, obj):
        return obj.campaign_post.campaign_user.id

    def campaign(self, obj):
        return obj.campaign_post.campaign_content.campaign.title


@admin.register(CampaignLink)
class CampaignLinkAdmin(admin.ModelAdmin):
    list_display = ['campaign_content', 'id', 'link']
    list_select_related = ['campaign_content']


@admin.register(CampaignPublisher)
class CampaignPublisherAdmin(ReadOnlyAdmin):
    list_display = ('campaign', 'publisher', 'tariff')
    list_select_related = ('campaign', 'publisher')
    raw_id_fields = ('campaign', 'publisher')
    list_filter = (
        CampaignFilter,
    )
