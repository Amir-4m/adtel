# AdMood Telegram Bot    

## .env
```python
DEBUG = True
DEVEL = True

ALLOWED_HOSTS = []

BASE_DIR = '' 
BASE_URL = ""
BASE_REPORT_URL = ""

DB_ENGINE = 'django.db.backends.mysql'
DB_NAME = ''
DB_USER = ''
DB_PASS = ''
DB_HOST = 'localhost'
DB_PORT = '3306'
DB_OPTIONS = {}  # {} If database is postgres or {'charset': 'utf8mb4'} for mysql

CACHE_BACKEND = 'django.core.cache.backends.memcached.MemcachedCache'
CACHE_HOST = 'localhost:11211'

CELERY_USER = ''
CELERY_PASS = ''
CELERY_HOST = '%s:5672/%s' % (DB_HOST, DB_NAME)

CREATOR_BOT_TOKEN = ""
BOT_VIEW_CHANNEL_ID = -100
END_SHOT_TIME_HOUR = 72


TELEGRAM_BOT_TOKEN =  '1051287073:AAHRBK_YTJlYJb5ii2-bxPXdUQNBl5um5H4'
TELEGRAM_BOT_MODE = 'WEBHOOK'
TELEGRAM_BOT_WEBHOOK_SITE =  'https://twh.jobisms.com:8443'


SENTRY_KEY = ""
SENTRY_HOST = ''
SENTRY_PROJECT_ID = 0
SENTRY_ENV = 'development'  # 'production'


ADMD_API_URL = 'admd api url'
ADMD_API_TOKEN = 'admd api token'

TARIFF_TOLERANCE = 0.20     # advertiser and publisher tariff tolerance


PROCESS_CAMPAIGN_TASKS = {'minute': '*/30', 'hour': '*', 'day_of_week': '*', 'day_of_month': '*', 'month_of_year': '*'}
SEND_PUSH_SCHEDULE = {'minute': '*/10', 'hour': '*', 'day_of_week': '*', 'day_of_month': '*', 'month_of_year': '*'}
EXPIRE_PUSH_SCHEDULE = {'minute': '*/10', 'hour': '*', 'day_of_week': '*', 'day_of_month': '*', 'month_of_year': '*'}
SEND_PUSH_SHOT_SCHEDULE = {'minute': '*/10', 'hour': '*', 'day_of_week': '*', 'day_of_month': '*', 'month_of_year': '*'}
REMOVE_TEST_CAMPAIGNS_SCHEDULE = {'minute': '*/10', 'hour': '*', 'day_of_week': '*', 'day_of_month': '*', 'month_of_year': '*'}
CLOSE_CAMPAIGN_BY_MAX_VIEW_SCHEDULE = {'minute': '*/5', 'hour': '*', 'day_of_week': '*', 'day_of_month': '*', 'month_of_year': '*'}
EXPIRE_PUSH_MINUTE = 600  # expire sent push to user 
END_SHOT_PUSH_TIME_HOUR = 5 # send push to user 5 hours before campaign end datetime  
SEND_SHOT_START_HOUR = 5 # check to pass 5 hours of campaign start datetime 
SEND_SHOT_END_HOUR = 120 # user has 5 days after campaign end datetime to send his screen shot 
```

## TELEGRAM PROXY
```python
PROXY4TELEGRAM_HOST = ""
PROXY4TELEGRAM_PORT = 0
PROXY4TELEGRAM_USER = ""
PROXY4TELEGRAM_PASS = ""

API_ID = 'API ID'
API_HASH = 'API hash'
```
