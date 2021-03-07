import requests
import logging
from time import sleep

from django.conf import settings
from django.utils import timezone
from django.template import Template, Context
from django.db import transaction

from celery import shared_task
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.errors import FloodWaitError
from telethon.utils import pack_bot_file_id

from telegram import Bot, ParseMode, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.utils.request import Request

from . import texts, buttons
from apps.utils.url_encoder import UrlEncoder
from apps.utils.html import filter_escape
from apps.telegram_bot.exceptions import ShortLinkError
from apps.push.models import PushText, CampaignPush
from apps.push.tasks import send_push_to_user
from apps.tel_tools.models import TelegramSession
from apps.telegram_adv.models import (
    Campaign,
    CampaignPost,
    CampaignUser,
    CampaignContent,
    CampaignFile,
    CampaignPostLog,
    ShortLink,
    ShortLinkLog,
    TelegramChannel,
    TelegramAgent,
    ReceiverChannel
)

logger = logging.getLogger(__name__)

TELETHON_PROXY = None
if settings.PROXY4TELEGRAM_HOST:
    # import os
    import socks

    TELETHON_PROXY = (
        socks.HTTP,
        settings.PROXY4TELEGRAM_HOST,
        settings.PROXY4TELEGRAM_PORT,
        # True,
        # settings.PROXY4TELEGRAM_USER,
        # settings.PROXY4TELEGRAM_PASS,
    )
    # PROXY4TELEGRAM = f'http://{settings.PROXY4TELEGRAM_HOST}:{settings.PROXY4TELEGRAM_PORT}'
    # os.environ['http_proxy'] = PROXY4TELEGRAM
    # os.environ['https_proxy'] = PROXY4TELEGRAM

bot_settings = settings.TELEGRAM_BOT
proxy_url = None
if bot_settings.get('PROXY'):
    proxy_url = bot_settings['PROXY']

# agent bot
agent = Bot(
    token=bot_settings.get('TOKEN'),
    request=Request(con_pool_size=4, connect_timeout=3.05, read_timeout=27, proxy_url=proxy_url)
)

# creator bot
bot = Bot(
    token=settings.CREATOR_BOT_TOKEN,
    request=Request(con_pool_size=4, connect_timeout=3.05, read_timeout=27, proxy_url=proxy_url)
)


def _get_telegram_admin_user():
    # TODO: change this and get by admin type: view, fraud, ....
    return TelegramSession.objects.first()


@shared_task
def upload_file(obj_id, push=False):
    if push:
        model = PushText
        model_file = PushText.objects.get(id=obj_id)
        file = model_file.image
        file_type = CampaignFile.TYPE_PHOTO

    else:
        model = CampaignFile
        model_file = CampaignFile.objects.get(id=obj_id)
        file = model_file.file
        file_type = model_file.file_type

    context = dict(chat_id=settings.BOT_VIEW_CHANNEL_ID)
    if file_type == CampaignFile.TYPE_PHOTO:
        method = bot.send_photo
        context.update(dict(photo=file))

    elif file_type == CampaignFile.TYPE_VIDEO:
        method = bot.send_video
        context.update(dict(video=file))

    elif file_type == CampaignFile.TYPE_AUDIO:
        method = bot.send_audio
        context.update(dict(audio=file))

    else:
        method = bot.send_document
        context.update(dict(document=file))

    try:
        bot_response = method(**context, timeout=1000)
        file_id = grab_file_id(bot_response, file_type)
        model.objects.filter(id=obj_id).update(telegram_file_hash=file_id)
    except Exception as e:
        logger.error(f"upload {model_file}: {obj_id} failed, error: {e}")


@shared_task
def get_files_id(campaign_content_id, channel_id, admin_id, file_type, from_msg_id, to_msg_id):
    campaign_content = CampaignContent.objects.get(id=campaign_content_id)
    channel = ReceiverChannel.objects.get(id=channel_id)
    admin = TelegramSession.objects.get(id=admin_id)

    campaign_files = []

    with TelegramClient(StringSession(admin.session), admin.api_id, admin.api_hash, proxy=TELETHON_PROXY) as client:
        client.session.save_entities = False
        client.flood_sleep_threshold = 0
        messages = client.iter_messages(channel.chat_id, min_id=max(from_msg_id-1, 1), max_id=to_msg_id+1)
        for message in messages:
            try:
                file_id = pack_bot_file_id(message.media)
                if not CampaignFile.objects.filter(campaign_content=campaign_content, telegram_file_hash=file_id).exists():
                    campaign_files.append(
                        CampaignFile(
                            name=f"{campaign_content.display_text} {file_type} {message.id}",
                            telegram_file_hash=file_id,
                            file_type=file_type,
                            campaign_content=campaign_content
                        )
                    )
            except FloodWaitError as e:
                sleep(e.seconds)
            except Exception as e:
                logger.error(
                    f"import file for CampaignContent: {campaign_content_id} message: {message} failed, error: {e}"
                )
                break
        admin.session = client.session.save()
        admin.save()

    CampaignFile.objects.bulk_create(campaign_files)


def get_shortlink(campaign_link, campaign_title, campaign_user_id):
    for i in range(10):
        try:
            payload = {
                'title': campaign_title,
                'dest_url': campaign_link.link,
                'utm_source': campaign_link.extra_data.get("utm_source"),
                'utm_medium': campaign_link.extra_data.get("utm_medium"),
                'utm_campaign': campaign_link.extra_data.get("utm_campaign"),
                'utm_term': campaign_link.extra_data.get("utm_term"),
                'utm_content': campaign_link.extra_data.get("utm_content", campaign_user_id),
            }
            r = requests.post(f'{settings.ADMD_API_URL}',
                              json=payload,
                              headers={'Authorization': settings.ADMD_API_TOKEN})
            r.raise_for_status()
            result = r.json()
        except requests.HTTPError:
            logger.error(f'requests error: {r.status_code}, body: {r.text}, payload: {payload}')
        except Exception as e:
            logger.error(f'This exception occurred because of {e}')
        else:
            shortlink = ShortLink.objects.create(
                campaign_link=campaign_link,
                link=result['short_url'],
                reference_id=result['id'],
            )
            return shortlink


def valid_campaign_post_ids(no_shot=False):
    """
        return campaign post ids that should read their views and shortlink logs
        if no_shot:
            user can send screen shots until this time and after that if no shot sent
            campaign post screen shot will update to no_shot
        else:
            reading campaign_posts views and short_links logs

    :param no_shot:
    :return:
    """

    if no_shot:
        query = Campaign.objects.filter(
            is_enable=True,
            status__in=[Campaign.STATUS_CLOSE, Campaign.STATUS_APPROVED],
            end_datetime__lt=timezone.now() - timezone.timedelta(hours=settings.SEND_SHOT_END_HOUR),
            campaignuser__campaignpost__screen_shot__exact=''
        )
    else:
        query = Campaign.objects.filter(
            is_enable=True,
            status=Campaign.STATUS_APPROVED,
            end_datetime__gte=timezone.now()
        )

    return query.values_list('campaignuser__campaignpost__id', flat=True)


@shared_task
def read_campaign_posts_views(campaign_posts, log_mode=True, update_views=False):
    if all(isinstance(x, int) for x in campaign_posts):
        campaign_posts = CampaignPost.objects.filter(id__in=campaign_posts)

    telegram_log = []
    adm_ts = _get_telegram_admin_user()
    total_views = {}
    with TelegramClient(StringSession(adm_ts.session), adm_ts.api_id, adm_ts.api_hash, proxy=TELETHON_PROXY) as client:
        client.session.save_entities = False
        if not update_views:
            client.flood_sleep_threshold = 20
            client.request_retries = 2

        for campaign_post in campaign_posts:
            view_type = campaign_post.campaign_content.view_type
            view_id = campaign_post.campaign_content.id
            try:
                # Optimize telethon get_messages to reduce flood wait
                if view_type == CampaignContent.TYPE_VIEW_TOTAL and total_views.get(view_id) is not None:
                    banner_views = total_views[view_id]
                else:
                    banner_views = client.get_messages(
                        campaign_post.campaign_content.mother_channel.get_id_or_tag,
                        ids=campaign_post.message_id
                    ).views
                    if view_type == CampaignContent.TYPE_VIEW_TOTAL:
                        total_views[view_id] = banner_views

                campaign_post.views = banner_views
                if update_views:
                    campaign_post.save(update_fields=['updated_time', 'views'])

                if log_mode:
                    telegram_log.append(
                        CampaignPostLog(
                            campaign_post=campaign_post,
                            banner_views=banner_views,
                        )
                    )
                logger.info(f"read view for post: {campaign_post.id} and campaign: {campaign_post.campaign_content.campaign.id}")
            except FloodWaitError as e:
                logger.warning(f"read view for post: {campaign_post.id} and campaign: {campaign_post.campaign_content.campaign.id} failed, error: {e}")
            except Exception as e:
                logger.error(f"read view for post: {campaign_post.id} and campaign: {campaign_post.campaign_content.campaign.id} failed, error: {e}")

        adm_ts.session = client.session.save()
        adm_ts.save()

    if telegram_log:
        CampaignPostLog.objects.bulk_create(telegram_log)


@shared_task
def log_campaign_post_views():
    """
        read views for valid campaign post which their campaign is still open
    """
    campaign_posts = list(CampaignPost.objects.select_related(
        'campaign_content'
    ).filter(
        id__in=valid_campaign_post_ids(),
        views__isnull=True
    ).order_by('?'))
    if campaign_posts:
        read_campaign_posts_views(campaign_posts, log_mode=True, update_views=False)


@shared_task
def deactive_campaign():
    """
        check if timezone.now() passed the campaign end_datetime close campaign
        fill campaign_posts views
    """

    finished_campaigns = Campaign.objects.filter(
        end_datetime__lt=timezone.now(),
        status=Campaign.STATUS_APPROVED
    )

    campaign_posts = list(CampaignPost.objects.select_related(
        'campaign_content'
    ).filter(
        screen_shot='',
        views__isnull=True,
        campaign_user__campaign_id__in=finished_campaigns.values_list('id', flat=True),
    ))
    if campaign_posts:
        read_campaign_posts_views(campaign_posts, log_mode=False, update_views=True)

    finished_campaigns.update(
        status=Campaign.STATUS_CLOSE
    )


@shared_task
def check_no_shot_posts():
    with transaction.atomic():
        CampaignPost.objects.select_for_update().filter(
            id__in=valid_campaign_post_ids(no_shot=True)
        ).update(
            screen_shot='no_shot',
        )


@shared_task
def process_campaign_tasks():
    log_campaign_post_views.delay()
    log_short_links.delay()
    deactive_campaign.delay()
    check_no_shot_posts.delay()


@shared_task
def log_short_links():
    """
    read shortlink log if It's campaign status is approved or close
    and still need to read the logs

    :return:
    """
    short_links = ShortLink.objects.filter(
        campaign_post__id__in=valid_campaign_post_ids()
    )

    short_links_logs = []
    for short_link in short_links:
        try:
            r = requests.get(f'{settings.ADMD_API_URL}{short_link.reference_id}',
                             headers={'Authorization': settings.ADMD_API_TOKEN})

            r.raise_for_status()
            result = r.json()
        except requests.HTTPError:
            logger.error(f'requests error: {r.status_code}, body: {r.text}')
        except Exception as e:
            logger.error(f'This exception occurred because of {e}')
        else:
            short_links_logs.append(
                ShortLinkLog(
                    short_link=short_link,
                    hit_count=result['hit_count'],
                    ip_count=result['ip_count']
                )
            )
            logger.info(msg=f'Number of clicks for ({short_link.reference_id}) reference_id is {result["hit_count"]}')

    ShortLinkLog.objects.bulk_create(short_links_logs)


@shared_task
def receive_shot(telegram_user_id, file_id, campaign_post_id):
    """
    Receive shot for CampaignPost
    """
    try:
        with transaction.atomic():
            campaign_post = CampaignPost.objects.select_for_update().get(id=campaign_post_id)

            photo_file = agent.get_file(file_id, timeout=30)
            file_format = photo_file.file_path.split('.')[-1]
            file_path = f'shot_{campaign_post_id}.{file_format}'
            photo_file.download(custom_path=f"media/{file_path}", timeout=100)
            campaign_post.screen_shot = file_path
            campaign_post.screen_time = timezone.now()
            update_fields = ['updated_time', 'screen_shot', 'screen_time']
            if campaign_post.views is None:
                read_campaign_posts_views([campaign_post], log_mode=False, update_views=False)
                update_fields.append('views')

            campaign_post.save(update_fields=update_fields)

        agent.send_message(telegram_user_id, texts.SEND_SHOT_SUCCESS, reply_markup=buttons.back_button("back_to_campaign"))
    except Exception as e:
        logger.error(msg=f'receive shot failed, error: {e}')
        agent.send_message(telegram_user_id, texts.SEND_SHOT_ERROR, reply_markup=buttons.start_buttons())


@shared_task
def update_channels(channel_ids):
    channels = TelegramChannel.objects.filter(id__in=channel_ids, channel_id__isnull=False)

    adm_ts = _get_telegram_admin_user()
    with TelegramClient(StringSession(adm_ts.session), adm_ts.api_id, adm_ts.api_hash, proxy=TELETHON_PROXY) as client:
        client.session.save_entities = False
        client.flood_sleep_threshold = 0
        for channel in channels:
            try:
                channel_info = client(GetFullChannelRequest(channel.channel_id))
            except ValueError:
                channel_info = client(GetFullChannelRequest(channel.tag))
            except Exception as e:
                logger.error(f"updating channel info: {channel}, got error: {e} type: {type(e)}")
                break

            channel.title = channel_info.chats[0].title
            channel.tag = f"@{channel_info.chats[0].username}"
            channel.member_no = channel_info.full_chat.participants_count

            channel.save(update_fields=['updated_time', 'title', 'tag', 'member_no'])

        adm_ts.session = client.session.save()
        adm_ts.save()


def grab_file_id(telegram_message, file_type):
    """
    getting file_id due to the file type from message object.
    :param telegram_message:
    :param file_type:
    :return:
    """
    try:
        file = telegram_message[file_type]
        if file:
            if isinstance(file, list):
                file_id = file[-1].file_id
            else:
                file_id = file.file_id

            return file_id
    except Exception as e:
        logger.info(f"getting file_id got error: {e}")
        return None


def render_text_and_inline(campaign_content, campaign_user_id):
    """
        render the main text message of content and return short_links for campaign post
        * both content description and inline keyboards can have shortlink

    :param campaign_content:
    :param campaign_user_id:
    """
    short_link_ids = []
    inline_short_link_ids = []
    reply_markup = None

    content = campaign_content.content
    campaign_content_links = campaign_content.links.filter(
        inline__isnull=True
    ).distinct()

    for campaign_link in campaign_content_links:
        try:
            short_link = get_shortlink(campaign_link, campaign_content.campaign.title, campaign_user_id)
            short_link_ids.append(short_link.id)
        except Exception as e:
            logger.error(f"{e}")
            continue

        # change links in text
        content = content.replace(campaign_link.link, short_link.link)

    content_inlines = list(campaign_content.inlines.order_by('row'))
    if content_inlines:
        _buttons = []
        _short_link_ids = []
        last_row = -1
        for inline_keyboard in content_inlines:
            url = inline_keyboard.link
            campaign_link = getattr(inline_keyboard, "campaign_link", False)

            # if inline has campaign_link should get a new shortlink and change the default url
            if campaign_link:
                try:
                    short_link = get_shortlink(campaign_link, campaign_content.campaign.title, campaign_user_id)
                    url = short_link.link
                    _short_link_ids.append(short_link.id)
                except ShortLinkError:
                    continue

            if inline_keyboard.row != last_row:
                _buttons.append([])
                last_row = inline_keyboard.row
            _buttons[-1].append(InlineKeyboardButton(inline_keyboard.text, url=url))

        reply_markup = InlineKeyboardMarkup(_buttons)
        short_link_ids.extend(_short_link_ids)

    short_link_ids.extend(inline_short_link_ids)
    return content, reply_markup, short_link_ids


def get_campaign_content_file(campaign_content, campaign_content_files):
    created_campaign_content = CampaignPost.objects.filter(campaign_content=campaign_content).count()

    index = created_campaign_content % len(campaign_content_files)
    campaign_file = campaign_content_files[index]

    file = campaign_file.telegram_file_hash or campaign_file.file
    file_type = campaign_file.file_type

    return file, file_type, campaign_file


def initiate_context(campaign_content, mother_channel, text, reply_markup, user=None):
    """
    create campaign content for first time due to the file type
    :param campaign_content:
    :param mother_channel:
    :param text:
    :param reply_markup:
    :param user:
    :return:
    """
    campaign_file = None
    context = dict(chat_id=mother_channel,
                   caption=text,
                   parse_mode='HTML',
                   timeout=1000,
                   reply_markup=reply_markup)

    campaign_content_files = list(campaign_content.files.order_by('pk'))

    if campaign_content_files:
        file, file_type, campaign_file = get_campaign_content_file(campaign_content, campaign_content_files)

        if file_type == CampaignFile.TYPE_PHOTO:
            context.update(dict(method=bot.send_photo, photo=file))

        elif file_type == CampaignFile.TYPE_VIDEO:
            context.update(dict(method=bot.send_video, video=file))

        elif file_type == CampaignFile.TYPE_AUDIO:
            context.update(dict(method=bot.send_audio, audio=file))

        elif file_type == CampaignFile.TYPE_DOCUMENT:
            context.update(dict(method=bot.send_document, document=file))

    elif campaign_content.is_sticker:
        context.update(dict(method=bot.send_sticker, sticker=user.sticker))

    else:
        context.update(dict(method=bot.send_message, text=text))

    return context, campaign_file


def get_campaign_content_context(campaign_content, user, mother_channel, campaign_user_id):
    """
    generate a context of banner by its method to send caption or main text reply markups
    :param campaign_content:
    :param user:
    :param mother_channel:
    :param campaign_user_id:
    :return:
    """

    campaign_file = None
    text_raw, reply_markup, short_links_id = render_text_and_inline(campaign_content, campaign_user_id)
    text = filter_escape(text_raw)
    # we just need to update banner content due to short link valid is enable or not
    if campaign_content.view_type == CampaignContent.TYPE_VIEW_TOTAL and campaign_content.message_id:
        context = dict(message_id=campaign_content.message_id)

        # short link valid edit content by new links
        if short_links_id:
            context.update(
                dict(method=bot.edit_message_caption,
                     caption=text,
                     chat_id=mother_channel,
                     parse_mode=ParseMode.HTML,
                     reply_markup=reply_markup)
            )
        # no change needed just forward
        else:
            context.update(
                dict(method=bot.forward_message,
                     chat_id=user.user_id,
                     from_chat_id=mother_channel)
            )

    # create new banner due to it's type (text, photo, ... )
    else:
        context, campaign_file = initiate_context(campaign_content, mother_channel, text, reply_markup, user)

    return context, short_links_id, campaign_file


def render_campaign_content(campaign_content, user, mother_channel, campaign_user_id):
    """
    generate caption for specific content due to has short link, file or not
    :param campaign_content:
    :param user:
    :param mother_channel:
    :param campaign_user_id:
    :return:
    """

    context, short_links_ids, campaign_file = get_campaign_content_context(
        campaign_content,
        user,
        mother_channel,
        campaign_user_id
    )

    method = context.pop('method')
    if method == bot.forward_message:
        return campaign_content.message_id, short_links_ids, None

    bot_response = method(**context, disable_web_page_preview=True)
    banner_id = bot_response.message_id
    if campaign_file and not campaign_file.telegram_file_hash:
        campaign_file.telegram_file_hash = grab_file_id(bot_response, campaign_file.file_type)
        campaign_file.save(update_fields=['updated_time', 'telegram_file_hash'])

    return banner_id, short_links_ids, campaign_file


def create_system_message(campaign, channels_list):
    """
    create a message
    :param campaign:
    :param channels_list:
    :return:
    """
    url_encoder = UrlEncoder()
    code = url_encoder.encode_id(campaign.id)
    channel_tag_list = [c.tag for c in channels_list]
    c = Context(
        dict(title=campaign.text_get_ad(),
             code=f"#{code}", channels="\n".join(channel_tag_list))
    )
    t = Template(texts.GET_ADV_INFO)
    system_message = t.render(c)

    user_message = system_message + texts.USER_CONDITION

    if len(channels_list) > 1:
        user_message += texts.USER_CONDITION_MORE_THAN_ONE

    return system_message, user_message


@shared_task
def render_campaign(campaign_push, user_id, channels, tariff):
    user = campaign_push.users.get(user_id=user_id)
    campaign_contents = list(campaign_push.campaign.contents.order_by('id'))
    sheba = campaign_push.publishers.first().sheba
    agent_obj = TelegramAgent.objects.get(bot_token=settings.TELEGRAM_BOT.get('TOKEN'))
    campaign_user = CampaignUser.objects.create(
        sheba_number=sheba.sheba_number,
        sheba_owner=sheba.sheba_owner,
        user=user,
        campaign=campaign_push.campaign,
        agent=agent_obj,
        tariff=tariff
    )

    campaign_posts = []
    for campaign_content in campaign_contents:
        if campaign_content.post_link:
            agent.send_message(
                chat_id=user.user_id,
                text=texts.POST_LINK_CONTENT.format(campaign_content.post_link),
                disable_web_page_preview=True
            )
            continue

        mother_channel = campaign_content.mother_channel.get_id_or_tag

        banner_id, short_links_ids, campaign_file = render_campaign_content(
            campaign_content,
            user,
            mother_channel,
            campaign_user.id
        )
        campaign_post = CampaignPost.objects.create(
            campaign_content=campaign_content,
            campaign_user=campaign_user,
            message_id=banner_id,
            campaign_file=campaign_file,
        )
        campaign_posts.append(campaign_post)

        # update shortlinks
        if short_links_ids:
            ShortLink.objects.filter(
                id__in=short_links_ids
            ).update(
                campaign_post=campaign_post
            )

        if campaign_content.view_type == campaign_content.TYPE_VIEW_TOTAL and not campaign_content.message_id:
            campaign_content.message_id = banner_id
            campaign_content.save(update_fields=['updated_time', 'message_id'])

    # create message that define for CRM which channels got this campaign
    # and append the role of forward and sharing contents
    system_message, user_message = create_system_message(
        campaign_push.campaign,
        campaign_push.publishers.filter(id__in=channels)
    )
    agent.send_message(
        chat_id=campaign_post.campaign_content.mother_channel.get_id_or_tag,
        text=system_message
    )

    # forward banners and send system message to user
    for campaign_post in campaign_posts:
        agent.forward_message(
            chat_id=user.user_id,
            message_id=campaign_post.message_id,
            from_chat_id=campaign_post.campaign_content.mother_channel.get_id_or_tag
        )
    agent.send_message(chat_id=user.user_id, text=user_message)
    campaign_user.channels.set(campaign_push.publishers.filter(id__in=channels))

    # update campaign push status
    if campaign_push.status != CampaignPush.STATUS_RECEIVED:
        campaign_push.status = CampaignPush.STATUS_RECEIVED
        campaign_push.save(update_fields=['updated_time', 'status'])

    # if user has channels to get this campaign push again
    if campaign_push.has_push_data():
        send_push_to_user(campaign_push, users=(user,))

    # functions.check_send_push_again(campaign_push_id)
