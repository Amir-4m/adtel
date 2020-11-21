from django.apps import AppConfig


class PushConfig(AppConfig):
    name = 'apps.push'

    def ready(self):
        import apps.push.signals
