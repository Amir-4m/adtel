"""
Django settings for conf project.

Generated by 'django-admin startproject' using Django 2.2.2.

For more information on this file, see
https://docs.djangoproject.com/en/2.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/2.2/ref/settings/
"""
import ast
from pathlib import Path

from celery.schedules import crontab
from decouple import config, Csv

from .celery import app as celery_app

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.0/howto/deployment/checklist/

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config("DEBUG", default=False, cast=bool)
DEVEL = config("DEVEL", default=False, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost', cast=Csv())

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config("SECRET_KEY")

# Application definition
INSTALLED_APPS = [
    'apps.telegram_bot',
    'apps.telegram_user',
    'apps.telegram_adv',
    'apps.reports',
    'apps.push',
    'apps.tel_tools',

    'markdownx',
    'rest_framework',
    'rest_framework.authtoken',
    'admin_auto_filters',

    'django.contrib.humanize',
    'django_admin_listfilter_dropdown',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'conf.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'conf.wsgi.application'

# Database
# https://docs.djangoproject.com/en/2.2/ref/settings/#databases
DATABASES = {
    'default': {
        'ENGINE': config('DB_ENGINE'),
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER', default=''),
        'PASSWORD': config('DB_PASS', default=''),
        'HOST': config('DB_HOST', default=''),
        'PORT': config('DB_PORT', default=''),
        'CONN_MAX_AGE': config('DB_CONN_MAX_AGE', default=0, cast=int),
    }
}
if DATABASES['default']['ENGINE'] == 'django.db.backends.mysql':
    DATABASES['default']['OPTIONS'] = {"charset": "utf8mb4"}

# Password validation
# https://docs.djangoproject.com/en/2.2/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

CACHES = {
    'default': {
        'BACKEND': config('CACHE_BACKEND', default='django.core.cache.backends.locmem.LocMemCache'),
        'LOCATION': config('CACHE_HOST', default=''),
        'KEY_PREFIX': 'ADTEL',
    },
    'session': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        # TODO: put in local_settings
        'LOCATION': '/tmp/django_adtel_cache',
        'TIMEOUT': 2 * 86400,
    }
}

CELERY_BROKER_URL = 'amqp://%(USER)s:%(PASS)s@%(HOST)s' % {
    'USER': config('CELERY_USER'),
    'PASS': config('CELERY_PASS'),
    'HOST': config('CELERY_HOST'),
}
CELERY_ENABLE_UTC = False

PROCESS_CAMPAIGN_TASKS = ast.literal_eval(config('PROCESS_CAMPAIGN_TASKS'))
SEND_PUSH_SCHEDULE = ast.literal_eval(config('SEND_PUSH_SCHEDULE'))
EXPIRE_PUSH_SCHEDULE = ast.literal_eval(config('EXPIRE_PUSH_SCHEDULE'))
SEND_PUSH_SHOT_SCHEDULE = ast.literal_eval(config('SEND_PUSH_SHOT_SCHEDULE'))
REMOVE_TEST_CAMPAIGNS_SCHEDULE = ast.literal_eval(config('REMOVE_TEST_CAMPAIGNS_SCHEDULE'))
CLOSE_CAMPAIGN_BY_MAX_VIEW_SCHEDULE = ast.literal_eval(config('CLOSE_CAMPAIGN_BY_MAX_VIEW_SCHEDULE'))

# push to get shot for campaign
END_SHOT_PUSH_TIME_HOUR = config('END_SHOT_PUSH_TIME_HOUR', cast=int, default=24)

# send shot in bot and make no shot
SEND_SHOT_START_HOUR = config('SEND_SHOT_START_HOUR', cast=int)
SEND_SHOT_END_HOUR = config('SEND_SHOT_END_HOUR', cast=int)

EXPIRE_PUSH_MINUTE = config('EXPIRE_PUSH_MINUTE', default=30, cast=int)

celery_app.conf.beat_schedule = {
    'process_campaign_tasks': {
        'task': 'apps.telegram_bot.tasks.process_campaign_tasks',
        'schedule': crontab(**PROCESS_CAMPAIGN_TASKS),
    },
    'send_push': {
        'task': 'apps.push.tasks.check_push_campaigns',
        'schedule': crontab(**SEND_PUSH_SCHEDULE),
    },
    'expire_push': {
        'task': 'apps.push.tasks.check_expire_campaign_push',
        'schedule': crontab(**SEND_PUSH_SCHEDULE),
    },
    'send_shot_push': {
        'task': 'apps.push.tasks.check_send_shot_push',
        'schedule': crontab(**EXPIRE_PUSH_SCHEDULE),
    },
    'remove_test_campaigns': {
        'task': 'apps.telegram_adv.tasks.remove_test_campaigns_all_data',
        'schedule': crontab(**REMOVE_TEST_CAMPAIGNS_SCHEDULE),
    }
}

PROXY4TELEGRAM_HOST = config('PROXY4TELEGRAM_HOST', default='')
PROXY4TELEGRAM_PORT = config('PROXY4TELEGRAM_PORT', default=0, cast=int)

# Telegram Bot Configs
TELEGRAM_BOT = {
    'TOKEN': config('TELEGRAM_BOT_TOKEN'),
    'MODE': config('TELEGRAM_BOT_MODE', default='POLLING'),
    'WEBHOOK_SITE': config('TELEGRAM_BOT_WEBHOOK_SITE', default=''),
    'PROXY': f"http://{PROXY4TELEGRAM_HOST}:{PROXY4TELEGRAM_PORT}" if PROXY4TELEGRAM_HOST else '',

    # 'WEBHOOK_PREFIX': (Optional[str]), # Should end with "/"
    # 'WEBHOOK_CERTIFICATE': (Optional[str]), # Path to certificate file

    # 'WEBHOOK_IP': (Optional[str]), # If webserver should be runned by django eg. '127.0.0.1'
    # 'WEBHOOK_PORT': (Optional[str]), # If webserver should be runned by django eg. '900'

    # 'ALLOWED_UPDATES': (Optional[list[str]]), # List the types of
    # updates you want your bot to receive. For example, specify
    # ``["message", "edited_channel_post", "callback_query"]`` to
    # only receive updates of these types. See ``telegram.Update``
    # for a complete list of available update types.
    # Specify an empty list to receive all updates regardless of type
    # (default). If not specified, the previous setting will be used.
    # Please note that this parameter doesn't affect updates created
    # before the call to the setWebhook, so unwanted updates may be
    # received for a short period of time.

    # 'TIMEOUT': (Optional[int|float]), # If this value is specified,
    # use it as the read timeout from the server

    # 'WEBHOOK_MAX_CONNECTIONS': (Optional[int]), # Maximum allowed number of
    # simultaneous HTTPS connections to the webhook for update
    # delivery, 1-100. Defaults to 40. Use lower values to limit the
    # load on your bot's server, and higher values to increase your
    # bot's throughput.

    # 'POLL_INTERVAL' : (Optional[float]), # Time to wait between polling updates from Telegram in
    # seconds. Default is 0.0

    # 'POLL_CLEAN': (Optional[bool]), # Whether to clean any pending updates on Telegram servers before
    # actually starting to poll. Default is False.

    # 'POLL_BOOTSTRAP_RETRIES': (Optional[int]), # Whether the bootstrapping phase of the `Updater`
    # will retry on failures on the Telegram server.
    # |   < 0 - retry indefinitely
    # |     0 - no retries (default)
    # |   > 0 - retry up to X times

    # 'POLL_READ_LATENCY': (Optional[float|int]), # Grace time in seconds for receiving the reply from
    # server. Will be added to the `timeout` value and used as the read timeout from
    # server (Default: 2).
}

# Internationalization
# https://docs.djangoproject.com/en/2.2/topics/i18n/
LANGUAGE_CODE = 'fa'
TIME_ZONE = 'Asia/Tehran'
USE_I18N = True
USE_L10N = False
USE_TZ = False

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.0/howto/static-files/
STATIC_ROOT = BASE_DIR / 'static'
STATIC_URL = '/static/'

MEDIA_ROOT = BASE_DIR / 'media'
MEDIA_URL = '/media/'

FIXTURE_DIRS = [
    BASE_DIR / 'fixtures',
]

LOCALE_PATHS = [
    BASE_DIR / 'locale',
]

LOG_DIR = BASE_DIR / 'logs'
LOGGING = ({
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '[%(asctime)s] %(levelname)s %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
        'verbose': {
            'format': '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'filters': ['require_debug_true'],
            'class': 'logging.StreamHandler',
            'formatter': 'verbose'
        },
        'file': {
            'level': 'DEBUG' if DEBUG else 'INFO',
            'class': 'logging.FileHandler',
            'formatter': 'verbose' if DEBUG else 'simple',
            'filename': LOG_DIR / 'django.log',
        },
        'db_queries': {
            'level': 'DEBUG',
            'filters': ['require_debug_true'],
            'class': 'logging.FileHandler',
            'filename': LOG_DIR / 'db_queries.log',
        },
    },
    'loggers': {
        'django.db.backends': {
            'level': 'DEBUG',
            'handlers': ['db_queries'],
            'propagate': False,
        },
        'apps': {
            'level': 'DEBUG',
            'handlers': ['file', 'console'],
        },

        # 'telegram.ext.dispatcher': {
        #     'level': 'DEBUG',
        #     'handlers': ['file'],
        # },
    },
})

REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'rest_framework.schemas.coreapi.AutoSchema',
    'DATETIME_FORMAT': '%Y-%m-%d %H:%M',
    'TIME_FORMAT': '%H:%M',
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
    'DEFAULT_PARSER_CLASSES': (
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser',
    ),
    'TEST_REQUEST_DEFAULT_FORMAT': 'json'
}

# TELEGRAM_SESSION_DIR = BASE_DIR / 'tel_tools/sessions/'

CREATOR_BOT_TOKEN = config('CREATOR_BOT_TOKEN')
BOT_VIEW_CHANNEL_ID = config('BOT_VIEW_CHANNEL_ID', cast=int)

BASE_URL = config('BASE_URL')
BASE_REPORT_URL = config('BASE_REPORT_URL')

ADMD_API_URL = config('ADMD_API_URL')
ADMD_API_TOKEN = config('ADMD_API_TOKEN')

TEST_CAMPAIGN_USER = config('TEST_CAMPAIGN_USER', cast=int)

CORE_API_URL = config('CORE_API_URL', default="")

if DEVEL is False:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration

    SENTRY_KEY = config('SENTRY_KEY')
    SENTRY_HOST = config('SENTRY_HOST')
    SENTRY_PROJECT_ID = config('SENTRY_PROJECT_ID')
    SENTRY_ENV = config('SENTRY_ENV')

    sentry_sdk.init(
        dsn=f"https://{SENTRY_KEY}@{SENTRY_HOST}/{SENTRY_PROJECT_ID}",
        integrations=[DjangoIntegration(), CeleryIntegration()],
        default_integrations=False,

        # If you wish to associate users to errors (assuming you are using
        # django.contrib.auth) you may enable sending PII data.
        send_default_pii=True,

        # Custom settings
        debug=DEBUG,
        environment=SENTRY_ENV
    )
