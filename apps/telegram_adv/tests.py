from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework.authtoken.models import Token

from django.conf import settings
from django.urls import reverse
from django.contrib.auth.models import User

from apps.telegram_adv.models import TelegramAgent


class CampaignAPITestCase(APITestCase):
    fixtures = ['campaign']

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.get(id=10)
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key)

    def test_create_campaign_contents(self):
        campaign = {
            "title": "testins banner",
            "is_enable": False,
            "status": "approved",
            "start_datetime": "2019-10-15T05:42:49.757Z",
            "end_datetime": "2019-10-15T05:42:49.757Z",
            "max_view": 52000,
            "publishers": [[1, 2500]],
            "agents": ["admood"]
        }

        response_campaign = self.client.post(reverse('campaign-list'), data=campaign)
        self.assertEqual(response_campaign.status_code, status.HTTP_201_CREATED)

        content_1 = {
            "campaign": response_campaign.data['id'],
            "display_text": "banner 1",
            "content": "hi this is my test banner\n\n\nhttps://www.varzesh3.com",
            "links": [
                {
                    "link": "https://www.varzesh3.com",
                    "utm_source": "Admood",
                    "utm_campaign": 1,
                    "utm_medium": "telegram",
                    "utm_term": 1
                }
            ],
            "view_type": "total",
            "mother_channel": -1001203051365,
            "inlines": [
                {
                    "text": "کلیک کن",
                    "row": 0,
                    "column": 0,
                    "link": "https://www.varzesh3.com",
                    "utm_source": "Admood",
                    "utm_campaign": 1,
                    "utm_medium": "telegram",
                    "utm_term": 1
                },
                {
                    "text": "کلیک کن دیگه",
                    "row": 0,
                    "column": 1,
                    "link": "https://www.varzesh3.com",
                    "utm_source": "Admood",
                    "utm_campaign": 1,
                    "utm_medium": "telegram",
                    "utm_term": 1
                }
            ]
        }
        content_2 = {
            "campaign": response_campaign.data['id'],
            "display_text": "banner 2",
            "content": "hi this is my test banner https://www.varzesh3.com",
            "view_type": "partial",
            "mother_channel": -1001203051365,
            "inlines": [
                {
                    "text": "کلیک کن",
                    "row": 0,
                    "column": 0,
                    "link": "https://www.digikal.com"
                }
            ]
        }

        content_sticker = {
            "campaign": response_campaign.data['id'],
            "display_text": "banner 2",
            "view_type": "partial",
            "mother_channel": -1001203051365,
            "is_sticker": True
        }

        content_post_link = {
            "campaign": response_campaign.data['id'],
            "display_text": "banner 2",
            "view_type": "total",
            "post_link": "https://t.me/total_fut/46113/",  # link has regex validation to be just telegram post url
        }

        content_post_link_invalid = {
            "campaign": response_campaign.data['id'],
            "display_text": "banner 2",
            "view_type": "oartial",
            "post_link": "https://varzesh3.com/",  # link has regex validation to be just telegram post url
        }

        response_content_1 = self.client.post(reverse('campaigncontent-list'), data=content_1)
        self.assertEqual(response_content_1.status_code, status.HTTP_201_CREATED)

        response_content_2 = self.client.post(reverse('campaigncontent-list'), data=content_2)
        self.assertEqual(response_content_2.status_code, status.HTTP_201_CREATED)

        response_content_3_sticker = self.client.post(reverse('campaigncontent-list'), data=content_sticker)
        self.assertEqual(response_content_3_sticker.status_code, status.HTTP_201_CREATED)

        response_content_4_post_link = self.client.post(reverse('campaigncontent-list'), data=content_post_link)
        self.assertEqual(response_content_4_post_link.status_code, status.HTTP_201_CREATED)

        response_content_post_link_invalid = self.client.post(reverse('campaigncontent-list'), data=content_post_link_invalid)
        self.assertEqual(response_content_post_link_invalid.status_code, status.HTTP_400_BAD_REQUEST)

        response_get = self.client.get(reverse('campaign-detail', args=[response_campaign.data['id']]))
        # campaign should create with is_enable=False at first
        self.assertEqual(response_get.data['is_enable'], False)

        # try to enable campaign without file, should fail
        response_enable_before_add_file = self.client.patch(
            reverse('campaign-detail', args=[response_campaign.data['id']]),
            data={'is_enable': True}
        )
        self.assertEqual(response_enable_before_add_file.status_code, status.HTTP_400_BAD_REQUEST)

        data = {
            "name": "فایل عکس کمپین",
            "telegram_file_hash": "AgACAgQAAx0EVfktugACAulmVM9ZsnmJ2lHsVj77CddAAMBAAMCAAN4AAMtugACGwQ",
            "file_type": "photo",
            "campaign": response_campaign.data['id']
        }

        response_campaign_file = self.client.post(reverse('campaignfile-list'), data=data)
        self.assertEqual(response_campaign_file.status_code, status.HTTP_201_CREATED)

        response_enable = self.client.patch(
            reverse('campaign-detail', args=[response_campaign.data['id']]),
            data={'is_enable': True}
        )
        self.assertTrue(
            response_enable.data['is_enable'] is True and
            response_enable.data['is_enable'] != response_campaign.data['is_enable']
        )

        report_campaign = self.client.get(reverse('campaign-report', args=[response_campaign.data['id']]))
        self.assertEqual(report_campaign.status_code, status.HTTP_200_OK)
        # report should just return partial contents here we create only two partial of four content
        self.assertTrue(len(report_campaign.data) == 2)

    def test_send_file(self):
        data = {
            "name": "فایل عکس",
            "telegram_file_hash": "AgACAgQAAx0EVfktugACAulmVM9ZsnmJ2lHsVj77CddAAMBAAMCAAN4AAMtugACGwQ",
            "file_type": "photo",
            "campaign_content": 1
        }
        response = self.client.post(reverse('campaignfile-list'), data=data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_get_channels(self):
        response = self.client.get(reverse('telegramchannel-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_not_authenticated(self):
        self.client.logout()
        enable_campaign_url = reverse('campaign-detail', args=[1])
        response = self.client.get(enable_campaign_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_render_campaign(self):
        bot_token = settings.TELEGRAM_BOT['TOKEN']
        TelegramAgent.objects.create(bot_token=bot_token, specific_mark="test")
        response = self.client.get(reverse('campaign-test', args=[1]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
