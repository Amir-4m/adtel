from django.db import models
from django.utils.translation import ugettext_lazy as _


class TelegramSession(models.Model):
    created_time = models.DateTimeField(_('created time'), auto_now_add=True)
    updated_time = models.DateTimeField(_('updated time'), auto_now=True)
    name = models.CharField(_('name'), max_length=64, unique=True)
    number = models.CharField(_('phone number'), max_length=13, unique=True)
    api_id = models.PositiveIntegerField(_('API ID'), unique=True)
    api_hash = models.CharField(_('API Hash'), max_length=32)
    password = models.CharField(_('two-step verification code'), max_length=100, blank=True,
                                help_text=_("fill if you enabled two-step verification"))
    is_enable = models.BooleanField(_('is enable'))
    session = models.TextField(blank=True)

    class Meta:
        db_table = 'telegram_sessions'

    def __str__(self):
        return self.name
