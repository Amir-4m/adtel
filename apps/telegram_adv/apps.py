from django.apps import AppConfig


class AdvertisementConfig(AppConfig):
    name = 'apps.telegram_adv'

    def ready(self):
        import apps.telegram_adv.signals
