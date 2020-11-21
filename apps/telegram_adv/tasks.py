import logging

from celery import shared_task
from telegram import Bot

from django.db.models import Case, When, F, Sum, IntegerField, Q

from .texts import PAID_PUSH
from .models import CampaignUser, Campaign, BankAccount, TelegramChannel, CampaignContent

logger = logging.getLogger(__name__)


@shared_task
def check_to_calculate_campaign_user(campaign_users_ids):
    campaign_users = CampaignUser.objects.prefetch_related(
        'campaignpost_set'
        ).filter(
        id__in=campaign_users_ids,
        campaign__status__in=[Campaign.STATUS_APPROVED, Campaign.STATUS_CLOSE],
        receipt_date__isnull=True,
    ).annotate(
        has_tariif_posts=Sum(
            Case(
                When(campaignpost__campaign_content__view_type=CampaignContent.TYPE_VIEW_PARTIAL, then=1),
                default=0,
            ), output_field=IntegerField()
        ),
        approved_posts=Sum(
            Case(
                When(campaignpost__approve_time__isnull=False, then=1),
                default=0
            ), output_field=IntegerField()
        )
    ).filter(
        has_tariif_posts=F('approved_posts')
    )

    for campaign_user in campaign_users:
        campaign_user.receipt_price = campaign_user.calculate_price()
        campaign_user.save(update_fields=['updated_time', 'receipt_price'])


@shared_task
def send_paid_push(chat_id, bot_token, campaign_title, channels_tag):
    try:
        push_bot = Bot(token=bot_token)
        push_bot.send_message(chat_id=chat_id, text=PAID_PUSH % (campaign_title, channels_tag), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"send paid push failed user: {chat_id} error: {e}")


@shared_task
def exchange_bank_account_task(from_bank_account_id, to_bank_account_id):
    from_bank_account = BankAccount.objects.get(id=from_bank_account_id)
    to_bank_account = BankAccount.objects.get(id=to_bank_account_id)

    channels = TelegramChannel.objects.filter(
        sheba_id=from_bank_account.id
    ).update(
        sheba_id=to_bank_account.id
    )

    campaign_users = CampaignUser.objects.filter(
        sheba_number=from_bank_account.sheba_number,
        receipt_date__isnull=True,
    ).update(
        sheba_number=to_bank_account.sheba_number,
        sheba_owner=to_bank_account.sheba_owner
    )

    logger.info(f"changing sheba from {from_bank_account} to {to_bank_account}"
                f"{channels} channels and {campaign_users} campaign_users effected")


@shared_task(bind=True,
             max_retries=3)
def delete_invalid_campaign_users(self):
    try:
        for c in CampaignUser.objects.filter(Q(channels__isnull=True) | Q(campaignpost__isnull=True)):
            c.campaignpost_set.all().delete()
            c.channels.clear()
            c.delete()
    except Exception as e:
        raise self.retry(exc=e, countdown=5)


@shared_task
def disable_campaign_by_max_view():
    """
        disable campaigns which even one of the contents views achieved max_view
        and don't read banner views until campaign end datetime.
    """
    campaigns = Campaign.objects.filter(
        status=Campaign.STATUS_APPROVED,
        is_enable=True
    ).only(
        'max_view'
    )

    for campaign in campaigns:
        contents_info = campaign.partial_contents_views()
        if any([cc['views'] >= campaign.max_view for cc in contents_info]):
            campaign.is_enable = False
            campaign.save(update_fields=['updated_time', 'is_enable'])


@shared_task
def remove_test_campaigns_all_data():
    test_campaigns = Campaign.objects.prefetch_related(
        'pushes',
        'contents',
        'contents__files',
        'campaignuser_set__campaignpost_set__campaign_file',
        'campaignuser_set__campaignpost_set__links'
    ).filter(
        status=Campaign.STATUS_TEST
    )

    try:
        for campaign in test_campaigns:
            campaign.publishers.clear()

            campaign_users = campaign.campaignuser_set.all()
            for campaign_user in campaign_users:
                posts = campaign_user.campaignpost_set.all()
                for post in posts:
                    post.links.all().delete()

                posts.delete()
            campaign_users.delete()

            contents = campaign.contents.all()
            for content in contents:
                links = content.links.all()
                for link in links:
                    link.short_links.all().delete()

                links.delete()
                content.files.all().delete()

            contents.delete()

            pushes = campaign.pushes.all()
            for push in pushes:
                push.users.clear()
                push.publishers.clear()

            pushes.delete()

        test_campaigns.delete()

    except Exception as e:
        logger.error(f"remove test data failed, error: {e}")

