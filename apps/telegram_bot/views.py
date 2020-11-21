import logging
import json

from queue import Queue
from threading import Thread

from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, Http404

from telegram import Bot, Update
from telegram.utils.request import Request
from telegram.ext import Dispatcher, MessageHandler, CallbackQueryHandler, Filters, CommandHandler
from telegram.error import InvalidToken, TelegramError

from apps.telegram_bot import telegrambot


logger = logging.getLogger(__name__)

bot_settings = settings.TELEGRAM_BOT
bot_token = bot_settings.get('TOKEN')

bot = None
update_queue = Queue()


def add_handlers(dispatcher):
    dispatcher.add_handler(CommandHandler("stop", telegrambot.stop))
    dispatcher.add_handler(CommandHandler("start", telegrambot.start))
    dispatcher.add_handler(MessageHandler(Filters.all, telegrambot.dispatcher))
    dispatcher.add_handler(CallbackQueryHandler(pattern='push', callback=telegrambot.push_campaign_management))
    dispatcher.add_handler(CallbackQueryHandler(telegrambot.call_state_function))
    dispatcher.add_error_handler(telegrambot.error_handler)


def urljoin(*args):
    """
    Joins given arguments into an url. Trailing but not leading slashes are
    stripped for each argument.
    """
    return "/".join(filter(None, map(lambda x: str(x).rstrip('/'), args)))


@csrf_exempt
def web_hook(request, token):
    global update_queue, bot

    if token != bot_token:
        raise Http404('bot token mismatch')

    if bot is None:
        req = None
        if bot_settings.get('PROXY'):
            req = Request(proxy_url=bot_settings['PROXY'])
        bot = Bot(token=bot_token, request=req)
        dispatcher = Dispatcher(bot, update_queue)
        add_handlers(dispatcher)
        thread = Thread(target=dispatcher.start, name='dispatcher')
        thread.start()
        logger.debug('Telegram Bot Initiated')

    try:
        data = json.loads(request.body.decode("utf-8"))
        update = Update.de_json(data, bot)
        update_queue.put(update)

    except json.JSONDecodeError:
        logger.error(f'{request.body} can not be json decoded')
    except InvalidToken:
        logger.error(f'Telegram Bot Invalid Token: {bot_token}')
    except TelegramError as e:
        logger.warning(f'Bot <{bot.username}>: Error {e} was raised while processing Update.')
    except Exception as e:
        logger.error(f'Bot <{bot.username}>: Unknown error: {e}, body: {request.body}')

    return HttpResponse()
