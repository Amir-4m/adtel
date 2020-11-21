import csv
import logging

from django.core.management import BaseCommand

from telegram_adv.models import TelegramChannel

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Import channels with relative categories'

    def add_arguments(self, parser):
        # Named (optional) arguments
        parser.add_argument('--file',
                            dest='file_path',
                            help='CSV file')

    def handle(self, *args, **options):
        with open(options['file_path']) as f:
            reader = csv.reader(f)
            data = [row for row in reader]
            for row in data[1:]:
                try:
                    channel, created = TelegramChannel.objects.update_or_create(
                        tag=row[0],
                        defaults=dict(member_no=int(row[1]))
                    )

                    if not created:
                        channel.category.clear()

                    cat_list = []
                    for i in range(2, len(row)):
                        if row[i] == "1":
                            cat_list.append(int(data[0][i]))

                    channel.category.add(*cat_list)

                except Exception as e:
                    logger.exception(msg=f'This error occurred because of {e} in {row}.')
