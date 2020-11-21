from rest_framework import viewsets, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import ParseError

from django.utils.translation import ugettext_lazy as _

from apps.telegram_adv.api.functions import get_campaign_publisher_views, test_create_campaign
from apps.telegram_adv.api.serializers import (
    CampaignSerializer,
    CampaignFileSerializer,
    TelegramChannelSerializer,
    CampaignContentSerializer,
    Campaign,
    CampaignContent,
    CampaignFile,
    TelegramChannel,
)


class BaseViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]


class CampaignViewSet(BaseViewSet,
                      mixins.CreateModelMixin,
                      mixins.UpdateModelMixin,
                      mixins.RetrieveModelMixin):
    serializer_class = CampaignSerializer
    queryset = Campaign.objects.prefetch_related(
        'contents'
    ).all()

    @action(methods=['get'], detail=True)
    def report(self, request, *args, **kwargs):
        report_data = get_campaign_publisher_views(campaign_id=self.get_object().id)
        return Response(report_data)

    @action(methods=['get'], detail=True)
    def test(self, request, *args, **kwargs):
        campaign = self.get_object()
        if campaign.status != Campaign.STATUS_TEST:
            raise ParseError(_('campaign status is not test'))

        if not campaign.contents.exists():
            raise ParseError(_('you can\'t test campaign without content'))

        response, status = test_create_campaign(campaign=campaign)
        return Response(response, status=status)


class CampaignContentViewSet(BaseViewSet,
                             mixins.CreateModelMixin):
    serializer_class = CampaignContentSerializer
    queryset = CampaignContent.objects.all()


class CampaignFileViewSet(BaseViewSet,
                          mixins.CreateModelMixin):
    serializer_class = CampaignFileSerializer
    queryset = CampaignFile.objects.all()


class TelegramChannelViewSet(BaseViewSet,
                             mixins.ListModelMixin):
    serializer_class = TelegramChannelSerializer
    queryset = TelegramChannel.objects.order_by('id')
