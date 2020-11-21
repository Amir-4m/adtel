from django import forms
from django.utils.translation import ugettext_lazy as _


class ConfirmUser(forms.Form):
    code = forms.CharField(label=_('confirm code'), max_length=5)
