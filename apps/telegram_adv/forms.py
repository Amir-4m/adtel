from django import forms
from django.core.exceptions import ValidationError
from django.contrib.admin import widgets, site as admin_site

from apps.tel_tools.models import TelegramSession
from .models import ReceiverChannel, CampaignFile, BankAccount, TelegramChannel


class ImportCampaignUserForm(forms.Form):
    file = forms.FileField(label="file", widget=forms.ClearableFileInput(attrs={'multiple': True}))


class ImportCampaignContentFilesForm(forms.Form):
    channel = forms.ModelChoiceField(queryset=ReceiverChannel.objects.all())
    admin = forms.ModelChoiceField(queryset=TelegramSession.objects.all())
    file_type = forms.ChoiceField(choices=CampaignFile.FILE_TYPES)
    from_message_id = forms.IntegerField()
    to_message_id = forms.IntegerField()


class BankAccountExchangeForm(forms.Form):
    from_bank_account = forms.ModelChoiceField(
        queryset=BankAccount.objects.all(),
        widget=widgets.ForeignKeyRawIdWidget(TelegramChannel._meta.get_field('sheba').remote_field, admin_site),
    )
    to_bank_account = forms.ModelChoiceField(
        queryset=BankAccount.objects.all(),
        widget=widgets.ForeignKeyRawIdWidget(TelegramChannel._meta.get_field('sheba').remote_field, admin_site),
    )

    def clean(self):
        cleaned_data = super().clean()
        fba = cleaned_data.get('from_bank_account')
        tba = cleaned_data.get('to_bank_account')
        if fba == tba:
            raise ValidationError("these two fields shouldn't be same")
