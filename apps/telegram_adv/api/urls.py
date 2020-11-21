from rest_framework.routers import DefaultRouter

from .views import (
    CampaignViewSet,
    TelegramChannelViewSet,
    CampaignFileViewSet,
    CampaignContentViewSet
)

router = DefaultRouter()
router.register('campaigns', CampaignViewSet)
router.register('contents', CampaignContentViewSet)
router.register('files', CampaignFileViewSet)
router.register('channels', TelegramChannelViewSet)

urlpatterns = router.urls
