import logging

from telegram.ext.dispatcher import run_async

from django.utils.translation import ugettext as _
from django.core.exceptions import ValidationError

from apps.push.models import CampaignPush
from apps.telegram_adv.models import TelegramChannel, BankAccount
from apps.telegram_user.models import TelegramUser
from apps.push.tasks import cancel_push
from .tasks import receive_shot, render_campaign
from .decorators import add_session
from . import functions, buttons, texts

logger = logging.getLogger(__name__)


@run_async
@add_session(clear=True)
def start(bot, update, session):
    bot.send_message(
        chat_id=update.effective_user.id,
        text=texts.START % update.effective_user.first_name,
        reply_markup=buttons.start_buttons()
    )


@run_async
@add_session(clear=True)
def stop(bot, update, session):
    bot.send_message(
        chat_id=update.effective_user.id,
        text=texts.CANCEL
    )


@run_async
@add_session
def dispatcher(bot, update, session):
    user = session.get('user')

    text = update.message.text
    if text == _('add channel'):
        session['state'] = 'add_channel'
        update.message.reply_text(texts.ADD_CHANNEL, reply_markup=buttons.back_button("back"))

    elif text == _('send sticker'):
        session['state'] = 'get_sticker'
        bot.send_sticker(update.effective_user.id, sticker=user['sticker'])
        update.message.reply_text(texts.SEND_STICKER, reply_markup=buttons.cancel_button())

    elif text == _('finish shot'):
        session['state'] = 'get_shot'
        functions.ended_campaigns(bot, update)

    elif text == _('/fghij'):
        session['state'] = 'get_file_id'
        update.message.reply_text(texts.FILE_ID)

    elif text == _('remove channel'):
        session['state'] = 'remove_channel'
        update.message.reply_text(texts.REMOVE_CHANNEL, reply_markup=buttons.back_button("back"))

    elif text == _('active ad'):
        session['state'] = 'active_ad'
        functions.active_campaigns(update)

    elif text == _('report financial'):
        session.pop('state', None)
        functions.financial_detail(update)

    elif text == _('channel list'):
        session.pop('state', None)
        functions.channel_list(update, session)

    elif text == _('help'):
        session.pop('state', None)
        update.message.reply_text(texts.HELP, reply_markup=buttons.start_buttons())

    elif text == _('about_us'):
        session.pop('state', None)
        update.message.reply_text(texts.ABOUT_US, reply_markup=buttons.start_buttons())

    else:
        call_state_function(bot, update)
        return

    functions.refresh_session(bot, update, session)


@run_async
@add_session
def call_state_function(bot, update, session):
    state = session.get('state')
    try:
        eval(state)(bot, update)
    except Exception:
        session.pop('state', None)  # refresh user state
        bot.send_message(chat_id=update.effective_user.id,
                         text=texts.WRONG_KEYBOARD,
                         reply_markup=buttons.start_buttons())


@run_async
@add_session
def push_campaign_management(bot, update, session):
    """
        detect selected channel and save push data separately for each push object
    """
    if update.callback_query:
        data = update.callback_query.data
        selected_channels = session['selected_channels']

        if data.startswith('push_campaign_get'):
            _p, _c, _g, campaign_push_id = data.split('_')
            selected_channels = session['selected_channels'].get(campaign_push_id)
            if not selected_channels:
                bot.answer_callback_query(
                    update.callback_query.id,
                    texts.GET_ADV_NO_CHANNEL_ERROR
                )

            else:
                _p, _c, _g, campaign_push_id = data.split('_')
                session[f'push_data_{campaign_push_id}'] = []
                functions.select_campaign_push_to_send(
                    update,
                    bot,
                    campaign_push_id,
                    update.effective_user.id,
                    session['selected_channels'][campaign_push_id]
                )
                session['selected_channels'][campaign_push_id] = []

        elif data.startswith('push_campaign_cancel'):
            _p, _ch, _c, campaign_push_id = data.split('_')
            selected_channels = session['selected_channels'].get(campaign_push_id, None)
            if selected_channels:
                session['selected_channels'][campaign_push_id] = []
            session[f'push_data_{campaign_push_id}'] = []
            cancel_push(campaign_pushes=campaign_push_id)

        elif data.startswith('push_campaign_sheba'):
            bot.answer_callback_query(
                update.callback_query.id,
                texts.SHEBA_CLICKED
            )

        # check clicked channel to add or not, not if sheba or tariff is not match
        else:
            _p, campaign_push_id, channel_id, tariff = data.split('_')
            selected_channels = selected_channels.setdefault(campaign_push_id, [])
            session[f'push_data_{campaign_push_id}'] = CampaignPush.objects.get(id=campaign_push_id).get_push_data()
            push_data = session[f'push_data_{campaign_push_id}']
            channel_id = int(channel_id)
            if not selected_channels:
                selected_channels.append({'id': channel_id, 'tariff': tariff})

            elif channel_id in map(lambda ch: ch['id'], selected_channels):
                for i, channel in enumerate(selected_channels):
                    if channel['id'] == channel_id:
                        selected_channels.pop(i)
                        break

            elif BankAccount.objects.filter(
                    channels__in=(channel_id, selected_channels[0]['id'])
            ).distinct().count() > 1:
                return bot.answer_callback_query(
                    update.callback_query.id,
                    texts.SHEBA_NOT_SAME
                )

            elif tariff not in map(lambda ch: ch['tariff'], selected_channels):
                return bot.answer_callback_query(
                    update.callback_query.id,
                    texts.TARIFF_NOT_SAME
                )

            else:
                selected_channels.append({'id': channel_id, 'tariff': tariff})

            update.callback_query.edit_message_reply_markup(
                reply_markup=buttons.campaign_push_reply_markup(
                    campaign_push_id,
                    push_data,
                    selected_channels
                )
            )

    functions.refresh_session(bot, update, session)


@run_async
@add_session
def active_ad(bot, update, session):
    if update.callback_query:
        data = update.callback_query.data
        if data == "back":
            functions.start_menu(bot, update, session)

        elif data.startswith('cmp'):
            data = data.split('_')[1]
            functions.render_active_user_campaigns(update, data)

        # id of CampaignUser object
        elif data.startswith('ucmp'):
            _, campaign_user_id, campaign_id = data.split('_')
            functions.user_campaign_detail(update, campaign_user_id, campaign_id)

        # back to all active campaigns
        elif data == "back_to_active_adv":
            functions.active_campaigns(update)

        # back to CampaignUser of a specific campaign
        elif data.startswith("back_to_campaign_users"):
            data = data.split('_')[-1]
            functions.render_active_user_campaigns(update, data)


@run_async
@add_session
def add_channel(bot, update, session):
    user = session['user']
    if update.callback_query:
        data = update.callback_query.data
        if data == 'yes':
            session['state'] = 'get_sheba'
            update.callback_query.message.edit_text("کانال شما با موفقت تبت شد. ✅" + texts.SEND_SHEBA)

        elif data == 'add':
            channel_id = session.pop('channel_exists')
            channel = TelegramChannel.objects.get(id=channel_id)
            channel.admins.add(user['id'])
            update.callback_query.message.edit_text(texts.ADD_CHANNEL_SUCCESS)

        elif data == 'no':
            session.pop('add_channel', None)
            session.pop('get_text', None)
            update.callback_query.message.edit_text(texts.ADD_CHANNEL)

        elif data == 'stop' or data == 'back':
            session.pop('add_channel', None)
            functions.start_menu(bot, update, session)

    elif update.message:
        text = update.message.text
        if update.message.text.startswith('@'):
            functions.get_channel_info(bot, update, text.lower(), session)
        else:
            update.message.reply_text(texts.ADD_CHANNEL_FAILED)

    functions.refresh_session(bot, update, session)


@run_async
@add_session
def remove_channel(bot, update, session):
    if update.callback_query:
        data = update.callback_query.data
        if data == 'yes':
            functions.remove_user_from_channel(update, session)

        elif data == 'no':
            bot.delete_message(update.effective_user.id, update.callback_query.message.message_id)
            bot.send_message(update.effective_user.id,
                             text=texts.REMOVE_CHANNEL_CANCEL,
                             reply_markup=buttons.start_buttons())

        elif data == "back":
            functions.start_menu(bot, update, session)

    else:
        text = update.message.text
        if text.startswith('@'):
            functions.remove_channel_check(update, text, session)
        else:
            update.message.reply_text(texts.REMOVE_CHANNEL_ERROR)

    functions.refresh_session(bot, update, session)


@run_async
@add_session
def get_sticker(bot, update, session):
    if update.callback_query:
        data = update.callback_query.data
        if data == "cancel":
            functions.start_menu(bot, update, session)

    else:
        if update.message.sticker:
            sticker_file_id = update.message.sticker.file_id
            user = session['user']
            user['sticker'] = sticker_file_id
            TelegramUser.objects.filter(
                user_id=update.effective_user.id
            ).update(sticker=sticker_file_id)
            update.message.reply_text(texts.SEND_STICKER_SUCCESS, reply_markup=buttons.start_buttons())

        else:
            update.message.reply_text(texts.SEND_STICKER_ERROR, reply_markup=buttons.start_buttons())

    functions.refresh_session(bot, update, session)


@run_async
@add_session
def get_sheba(bot, update, session):
    if update.callback_query:
        data = update.callback_query.data
        if data == 'yes':
            functions.assign_sheba_to_channel(bot, update, session)

        elif data == 'edit':
            update.callback_query.message.edit_text(texts.SEND_SHEBA)

        elif data == 'cancel':
            bot.delete_message(
                update.effective_user.id,
                update.callback_query.message.message_id
            )
            bot.send_message(
                update.effective_user.id,
                texts.SEND_SHEBA_CANCEL,
                reply_markup=buttons.start_buttons()
            )

        elif data == "back":
            functions.start_menu(bot, update, session)

        elif data.isdigit():
            channel = TelegramChannel.objects.filter(
                id=data
            ).values(
                'tag',
                'channel_id'
            ).first()
            session['add_channel'] = channel
            update.callback_query.message.edit_text(texts.SEND_SHEBA)

        else:
            bot.send_message(update.effective_user.id, texts.ERROR, reply_markup=buttons.start_buttons())

    else:
        text = update.message.text
        if text.startswith('IR'):
            bank_account = BankAccount.objects.filter(sheba_number=text).first()
            if bank_account:
                session['sheba_obj'] = bank_account
                msg = texts.SEND_SHEBA_CONFIRM % (bank_account.sheba_number, bank_account.sheba_owner)
                update.message.reply_text(msg, reply_markup=buttons.sheba_button())
            else:
                bank_account = BankAccount(sheba_number=text)
                try:
                    bank_account.clean_fields(exclude=['sheba_owner'])
                except ValidationError:
                    update.message.reply_text(texts.SEND_SHEBA_ERROR)
                else:
                    session['got_sheba_number'] = True
                    session['sheba_obj'] = bank_account
                    update.message.reply_text(texts.SEND_SHEBA_SUCCESS)

        else:
            session.pop('got_sheba_number', None)
            sheba_number = session['sheba_obj'].sheba_number
            session['sheba_obj'].sheba_owner = text
            update.message.reply_text(
                texts.SEND_SHEBA_CONFIRM % (sheba_number, text),
                reply_markup=buttons.sheba_button()
            )

    functions.refresh_session(bot, update, session)


@run_async
@add_session
def get_shot(bot, update, session):
    if update.callback_query:
        data = update.callback_query.data
        if data == "back":
            functions.start_menu(bot, update, session)

        elif data == "back_to_campaign":
            functions.ended_campaigns(bot, update)

        elif data.startswith('cmp') or data == "back_to_campaign_user":
            functions.render_campaign_user(bot, update, session)

        elif data.startswith('ucmp') or data == "back_to_campaign_post":
            functions.render_campaign_posts(bot, update, session)

        # get shot for that post
        elif data.startswith('pcmp'):
            campaign_post_id = data.split('_')[1]
            functions.shot_campaign_post(update, session, campaign_post_id)

    elif update.message.photo:
        if session.get('shot') is None:
            update.message.reply_text(texts.SEND_SHOT_CHOSE_BANNER)
            return

        photo_id = update.message.photo[-1].file_id
        receive_shot.delay(update.effective_user.id, photo_id, session.get('shot'))

    else:
        bot.send_message(update.effective_user.id, texts.SEND_SHOT_BAD_INPUT)

    functions.refresh_session(bot, update, session)


@run_async
def get_file_id(bot, update):
    message = update.message
    msg = "file_type: %s\nfile_id:\n\n⬇️⬇️⬇️⬇️⬇️\n\n%s\n\n⬆️⬆️⬆️⬆️⬆️"

    if message.photo:
        msg = msg % ("photo 🌁", message.photo[-1].file_id)
    elif message.video:
        msg = msg % ("video ", message.video.file_id)
    elif message.audio:
        msg = msg % ("audio ", message.audio.file_id)
    elif message.voice:
        msg = msg % ("audio 🎵", message.voice.file_id)
    elif message.document:
        msg = msg % ("document 📂", message.document.file_id)
    elif message.sticker:
        msg = msg % ("sticker ", message.sticker.file_id)
    else:
        msg = "لطفا فایل خود را آپلود یا forward کنید."

    update.message.reply_text(msg)


@run_async
def error_handler(bot, update, telegram_error):
    logger.error(f'Update {update} caused error {telegram_error}')
