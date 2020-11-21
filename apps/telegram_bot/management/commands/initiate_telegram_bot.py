import os
import logging

from django.core.management import BaseCommand
from django.conf import settings

from telegram.ext import Updater
from telegram.error import InvalidToken, TelegramError

from apps.telegram_bot.views import urljoin, add_handlers

logger = logging.getLogger(__name__)

TELEGRAM_BOT_SETTING = getattr(settings, 'TELEGRAM_BOT', {})

proxy_url = None
if TELEGRAM_BOT_SETTING.get('PROXY'):
    proxy_url = TELEGRAM_BOT_SETTING['PROXY']


class Command(BaseCommand):

    def handle(self, *args, **options):

        mode = TELEGRAM_BOT_SETTING.get('MODE', 'POLLING')
        logger.info('Django Telegram Bot <{} mode>'.format(mode))

        token = TELEGRAM_BOT_SETTING.get('TOKEN')
        try:
            updater = Updater(token, request_kwargs=dict(proxy_url=proxy_url))
        except InvalidToken:
            logger.error(f'Invalid Bot Token : {token}')
            return

        if mode == 'WEBHOOK':
            webhook_site = TELEGRAM_BOT_SETTING.get('WEBHOOK_SITE')
            webhook_prefix = TELEGRAM_BOT_SETTING.get('WEBHOOK_PREFIX', '')
            if not webhook_site:
                logger.error('Required WEBHOOK_SITE missing in settings')
                return
            webhook_url = urljoin(webhook_site, webhook_prefix, token)

            cert = TELEGRAM_BOT_SETTING.get('WEBHOOK_CERTIFICATE')
            certificate = None
            if cert:
                if os.path.exists(cert):
                    logger.info('WEBHOOK_CERTIFICATE found in {}'.format(cert))
                    certificate = open(cert, 'rb')
                else:
                    logger.error('WEBHOOK_CERTIFICATE not found in {} '.format(cert))

            try:
                max_connections = TELEGRAM_BOT_SETTING.get('WEBHOOK_MAX_CONNECTIONS', 40)
                allowed_updates = TELEGRAM_BOT_SETTING.get('ALLOWED_UPDATES')
                timeout = TELEGRAM_BOT_SETTING.get('TIMEOUT')

                # updater.start_webhook(listen='127.0.0.1', port=5000, url_path=token)
                updater.bot.set_webhook(
                    url=webhook_url,
                    certificate=certificate,
                    timeout=timeout,
                    max_connections=max_connections,
                    allowed_updates=allowed_updates
                )

                logger.info(f'Telegram Bot <{updater.bot.username}> setting webhook [ {updater.bot.get_webhook_info()} ]')

            except TelegramError as e:
                logger.error(f'Telegram Error : {e}')
                return

        else:
            try:
                updater.bot.delete_webhook()
                add_handlers(updater.dispatcher)
                updater.start_polling()
            except TelegramError as e:
                logger.error(f'Telegram Error : {e}')
                return
