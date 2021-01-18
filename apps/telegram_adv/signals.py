from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.telegram_bot.tasks import upload_file
from .models import CampaignUser, CampaignFile, TelegramChannel
from .tasks import send_paid_push, update_publisher_channel


@receiver(post_save, sender=CampaignFile)
def upload_save_file_id(sender, instance, created, **kwargs):
    if not instance.telegram_file_hash:
        upload_file.apply_async(args=[instance.id], countdown=1)


@receiver(post_save, sender=CampaignUser)
def paid_push_notification(sender, instance, created, **kwargs):
    if not created and instance.has_receipt_date_changed():
        send_paid_push.delay(
            instance.user.user_id,
            instance.agent.bot_token,
            instance.campaign.title,
            instance.push_channels_context()
        )


@receiver(post_save, sender=TelegramChannel)
def create_channel(sender, instance, created, **kwargs):
    if created:
        update_publisher_channel.delay()
