import logging
import datetime

from khayyam import JalaliDatetime, JalaliDate
from persian import convert_en_numbers
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, error

from django.db import transaction
from django.shortcuts import reverse
from django.conf import settings
from django.core.cache import caches
from django.utils import timezone
from django.template import Template, Context
from django.forms.models import model_to_dict

from . import texts
from . import buttons
from apps.telegram_bot.tasks import render_campaign
from apps.push.models import CampaignPush, CampaignPushUser
from apps.telegram_user.models import TelegramUser
from apps.utils.url_encoder import UrlEncoder
from apps.telegram_adv.models import (
    TelegramChannel,
    TelegramAgent,
    Campaign,
    CampaignUser,
    CampaignPost,
    CampaignContent
)

logger = logging.getLogger(__name__)


# new functions after redesign
def refresh_session(bot, update, session=None, clear=False):
    session_cache = caches['session']
    if update.effective_user is None:
        logger.debug(f"no effective_user, update from channel: {update.channel_post.chat.title}.")
        return

    user_info = update.effective_user
    ck = f'telegram_user_session_{user_info.id}'

    if clear:
        session_cache.delete(ck)

    if session is not None:
        session_cache.set(ck, session)
        return session

    _session = session_cache.get(ck)
    if _session is None:
        user, created = TelegramUser.objects.get_or_create(
            user_id=user_info.id,
            defaults=dict(
                first_name=user_info.first_name or '',
                last_name=user_info.last_name or '',
                username=user_info.username or ''
            )
        )
        if created or update.effective_message.text == '/start':
            token = settings.TELEGRAM_BOT.get('TOKEN')
            # TODO: log if agent does not exist
            agent = TelegramAgent.objects.get(bot_token=token)
            user.agents.add(agent)

        if not user.is_valid:
            return False

        user_to_dict = model_to_dict(user,
                                     fields=['id', 'user_id', 'first_name', 'username', 'is_valid', 'sticker'])
        _session = {'user': user_to_dict, 'selected_channels': {}}
        session_cache.set(ck, _session)

    return _session


def start_menu(bot, update, session):
    session.pop('state', None)
    try:
        bot.delete_message(update.effective_user.id, update.callback_query.message.message_id)
    except error.BadRequest:
        # No callback_query message to delete
        pass

    bot.send_message(update.effective_user.id,
                     texts.START % update.effective_user.first_name,
                     reply_markup=buttons.start_buttons())


def get_channel_info(bot, update, channel_tag, session):
    channel = TelegramChannel.objects.prefetch_related(
        'admins'
    ).select_related(
        'sheba'
    ).filter(
        tag=channel_tag,
        channel_id__lt=0
    ).first()
    if channel is None:
        try:
            channel = bot.getChat(channel_tag)
            channel_member = bot.getChatMembersCount(channel_tag)
            channel_id = channel.id
            channel_title = channel.title
            session['add_channel'] = {
                'tag': channel_tag,
                'title': channel_title,
                'channel_id': channel_id,
                'member_no': channel_member,
            }
            refresh_session(bot, update, session)
            t = Template(texts.ADD_CHANNEL_INFO)
            c = Context(dict(id=channel_tag, title=channel_title, members=channel_member))
            message = t.render(c)
            update.message.reply_text(message, reply_markup=buttons.confirm_button())
            # session['get_text'] = True

        except error.BadRequest:
            update.message.reply_text(texts.ADD_CHANNEL_NOT_FOUND)

        except Exception as e:
            logger.error(f"getting channel info for: {channel_tag} got error: {e}")
            update.message.reply_text(texts.ADD_CHANNEL_ERROR)
        return

    elif update.effective_user.id in channel.admins.values_list('user_id', flat=True):
        update.message.reply_text(texts.ADD_CHANNEL_ALREADY_EXIST, reply_markup=buttons.start_buttons())

    else:
        sheba = channel.sheba.sheba_number
        t = Template(texts.ADD_CHANNEL_EXIST)
        c = Context(dict(tag=channel.tag,
                         title=channel.title,
                         sheba=f"{sheba[:4]}XXXX{sheba[-2:]}"))
        session['channel_exists'] = channel.id
        update.message.reply_text(t.render(c), reply_markup=buttons.exists_channel())

    refresh_session(bot, update, session)


def channel_list(update, session):
    """
    Show all active advs for a specific user
    """
    counter = 0
    message = "لیست کانال های %s\n\n" % update.effective_user.first_name
    channels = TelegramChannel.objects.select_related(
        'sheba'
    ).filter(
        admins__user_id=update.effective_user.id
    ).order_by(
        '-created_time'
    )
    if channels:
        for channel in channels:
            sheba = channel.sheba.sheba_number
            t = Template(texts.CHANNEL_INFO_LIST)
            c = Context(dict(title=channel.title,
                             tag=channel.tag,
                             sheba_no=f"{sheba[:6]}xxxxx{sheba[-4:]}",
                             sheba_owner=channel.sheba.sheba_owner
                             ))
            message += t.render(c)
            counter += 1
            if counter % 10 == 0:
                update.message.reply_text(message, reply_markup=buttons.start_buttons())
                message = "لیست کانال های %s\n\n" % update.effective_user.first_name

        if counter % 10 < 10:
            update.message.reply_text(message, reply_markup=buttons.start_buttons())
    else:
        update.message.reply_text(texts.NO_CHANNEL, reply_markup=buttons.start_buttons())


def ended_campaigns(bot, update):
    """
        Which campaigns should demonstrate to user for screen shot
    """
    campaigns = list(
        Campaign.objects.filter(
            id__in=CampaignUser.objects.filter(
                user__user_id=update.effective_user.id,
                channels__isnull=False,
                campaignpost__campaign_content__view_type=CampaignContent.TYPE_VIEW_PARTIAL,
                campaignpost__screen_shot__exact='',
                campaign__status__in=[Campaign.STATUS_APPROVED, Campaign.STATUS_CLOSE]
            ).values_list('campaign_id', flat=True),
            start_datetime__lte=timezone.now() - timezone.timedelta(hours=settings.SEND_SHOT_START_HOUR),
            end_datetime__gte=timezone.now() - timezone.timedelta(hours=settings.SEND_SHOT_END_HOUR)
        )
    )

    if campaigns:
        _buttons = [
            [InlineKeyboardButton(f"{campaign.text_display()}", callback_data=f'cmp_{campaign.id}')]
            for campaign in campaigns
        ]
        _buttons.extend([[InlineKeyboardButton("بازگشت ◀️", callback_data="back")]])
        context = dict(text=texts.SEND_SHOT, reply_markup=InlineKeyboardMarkup(_buttons))
    else:
        context = dict(text=texts.SEND_SHOT_NOT_ADV, reply_markup=buttons.start_buttons())

    if update.callback_query:
        bot.delete_message(update.effective_user.id, update.callback_query.message.message_id)
        bot.send_message(update.effective_user.id, **context)
    else:
        update.message.reply_text(**context)


def render_campaign_user(bot, update, session):
    """
    Depends on selected adv, which campaign user objects should send
    """
    try:
        campaign_id = int(update.callback_query.data.split('_')[1])
    except:
        campaign_id = session['campaign_id_back']

    campaign = Campaign.objects.get(id=campaign_id)

    campaign_users = list(CampaignUser.objects.filter(
        campaign_id=campaign_id,
        channels__isnull=False,
        user__user_id=update.effective_user.id,
        campaignpost__screen_shot__exact='',
        campaignpost__campaign_content__view_type=CampaignContent.TYPE_VIEW_PARTIAL
    ).distinct())

    session['campaign_id_back'] = campaign_id
    refresh_session(bot, update, session)

    if campaign_users:
        campaign_user_list = [
            [InlineKeyboardButton(text=", ".join(cmp.channels.values_list('tag', flat=True)),
                                  callback_data=f'ucmp_{cmp.id}')]
            for cmp in campaign_users
        ]

        campaign_user_list.append([InlineKeyboardButton("بازگشت ◀️", callback_data="back_to_campaign")])

        update.callback_query.edit_message_text(
            text=texts.SEND_SHOT_RENDER_ADVC_CHOICE % campaign.text_display(),
            reply_markup=InlineKeyboardMarkup(campaign_user_list),
            parse_mode="Markdown"
        )

    else:
        update.callback_query.edit_message_text(text=texts.SEND_SHOT_RENDER_CPU_ERROR)


def render_campaign_posts(bot, update, session):
    try:
        campaign_user_id = int(update.callback_query.data.split('_')[1])
    except:
        campaign_user_id = session['back_to_campaign_user']

    campaign_posts = list(CampaignPost.objects.select_related('campaign_content').filter(
        campaign_user_id=campaign_user_id,
        screen_shot__exact='',
        campaign_content__view_type=CampaignContent.TYPE_VIEW_PARTIAL
    ))

    session['back_to_campaign_user'] = campaign_user_id
    refresh_session(bot, update, session)

    campaign_user_list = [
        [InlineKeyboardButton(text=cmp_post.campaign_content.display_text, callback_data=f'pcmp_{cmp_post.id}')]
        for cmp_post in campaign_posts
    ]
    campaign_user_list.append([InlineKeyboardButton("بازگشت ◀️", callback_data="back_to_campaign_user")])

    # if campaign has just one content skip choosing campaign_post got to receive screen_shot
    if len(campaign_posts) == 1:
        shot_campaign_post(update, session, campaign_posts[0].id)

    else:
        update.callback_query.edit_message_text(text=texts.SEND_SHOT_RENDER_BANNER_CHOICE,
                                                reply_markup=InlineKeyboardMarkup(campaign_user_list))


def shot_campaign_post(update, session, campaign_post_id):
    session['shot'] = campaign_post_id
    update.callback_query.edit_message_text(
        text=texts.SEND_SHOT_INPUT,
        reply_markup=buttons.back_button("back_to_campaign_user")
    )


def check_campaign_shot_time(campaign):
    campaign_start_time = datetime.datetime.combine(campaign.approve_date, campaign.time_slicing.start_time)
    start_time = campaign_start_time + campaign.time_slicing.show_duration
    end_time = campaign_start_time + datetime.timedelta(days=1) + campaign.time_slicing.view_duration

    return start_time < datetime.datetime.now() < end_time


def active_campaigns(update):
    """
    show all active campaigns for a specific user
    """
    user_active_campaigns = list(Campaign.objects.filter(
        status=Campaign.STATUS_APPROVED,
        campaignuser__user__user_id=update.effective_user.id,
    ).distinct())

    if user_active_campaigns:
        context = dict(
            text=texts.ACTIVE_ADVS,
            reply_markup=buttons.active_campaigns(user_active_campaigns, back_data="back")
        )
    else:
        context = dict(
            text=texts.NO_ACTIVE_ADVS,
            reply_markup=buttons.start_buttons()
        )

    if update.message:
        update.message.reply_text(**context)
    else:
        update.callback_query.message.edit_text(**context)


def render_active_user_campaigns(update, campaign_id):
    user_active_user_campaigns = list(CampaignUser.objects.prefetch_related(
        'channels'
    ).filter(
        campaign_id=campaign_id,
        user__user_id=update.effective_user.id,
    ).distinct())

    update.callback_query.message.edit_text(
        texts.ACTIVE_ADV_CONTROLS,
        reply_markup=buttons.active_campaign_user(user_active_user_campaigns, campaign_id)
    )


def user_campaign_detail(update, campaign_user_id, campaign_id):
    user_campaign = CampaignUser.objects.select_related(
        'campaign'
    ).get(
        id=campaign_user_id
    )

    channels = "\n".join(f"{ch} ✅" for ch in user_campaign.channels.values_list('tag', flat=True))
    t = Template(texts.ACTIVE_AD)
    c = Context(dict(title=user_campaign.campaign.text_display(),
                     channels=channels))
    message = t.render(c)
    update.callback_query.message.edit_text(
        text=message,
        reply_markup=buttons.back_button(f"back_to_campaign_users_{campaign_id}")
    )


def financial_detail(update):
    user_id = update.effective_user.id
    user_campaigns = list(CampaignUser.objects.select_related(
        'campaign'
    ).prefetch_related(
        'campaignpost_set',
        'campaignpost_set__campaign_content'
    ).filter(
        user__user_id=user_id,
        receipt_price__isnull=False,
    ).order_by('-pk')[:4])

    report = "آخرین گزارشات مالی شما به شرح زیر است: \n\n"
    if user_campaigns:
        for user_campaign in user_campaigns:
            context = dict(date=JalaliDatetime(user_campaign.created_time).strftime('%C'),
                           title=user_campaign.campaign.text_display(),
                           channels=user_campaign.channel_tags,
                           paid=user_campaign.receipt_date is not None)
            banners_info = ""
            for post in user_campaign.campaignpost_set.all():
                views = convert_en_numbers(getattr(post, "views", "-"))
                banners_info.join(f"\n{post.campaign_content.display_text} - بازدید:  {views}\n")
            context.update(banners_info=banners_info)

            if user_campaign.receipt_code:
                price_date = JalaliDate(user_campaign.receipt_date).strftime('%x')
                context.update(dict(price=convert_en_numbers(f'{user_campaign.receipt_price:,}'),
                                    price_date=price_date,
                                    price_code=user_campaign.receipt_code))

            report += Template(texts.FINANCIAL).render(Context(context))

        path = reverse('publisher-report', args=[UrlEncoder().encode_id(user_id)])
        update.message.reply_text(
            text=report,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(text="گزارش کامل", url=f"{settings.BASE_REPORT_URL}{path}")]]
            )
        )

    else:
        update.message.reply_text(texts.FINANCIAL_NOTHING, reply_markup=buttons.start_buttons())


def assign_sheba_to_channel(bot, update, session):
    user = session['user']
    sheba_obj = session.pop('sheba_obj', None)
    channel_info = session.pop('add_channel', None)
    channel_id = channel_info.pop('channel_id', None)

    if not sheba_obj.pk:
        sheba_obj.save()
    channel_info['sheba_id'] = sheba_obj.id

    channel, _c = TelegramChannel.objects.update_or_create(
        channel_id=channel_id,
        defaults=channel_info
    )
    channel.admins.add(user['id'])

    bot.delete_message(
        chat_id=update.effective_user.id,
        message_id=update.callback_query.message.message_id
    )
    # delete message to send a new message with Keyboard markup instead of InlineKeyboard
    bot.send_message(
        chat_id=update.effective_user.id,
        text=texts.SEND_SHEBA_OWNER_SUCCESS,
        reply_markup=buttons.start_buttons()
    )


def remove_channel_check(update, channel_tag, session):
    channel = TelegramChannel.objects.filter(
        admins__user_id=update.effective_user.id,
        tag=channel_tag
    ).first()
    if channel:
        session['remove_channel'] = channel.id
        t = Template(texts.REMOVE_CHANNEL_INFO)
        c = Context(dict(tag=channel.tag, title=channel.title, members=channel.member_no))
        update.message.reply_text(t.render(c), reply_markup=buttons.confirm_button())

    else:
        update.message.reply_text(texts.REMOVE_CHANNEL_NOT_EXISTS)


def remove_user_from_channel(update, session):
    user = session['user']
    channel_id = session.pop('remove_channel', None)
    channel = TelegramChannel.objects.get(id=channel_id)
    channel.user.remove(user['id'])
    text = texts.REMOVE_CHANNEL_SUCCESS
    update.callback_query.message.edit_text(text)


# new functions

def select_campaign_push_to_send(update, bot, campaign_push_user_id, user_id, selected_channels):
    """
        try to send a campaign to user in transaction atomic to avoid of conflicts
        if two admin click on get campaign in same time just one of them should get banner.
        and for other get and warning answer and inline will update in their chats
    """
    campaign_push_user = CampaignPushUser.objects.get(pk=campaign_push_user_id)
    with transaction.atomic():
        selected_channels_ids = [ch['id'] for ch in selected_channels]
        campaign_push = CampaignPush.objects.select_for_update().prefetch_related(
            'publishers',
            'campaign__contents__files',
            'campaign__contents__links',
            'campaign__contents__inlines',
            'users'
        ).select_related(
            'campaign'
        ).get(
            pk=campaign_push_user.campaign_push_id
        )

        # check for concurrency conflict
        campaign_user = CampaignUser.objects.select_related(
            'user'
        ).filter(
            campaign_id=campaign_push.campaign_id,
            channels__id__in=selected_channels_ids
        ).first()
        if campaign_user:
            bot.answer_callback_query(
                update.callback_query.id,
                texts.GOT_BEFORE.format(campaign_user.user.full_name)
            )

        else:
            bot.delete_message(
                update.effective_user.id,
                update.callback_query.message.message_id
            )
            tariff = selected_channels[0]['tariff']
            try:
                render_campaign(campaign_push_user, user_id, selected_channels_ids, tariff)
            except Exception as e:
                logger.error(f"render campaign: {campaign_push.campaign_id} for :{user_id} failed, error: {e}")

        # update inline messages in other admins chat expect this user
        update_push_inlines(bot, campaign_push_user, user_id)


def update_push_inlines(bot, campaign_push_user, excluded_user_id):
    """
        update inline of push in admins chats
        if has any other channels to select edit reply_markup
        else delete all messages from all admins chats

    :param bot:
    :param campaign_push_user:
    :param excluded_user_id:
    :return:
    """
    campaign_push = campaign_push_user.campaign_push

    if campaign_push_user.has_push_data():
        reply_markup = buttons.campaign_push_reply_markup(
            campaign_push_user,
        )
        method = bot.edit_message_reply_markup
    else:
        reply_markup = None
        method = bot.delete_message

    for user_push in campaign_push.user_pushes.exclude(user__user_id=excluded_user_id):
        try:
            method(
                chat_id=user_push.user.user_id,
                message_id=user_push.message_id,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"change in user: {user_push.user.user_id} failed, error: {e}")
