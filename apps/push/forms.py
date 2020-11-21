from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _
from django.contrib.admin.widgets import FilteredSelectMultiple, AdminTextareaWidget

from apps.telegram_adv.models import TelegramAgent, Campaign
from apps.telegram_user.models import TelegramUser


class ValidTextForm(forms.ModelForm):

    def clean(self):
        text = self.cleaned_data.get('text')
        message_id = self.cleaned_data.get('message_id')
        receiver_channel = self.cleaned_data.get('receiver_channel')

        if not (text or message_id):
            raise ValidationError(
                "You must specify either text or message_id.")
        if (message_id or receiver_channel) and not (message_id and receiver_channel):
            raise ValidationError(
                "You must specify message_id and receiver_channel together.")

        return self.cleaned_data


class PushTextForm(forms.Form):
    ADMIN_STATUS = (
        ('', ''),
        ('All Admins', _('All Admins')),
        ('Admins with Channels', _('Admins with Channels')),
        ('Admin without Channels', _('Admin without Channels')),
    )
    campaign = forms.ModelChoiceField(
        label=_('campaign'),
        queryset=Campaign.objects.filter(
            is_enable=True,
            status__in=[Campaign.STATUS_APPROVED, Campaign.STATUS_CLOSE]
        ).order_by('-pk'),
        required=False,
    )
    agent_list = forms.ModelMultipleChoiceField(
        queryset=TelegramAgent.objects.all(),
        widget=FilteredSelectMultiple(_('agent_list'), False),
        required=False,
        label=_('agent list')
    )
    admins_chooser = forms.ChoiceField(
        label=_('admins chooser'),
        required=False,
        choices=ADMIN_STATUS,
    )
    admin_list = forms.ModelMultipleChoiceField(
        queryset=TelegramUser.objects.filter(is_valid=True),
        widget=FilteredSelectMultiple(_('admin_list'), False),
        required=False,
        label=_('admin list')
    )
    channel_list = forms.CharField(
        widget=AdminTextareaWidget,
        required=False,
        label=_('channel list')
    )

    class Media:
        css = {
            'all': [
                'admin/css/widgets.css',
            ],
        }
        js = ['/adminF077D0/jsi18n/']

    def clean(self):
        cleaned_data = super().clean()

        if not any(_ for _ in cleaned_data.values()):
            raise forms.ValidationError('You must specify at least one of "admins_chooser, admin_list,'
                                        ' channel_list, category_list, channels_status_list or adv_owner_list" fields')

        if not cleaned_data.get('agent_list'):
            raise forms.ValidationError('"Agent_list" is required.')

        return self.cleaned_data
