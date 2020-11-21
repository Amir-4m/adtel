import csv
import logging

from django.core.management import BaseCommand

from telegram_user.models import TelegramUser
from telegram_adv.models import TelegramChannel

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Import admins with relative channels'

    def add_arguments(self, parser):
        # Named (optional) arguments
        parser.add_argument('--file',
                            dest='file_path',
                            help='CSV file')

    def handle(self, *args, **options):
        with open(options['file_path']) as f:
            reader = csv.reader(f)
            for row in reader:
                try:
                    user, created = TelegramUser.objects.get_or_create(
                        user_id=row[2],
                        defaults=dict(
                            first_name=row[1],
                            last_name='',
                            username=row[0]
                        )
                    )

                    channel, created = TelegramChannel.objects.get_or_create(
                        tag=row[3],
                        defaults=dict(title=row[4])
                    )

                    channel.user.add(user.id)
                except Exception as e:
                    logger.exception(msg=f'This error occurred because of {e} in {row}.')
