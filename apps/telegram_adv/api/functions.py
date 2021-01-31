from django.conf import settings
from django.db.models import Sum, Case, When, Max, F
from django.db.models.functions import Coalesce
from rest_framework import status

from apps.push.models import CampaignPush, CampaignPushUser
from apps.telegram_adv.api.serializers import CampaignUserSerializer
from apps.telegram_adv.models import CampaignContent, TelegramChannel, CampaignUser, CampaignPostLog
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
        # qs = content.campaignpost_set.filter(is_enable=True)
        # views = qs.annotate(
        #     post_views=Case(
        #         When(
        #             views__isnull=True, then=Max('logs__banner_views')
        #         ), default=F('views')
        #     )
        # ).aggregate(
        #     views=Coalesce(Sum('post_views'), 0)
        # )['views']
        qs = CampaignPostLog.objects.filter(campaign_post__is_enable=True, campaign_post__campaign_content=content)

        views = qs.values('campaign_post').annotate(post_views=Max('banner_views')).aggregate(views=Coalesce(Sum('post_views'), 0))['views']

        hourly_views = {}
        hourly = qs.values('created_time__hour', 'campaign_post').annotate(total_view=Max('banner_views'))
        for _h in hourly:
            hourly_views.setdefault(_h['created_time__hour'], 0)
            hourly_views[_h['created_time__hour']] += _h['total_view']

        report.append(
            {
                'content': content.id,
                'views': views,
                'hourly': hourly_views,
                'detail': CampaignUserSerializer(
                    CampaignUser.objects.filter(id__in=qs.values_list('campaign_post__campaign_user__id', flat=True)), many=True).data
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
