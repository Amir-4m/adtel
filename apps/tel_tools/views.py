from django.template.response import TemplateResponse
from django.shortcuts import redirect
from django.core.cache import cache
from django.contrib import messages
from django.utils.translation import ugettext_lazy as _

from .tasks import login
from .forms import ConfirmUser
from .models import TelegramSession


def confirm_number(request, api_id):
    if TelegramSession.objects.filter(api_id=api_id).exists():
        form = ConfirmUser()
        if request.method == 'POST':
            form = ConfirmUser(request.POST)
            if form.is_valid():
                data = form.cleaned_data
                code = data.get('code')
                api_id, api_hash, number, password = cache.get(f'telegram_userinfo_{api_id}')
                login.delay(api_id, api_hash, number, code, password)
                cache.delete(f'telegram_userinfo_{api_id}')  # don't have any expiration time before is needed to delete?
                messages.info(request, _('please check your saved message and reload the page'))
                return redirect('admin:tel_tools_telegramsession_changelist')

        return TemplateResponse(request, 'admin/tel_tools/telegramsession/confirm.html', {'form': form})

    return redirect('admin:tel_tools_telegramsession_changelist')
