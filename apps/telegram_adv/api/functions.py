from django.conf import settings
from django.db.models import Sum, Case, When, Max, F
from django.db.models.functions import Coalesce
from rest_framework import status

from apps.push.models import CampaignPush, CampaignPushUser
from apps.telegram_adv.api.serializers import CampaignUserSerializer
from apps.telegram_adv.models import CampaignContent, TelegramChannel, CampaignUser
from apps.telegram_bot.tasks import render_campaign
from apps.telegram_user.models import TelegramUser


def get_campaign_publisher_views(campaign_id):
    """
        return partial contents views for a specific campaign
    :param campaign_id:
    :return:
    """
    report = []
    for content in CampaignContent.objects.prefetch_related(
            'campaignpost_set__logs'
    ).filter(
        campaign_id=campaign_id,
        view_type=CampaignContent.TYPE_VIEW_PARTIAL
    ).order_by(
        'id'
    ):
        qs = content.campaignpost_set.filter(is_enable=True)
        views = qs.annotate(
            post_views=Case(
                When(
                    views__isnull=True, then=Max('logs__banner_views')
                ), default=F('views')
            )
        ).aggregate(
            views=Coalesce(Sum('post_views'), 0)
        )['views']
        # views = content.campaignpost_set.filter(
        #     is_enable=True,
        #     views__isnull=False
        # ).aggregate(
        #     total_views=Coalesce(Sum('views'), 0)
        # )['total_views']
        #
        # for post in content.campaignpost_set.filter(is_enable=True, views__isnull=True):
        #     views += getattr(post.logs.last(), 'banner_views', 0)
        report.append(
            {
                'content': content.id,
                'views': views,
                'detail': CampaignUserSerializer(
                    CampaignUser.objects.filter(id__in=qs.values_list('campaign_user__id', flat=True)), many=True).data
            }
        )

    return report


def test_create_campaign(campaign):
    """
        create contents in their mother channels then forward to a test_user
            1- create a push object for test_user with it's telegram channels
            2- try to render contents in their mother channels then forward to test_user

    :param campaign:
    :return:
    """
    test_user, _c = TelegramUser.objects.get_or_create(
        user_id=settings.TEST_CAMPAIGN_USER
    )
    campaign_push = CampaignPush.objects.create(
        campaign=campaign,
    )
    test_channel, _c = TelegramChannel.objects.get_or_create(
        channel_id=100200300,
        defaults=dict(
            title="@test",
            sheba_id=1
        )
    )
    test_channel.admins.add(test_user)
    campaign_push.publishers.add(test_channel)
    CampaignPushUser.objects.create(
        campaign_push=campaign_push,
        user=test_user,
        message_id=1997
    )

    try:
        render_campaign(
            campaign_push,
            test_user.user_id,
            test_user.telegramchannel_set.values_list('id', flat=True),
            2000
        )
        return {'detail': True}, status.HTTP_200_OK

    except Exception as e:
        return {'detail': f'{e}'}, status.HTTP_400_BAD_REQUEST

    finally:
        # remove all the test data
        campaign_push.users.clear()
        campaign_push.publishers.clear()
        campaign_push.delete()
