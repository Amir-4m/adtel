from django.contrib import admin
from django.urls import path
from django.shortcuts import redirect, render
from django.db.models import Q, F

from apps.telegram_adv.models import TelegramChannel, CampaignUser
from apps.telegram_user.models import TelegramUser
from apps.push.models import PushText, CampaignPush, CampaignPushUser
from apps.push.forms import ValidTextForm, PushTextForm
from apps.push.tasks import push_text_send
from apps.utils.admin import ReadOnlyAdmin, CampaignFilter, ReadOnlyTabularInline


# filter queries
def calc_receipt_admins(form):
    channel_list = []
    recipient_ids = []
    recipients_query = TelegramUser.objects.filter(is_valid=True)
    # recipients_query is AdvControl objects
    if form.cleaned_data.get('campaign'):
        recipients_query = CampaignUser.objects.select_related('agent', 'user').filter(
            campaign=form.cleaned_data.get('campaign'),
            agent__in=form.cleaned_data.get('agent_list'),
        ).distinct()

        if form.cleaned_data.get('channel_list') or form.cleaned_data.get('category_list'):
            channel_list = TelegramChannel.objects.filter(
                Q(tag__in=list(map(str.strip, form.cleaned_data.get('channel_list', '').splitlines()))) |
                Q(category__in=form.cleaned_data.get('category_list', []))
            ).values_list('id', flat=True)
            recipients_query = recipients_query.filter(channels__in=channel_list)

        recipient_ids = recipients_query.values_list('user_id', flat=True)

    # recipients_query is TelegramUser objects
    # elif form.cleaned_data.get('channels_chooser'):
    #     recipients_query = recipients_query.filter(user_channels__status=TelegramChannel.STATUS_CONFIRMED)

    # recipients_query is TelegramUser objects
    elif form.cleaned_data.get('admins_chooser'):
        if form.cleaned_data.get('admins_chooser') == 'Admins with Channels':
            recipients_query = recipients_query.filter(id__in=TelegramChannel.objects.values_list('user', flat=True))

        elif form.cleaned_data.get('admins_chooser') == 'Admin without Channels':
            recipients_query = recipients_query.exclude(id__in=TelegramChannel.objects.values_list('user', flat=True))

    # recipients_query is TelegramUser objects
    else:
        if form.cleaned_data.get('channel_list') or form.cleaned_data.get('category_list'):
            channel_list = TelegramChannel.objects.filter(
                Q(tag__in=list(map(str.strip, form.cleaned_data.get('channel_list', '').splitlines()))) |
                Q(category__in=form.cleaned_data.get('category_list', []))
            ).values_list('id', flat=True)
            recipients_query = recipients_query.filter(user_channels__in=channel_list)

        # above block can be replaced with below script if There will be unsatisfied query process
        # elif form.cleaned_data.get('channel_list'):
        #     recipients = recipients.filter(telegramchannel__in=channel_list)
        # elif form.cleaned_data.get('category_list'):
        #     recipients = recipients.filter(telegramchannel__category__in=form.cleaned_data.get('category_list'))

        # if form.cleaned_data.get('channels_status_list'):
        #     recipients_query = recipients_query.filter(user_channels__status__in=form.cleaned_data.get('channels_status_list'))

        # if not any([form.cleaned_data.get(k) for k in ['channel_list', 'category_list', 'channels_status_list']]):
        #     recipients_query = TelegramUser.objects.none()

        if form.cleaned_data.get('admin_list'):
            recipients_query = recipients_query | form.cleaned_data.get('admin_list')

        if form.cleaned_data.get('campaign_owner_list'):
            recipients_query = recipients_query | form.cleaned_data.get('adv_owner_list')

    if not recipient_ids:
        recipient_ids = recipients_query.values_list('pk', flat=True)

    recipients = TelegramUser.objects.prefetch_related('agent').filter(
        is_valid=True,
        agents__in=form.cleaned_data.get('agent_list'),
        pk__in=recipient_ids
    ).values(tu_id=F('pk'), telegram_id=F('user_id'), token=F('agents__bot_token'))

    return recipients, channel_list


def push_send(push_id, recipient_list):
    send_dict = {}
    for row in recipient_list:
        send_dict.setdefault(row['token'], []).append(row['telegram_id'])

    for bot_token, telegram_user_id_list in send_dict.items():
        push_text_send.delay(bot_token, telegram_user_id_list, push_id)


# this is admin push text after click new push
def push_text_admin_submit(request, push_id):
    """
    :param request:
    :param push_id: push object pk
    :return:
    """
    form = PushTextForm()
    if request.method == 'POST':
        form = PushTextForm(request.POST)
        if form.is_valid():
            admin_ids, _ = calc_receipt_admins(form)
            # admin_ids = get_admin_ids(form)
            push_send(push_id, admin_ids)
            return redirect('admin:push_pushtext_changelist')
    context = {
        'form': form,
        'title': 'Push Text'
    }
    return render(request, 'admin/push/push.html', context)


@admin.register(PushText)
class PushTextAdmin(admin.ModelAdmin):
    form = ValidTextForm
    list_display = ['title', 'created_time']
    change_form_template = 'admin/push/change_form_with_push.html'

    def response_change(self, request, obj):
        if 'new_push' in request.POST:
            return redirect('admin:push_text', obj.pk)

        return super().response_change(request, obj)

    def get_urls(self):
        return [
                   path('pre_push_text/<int:push_id>/', self.admin_site.admin_view(push_text_admin_submit),
                        name='push_text'),
               ] + super().get_urls()


class PushUserInline(admin.TabularInline):
    fields = ('user', 'is_delivered', 'status')
    readonly_fields = ('is_delivered',)
    model = CampaignPushUser
    extra = 0

    def is_delivered(self, obj):
        return obj.is_delivered()

    is_delivered.boolean = True


@admin.register(CampaignPush)
class PushCampaignAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'channels', 'confirmed_channels', 'created_time', 'updated_time')
    search_fields = ('campaign__title',)
    list_select_related = ('campaign',)
    filter_horizontal = ('publishers',)
    inlines = (PushUserInline,)
    list_filter = [
        CampaignFilter
    ]

    def channels(self, obj):
        return ", ".join(obj.publishers.values_list('tag', flat=True))

    def confirmed_channels(self, obj):
        return ", ".join(obj.confirmed_channels().values_list('channels__tag', flat=True)) or "-"

    def is_delivered(self, obj):
        return obj.is_delivered()

    is_delivered.boolean = True
