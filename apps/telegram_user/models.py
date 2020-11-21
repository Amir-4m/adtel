from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import ugettext_lazy as _
from apps.utils.url_encoder import UrlEncoder
from apps.telegram_adv.models import TelegramAgent


url_encoder = UrlEncoder()


class TelegramUser(models.Model):
    created_time = models.DateTimeField(_('creation time'), auto_now_add=True)
    updated_time = models.DateTimeField(_('last update time'), auto_now=True)
    # TODO: change to telegram_user_id
    user_id = models.PositiveIntegerField(_('user id'), unique=True)
    first_name = models.CharField(_('first name'), max_length=64, blank=True)
    last_name = models.CharField(_('last name'), max_length=64, blank=True)
    username = models.CharField(_('username'), max_length=64, blank=True)
    is_valid = models.BooleanField(_('is valid'), default=True)
    sticker = models.CharField(_('user sticker'), max_length=150, default='CAADBAADIyIAAnVXHAWQEUtRfnfQ1BYE')

    agents = models.ManyToManyField(TelegramAgent, verbose_name='agents')

    class Meta:
        db_table = 'telegram_user'

    def __str__(self):
        represent = self.username or self.full_name
        return f"{represent} - {self.user_id}"

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()

    def url_encode(self):
        return url_encoder.encode_id(self.user_id)
