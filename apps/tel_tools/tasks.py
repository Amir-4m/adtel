import logging

from celery import shared_task
from django.core.cache import cache
from django.conf import settings
from django.utils.translation import ugettext_lazy as _

from telethon.sync import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

from .models import TelegramSession

logger = logging.getLogger(__name__)

TELETHON_PROXY = None
if getattr(settings, 'PROXY4TELEGRAM_HOST', ''):
    import socks
    TELETHON_PROXY = (
        socks.HTTP,
        settings.PROXY4TELEGRAM_HOST,
        settings.PROXY4TELEGRAM_PORT,
        # True,
        # settings.PROXY4TELEGRAM_USER,
        # settings.PROXY4TELEGRAM_PASS,
    )


@shared_task
def send_confirm_code(api_id, api_hash, number):
    client = TelegramClient('anon', api_id, api_hash, proxy=TELETHON_PROXY)
    try:
        client.connect()
        res = client.send_code_request(number)
        cache.set(f'telegram_phone_hash_{api_id}', res.phone_code_hash)
        logger.info(_(f"LOGIN CODE SENT FOR {number}"))
    except Exception as e:
        logger.error(_(f"LOGIN CODE NOT SENT FOR {number}\n{e}"))
    else:
        client.disconnect()


@shared_task
def login(api_id, api_hash, number, code, password):
    client = TelegramClient('anon', api_id, api_hash, proxy=TELETHON_PROXY)
    try:
        client.connect()
        phone_code_hash = cache.get(f'telegram_phone_hash_{api_id}')
        try:
            client.sign_in(phone=number, code=code, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError:
            client.sign_in(password=password)
    except Exception as e:
        logger.error(_(f"SIGN IN TO {number} FAILED\n{e}"))
        client.disconnect()
    else:
        logger.info(_(f"SIGN IN TO {number} SUCCESS"))
        client.send_message('me', _('django admin panel enabled for this number'))
        client.disconnect()
        TelegramSession.objects.filter(
            api_id=api_id
        ).update(
            session=StringSession.save(client.session)
        )
