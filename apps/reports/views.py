import logging
import pandas as pd
from khayyam import JalaliDatetime

from django.shortcuts import render, Http404
from django.utils import translation
from django.conf import settings
from django.db.models import Prefetch, Min, Max
from django.views.generic import DetailView
from django.contrib.auth.mixins import PermissionRequiredMixin, LoginRequiredMixin

from apps.telegram_adv.models import Campaign, CampaignPost, CampaignUser, CampaignContent, CampaignPostLog


logger = logging.getLogger(__name__)


def campaign_report(request, campaign_code):

    try:
        campaign = Campaign.objects.get(pk=Campaign.url_decode(campaign_code))
        translation.activate(settings.LANGUAGE_CODE)
        context = {
            'title': campaign.text_display(),
            'status': campaign.get_status_display(),
            'total_contents': campaign.total_contents_views(),
            'partial_contents': campaign.partial_contents_views(),
        }

    except Exception:
        raise Http404

    context['campaign_users'] = list(CampaignUser.report.filter(
        campaign_id=campaign.id,
    ).prefetch_related(
        Prefetch(
            'campaignpost_set',
            queryset=CampaignPost.objects.filter(
                campaign_content__view_type=CampaignContent.TYPE_VIEW_PARTIAL,
                is_enable=True
            ).order_by("campaign_content_id"))
    ).distinct())

    for campaign_user in context['campaign_users']:
        for campaign_post in campaign_user.campaignpost_set.all():
            if campaign_post.views:
                campaign_post.last_views = campaign_post.views
            else:
                views = getattr(campaign_post.logs.last(), 'banner_views', 0)
                campaign_post.last_views = views

    return render(request, 'reports/campaign_report.html', context=context)


def financial_report(request, user_id):
    campaign_users = CampaignUser.report.filter(
        user__user_id=Campaign.url_decode(user_id)
    ).prefetch_related(
        Prefetch(
            'campaignpost_set',
            queryset=CampaignPost.objects.filter(
                is_enable=True
            )
        )
    ).order_by('-id')

    return render(request, 'reports/financial_report.html', context={'campaign_users': campaign_users})


class CampaignUserChartView(LoginRequiredMixin,
                            PermissionRequiredMixin,
                            DetailView):
    permission_required = ("is_staff",)
    login_url = '/adminF077D0/'
    template_name = 'reports/statistics.html'
    queryset = CampaignUser.objects.prefetch_related(
        'campaignpost_set',
        'campaignpost_set__logs'
    ).select_related(
        'campaign'
    )

    def get(self, request, *args, **kwargs):
        context = self.generate_chart()
        return self.render_to_response(context)

    def generate_chart(self):
        campaign_user = self.get_object()
        context = {
            'title': campaign_user.campaign.text_display(),
            'user': campaign_user.user,
            'channels': campaign_user.channel_tags
        }

        campaign_posts_logs_range = CampaignPostLog.objects.filter(
            campaign_post__campaign_content__campaign=campaign_user.campaign
        ).aggregate(
            start_time=Min('created_time'),
            end_time=Max('created_time'),
        )
        start_time = campaign_posts_logs_range['start_time']
        end_time = campaign_posts_logs_range['end_time']

        if start_time is None or end_time is None:
            return context

        date_range = [
            timestamp.to_pydatetime()
            # TODO: dynamic freq set in settings
            for timestamp in pd.date_range(start_time, end_time, freq="30min").tolist()
        ]
        try:
            series = CampaignUserChartView.generate_data(campaign_user, date_range)
        except Exception as e:
            logger.error(f"generate chart for campaign user: {campaign_user.id} failed, error: {e}")
            return context

        categories = [
            CampaignUserChartView.format_datetime(datetime)
            for datetime in date_range
        ]

        return {
            'chart': {
                'title': {'text': campaign_user.campaign.text_display()},
                'xAxis': {'categories': categories, 'offset': 0},
                'yAxis': {'title': {'text': 'تعداد نمایش'}, },
                'tooltip': {
                    'split': 'true',
                    'valueSuffix': ' بازدید '
                },
                'plotOptions': {
                    'area': {
                        'stacking': 'normal',
                        'lineColor': '#666666',
                        'lineWidth': 1,
                        'marker': {
                            'lineWidth': 1,
                            'lineColo': '#666666'
                        }
                    }
                },
                'series': series
            }
        }

    @staticmethod
    def generate_data(campaign_user, date_range):
        series = []

        # return nearest datetime in date_range
        def nearest(log_time):
            datetime = min(date_range, key=lambda x: abs(x - log_time))
            return date_range.index(datetime)

        for post in campaign_user.campaignpost_set.filter(logs__isnull=False).distinct():
            post_logs = [(log.created_time, log.banner_views) for log in post.logs.order_by('id')]
            post_info = {
                'name': f"{post.campaign_content.display_text}\u200e",
                'data': ['null'] * len(date_range),
            }
            for log_info in post_logs:
                date_index = nearest(log_info[0])
                post_info['data'][date_index] = log_info[1]

            # replace null values to previous banner_views or next not null values
            for i, item in enumerate(post_info['data']):
                if item == 'null':
                    if i != 0 and post_info['data'][i - 1] != 'null':
                        post_info['data'][i] = post_info['data'][i - 1]
                    else:
                        index = i + 1
                        while post_info['data'][index] == 'null':
                            index += 1
                        post_info['data'][i] = post_info['data'][index]

            series.append(post_info)

        return series

    @staticmethod
    def format_datetime(datetime):
        return JalaliDatetime(datetime).strftime('%m/%d - %H:%M:%S')


