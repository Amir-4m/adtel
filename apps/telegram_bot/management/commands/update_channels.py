from telegram import Bot, error

from django.core.management import BaseCommand
from django.conf import settings

from telegram_adv.models import TelegramChannel


class Command(BaseCommand):
    def handle(self, *args, **options):
        bot = Bot(token=settings.TELEGRAM_BOT.get('TOKEN'))

        channels = TelegramChannel.objects.filter(
            channel_id__isnull=True,
        )

        for channel in channels:
            try:
                channel_info = bot.getChat(channel.tag)
                channel_id = channel_info.id
                channel.channel_id = channel_id
                channel.save(update_fields=['updated_time', 'channel_id'])
            except (error.TelegramError, error.BadRequest):
                print(f"telegram error for channel_id: {channel.tag} channel may be deleted or changed username etc..")
            except Exception as e:
                print(f"error in updating channel: {channel.tag} error: {e}")
