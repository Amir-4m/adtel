import logging

from django.conf import settings
from django.utils import timezone
from django.core.cache import cache
from django.db.models import Sum, Prefetch, Q
from django.db.models.functions import Coalesce

from telegram import Bot
from telegram.utils.request import Request
from celery import shared_task

from apps.telegram_adv.models import CampaignPublisher, Campaign, CampaignUser, CampaignContent, CampaignFile
from apps.telegram_bot.buttons import campaign_push_reply_markup
from apps.push.models import PushText, CampaignPush, CampaignPushUser
from apps.push.texts import SEND_CAMPAIGN_PUSH, SEND_SHOT_PUSH

logger = logging.getLogger(__name__)

token = settings.TELEGRAM_BOT['TOKEN']
proxy_url = settings.TELEGRAM_BOT['PROXY']
request = Request(con_pool_size=4, connect_timeout=3.05, read_timeout=27, proxy_url=proxy_url)
bot = Bot(token=token, request=request)


@shared_task
def push_text_send(bot_token, telegram_user_id_list, push_id):
    _bot = Bot(token=bot_token, request=request)
    push = PushText.objects.get(id=push_id)
    if push.message_id:
        context = dict(method=_bot.forward_message,
                       from_chat_id=push.receiver_channel.tag or int(push.receiver_channel.chat_id),
                       message_id=push.message_id)

    elif push.image:
        context = dict(method=_bot.send_photo,
                       caption=push.text,
                       photo=push.image)

    else:
        context = dict(method=_bot.send_message,
                       text=push.text)

    method = context.pop('method')
    for admin_user_id in telegram_user_id_list:
        try:
            method(chat_id=admin_user_id, **context)
        except Exception as e:
            logger.error(
                f'Failed to push text with id: {push.id}, user_id: {admin_user_id}, agent: {bot_token}, error: {e}')


@shared_task
def check_push_campaigns():
    """
        send push for campaigns which campaignusers channels views is less than campaign max_view
    :return:
    """
    campaigns = Campaign.objects.prefetch_related(
        'campaignuser_set',
        'pushes'
    ).filter(
        status=Campaign.STATUS_APPROVED,
        is_enable=True,
        start_datetime__lte=timezone.now(),
        end_datetime__gte=timezone.now(),
        file__isnull=False
    ).annotate(
        confirmed_views=Coalesce(Sum('campaignuser__channels__view_efficiency'), 0)
    )

    for campaign in campaigns:
        # no reaction pushes should count as confirmed until user reject or expire
        void_push_views = campaign.pushes.filter(
            status=CampaignPush.STATUS_SENT,
        ).aggregate(
            views=Coalesce(Sum('publishers__view_efficiency'), 0)
        )['views']
        total_counted_views = campaign.confirmed_views + void_push_views

        if campaign.max_view > total_counted_views:
            generate_campaign_push(campaign.id, campaign.max_view - total_counted_views)


def generate_campaign_push(campaign_id, campaign_remain_views):
    """
        create campaign pushes for campaign due to remain views and channels which has no campaign user
        or push status is not expired or rejected to avoid conflict

    :param campaign_id:
    :param campaign_remain_views:
    :return:
    """
    no_push_campaign_publishers = CampaignPublisher.objects.prefetch_related(
        'publisher__admins',
        'publisher__sheba'
    ).filter(
        ~Q(
            publisher_id__in=CampaignUser.objects.filter(
                campaign_id=campaign_id
            ).values_list('channels__id', flat=True)
        ) &
        ~Q(
            publisher_id__in=CampaignPush.objects.filter(
                campaign_id=campaign_id
            ).values_list('publishers__id', flat=True)
        ),
        campaign_id=campaign_id,
    ).order_by(
        'id'
    )

    sum_view_efficiency = 0
    user_channels = {}
    for campaign_publisher in no_push_campaign_publishers:
        if sum_view_efficiency + campaign_publisher.publisher.view_efficiency > campaign_remain_views:
            continue

        sum_view_efficiency += campaign_publisher.publisher.view_efficiency
        user_channels.setdefault(
            tuple(campaign_publisher.publisher.admins.order_by('id').values_list('id', flat=True)),
            []
        ).append(
            campaign_publisher.publisher
        )

    for i, _users_channels in enumerate(user_channels.items()):
        users, channels = _users_channels
        campaign_push = CampaignPush.objects.create(
            campaign_id=campaign_id
        )
        campaign_push.users.set(users)
        campaign_push.publishers.set(channels)

        send_push_to_user.apply_async(
            args=(campaign_push.id,),
            countdown=i * 5
        )


@shared_task
def send_push_to_user(campaign_push, users=None):
    """
        send a CampaignPush to user if has any channel to get campaign

            * campaign pushes with no message_id are not delivered to user successfully just sent

    :param campaign_push:
    :param users:
    :return:
    """
    if isinstance(campaign_push, int):
        campaign_push = CampaignPush.objects.select_related(
            'campaign__file'
        ).prefetch_related(
            'users',
            'publishers'
        ).get(
            id=campaign_push
        )
    if not users:
        users = campaign_push.users.all()

    kwargs = {
        'caption': SEND_CAMPAIGN_PUSH.format(campaign_push.campaign.title),
        'reply_markup': campaign_push_reply_markup(
            campaign_push.id,
            campaign_push.get_push_data(),
        ),
        'parse_mode': 'HTML',
        'photo': campaign_push.campaign.file.get_file()
    }

    for user in users:
        try:
            response = bot.send_photo(chat_id=user.user_id, **kwargs)
            CampaignPushUser.objects.filter(
                campaign_push=campaign_push,
                user=user,
            ).update(
                message_id=response.message_id
            )
        except Exception as e:
            logger.error(f"send push campaign: #{campaign_push.id} failed, error{e}")


@shared_task
def check_expire_campaign_push():
    # TODO: re-check and test query
    expired_campaign_pushes = CampaignPush.objects.prefetch_related(
        'publisher__admins'
    ).exclude(
        status__in=(CampaignPush.STATUS_EXPIRED, CampaignPush.STATUS_REJECTED)
    ).filter(
        created_time__lte=timezone.now() - timezone.timedelta(minutes=settings.EXPIRE_PUSH_MINUTE),
        created_time__gte=timezone.now() - timezone.timedelta(minutes=2 * settings.EXPIRE_PUSH_MINUTE),
        campaign__status=Campaign.STATUS_APPROVED,
        campaign__is_enable=True,
    )

    expired_campaign_pushes_ids = list(expired_campaign_pushes.values_list('id', flat=True))
    if expired_campaign_pushes_ids:
        cancel_push.apply_async(
            kwargs=dict(campaign_pushes=expired_campaign_pushes_ids),
            countdown=1
        )


@shared_task
def cancel_push(**kwargs):
    """
        cancel sent pushes to users in to different way:
            1 - user reject to get campaign  status ---> rejected
            2 - push expiration              status ---> expired

            update CampaignPublish status and delete message in user chat

    :param kwargs:
    :return:
    """

    campaign_pushes = kwargs.get('campaign_pushes')
    if isinstance(campaign_pushes, list):
        status = CampaignPush.STATUS_EXPIRED
        campaign_pushes_ids = campaign_pushes

    else:  # user reject to get campaign
        status = CampaignPush.STATUS_REJECTED
        campaign_pushes_ids = [campaign_pushes]

    campaign_pushes = CampaignPush.objects.prefetch_related(
        'user_pushes__user'
    ).filter(
        id__in=campaign_pushes_ids,
    )

    for campaign_push in campaign_pushes:

        if campaign_push.status != CampaignPush.STATUS_RECEIVED:
            campaign_push.status = status

        for user_push in campaign_push.user_pushes.filter(message_id__isnull=False):
            try:
                bot.delete_message(
                    user_push.user.user_id,
                    user_push.message_id
                )
            except Exception as e:
                logger.error(f"delete push: {campaign_push} failed, error: {e}")

    CampaignPush.objects.bulk_update(campaign_pushes, fields=['updated_time', 'status'])


@shared_task
def check_send_shot_push():
    """
        when campaign is close to it's end datetime send push to campaign users to send
        their screen shots.

        cache users who sent push for avoid resend

    :return:
    """

    campaigns = Campaign.objects.prefetch_related(
        Prefetch(
            'campaignuser_set',
            queryset=CampaignUser.objects.select_related(
                'user',
                'campaign'
            ).filter(
                campaignpost__campaign_content__view_type=CampaignContent.TYPE_VIEW_PARTIAL,
                campaignpost__screen_shot__exact='',
                campaignpost__is_enable=True
            ).distinct()
        )
    ).filter(
        status=Campaign.STATUS_APPROVED,
        end_datetime__gte=timezone.now(),
        end_datetime__lte=timezone.now() + timezone.timedelta(hours=settings.END_SHOT_PUSH_TIME_HOUR)
    ).only('id', 'title')

    for campaign in campaigns:
        push_text = SEND_SHOT_PUSH.format(campaign.title)
        pushed_campaign_users = cache.get(f"push_campaign_{campaign.id}", set())
        campaign_users = set(
            campaign.campaignuser_set.exclude(
                user__user_id__in=pushed_campaign_users
            ).values_list('user__user_id', flat=True)
        )

        for campaign_user_chat_id in campaign_users:
            try:
                bot.send_message(
                    chat_id=campaign_user_chat_id,
                    text=push_text,
                    parse_mode="MARKDOWN"
                )
                pushed_campaign_users.add(campaign_user_chat_id)

            except Exception as e:
                logger.error(f"send shot push to: {campaign_user_chat_id} "
                             f"for campaign: {campaign.title} failed, error: {e}")

        cache.set(f"push_campaign_{campaign.id}", pushed_campaign_users, 4 * 60 * 60)
