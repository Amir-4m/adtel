from django.urls import path
from django.views.decorators.cache import cache_page

from apps.reports.views import CampaignUserChartView, campaign_report, financial_report

urlpatterns = [
    path('advertiser/<str:campaign_code>/', cache_page(60 * 15)(campaign_report), name='advertiser-report'),
    path('publisher/<str:user_id>/', cache_page(60 * 15)(financial_report), name='publisher-report'),
    path('campaign_chart/<int:pk>/', CampaignUserChartView.as_view(), name='campaign-chart'),
]
