from django.utils.translation import ugettext as _

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from persian import convert_en_numbers


def start_buttons():
    buttons = [
        [KeyboardButton(_('finish shot')), KeyboardButton(_('active ad'))],
        [KeyboardButton(_('remove channel')), KeyboardButton(_('channel list')), KeyboardButton(_('add channel'))],
        [KeyboardButton(_('report financial')), KeyboardButton(_('send sticker'))],
        [KeyboardButton(_('about us')), KeyboardButton(_('help'))],
    ]
    return ReplyKeyboardMarkup(buttons, one_time_keyboard=True)


def confirm_button():
    to_send = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("بله", callback_data="yes"),
             InlineKeyboardButton("خیر", callback_data="no")],
        ]
    )
    return to_send


def back_button(back):
    to_send = InlineKeyboardMarkup([
        [InlineKeyboardButton("بازگشت ◀️", callback_data=back)]
    ])
    return to_send


def cancel_button():
    to_send = InlineKeyboardMarkup([
        [InlineKeyboardButton("انصراف", callback_data="cancel")]
    ])
    return to_send


def active_campaigns(campaigns, back_data=None):
    buttons = []
    for campaign in campaigns:
        buttons.append([InlineKeyboardButton(text=campaign.text_display(), callback_data=f"cmp_{campaign.id}")])

    if back_data:
        buttons.append([InlineKeyboardButton(text="بازگشت ◀️", callback_data=back_data)])
    return InlineKeyboardMarkup(buttons)


def active_campaign_user(campaign_users, campaign_id):
    buttons = [
        [InlineKeyboardButton(text=campaign_user.channel_tags, callback_data=f"ucmp_{campaign_user.id}_{campaign_id}")]
        for campaign_user in campaign_users
    ]
    buttons.append([InlineKeyboardButton(text="بازگشت ◀️", callback_data=f"back_to_active_adv")])
    return InlineKeyboardMarkup(buttons)


def exists_channel():
    to_send = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("بله ✅", callback_data="add"),
             InlineKeyboardButton("خیر ✏️", callback_data="no")],
        ]
    )
    return to_send


def sheba_button():
    to_send = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("بله ✅", callback_data="yes"),
             InlineKeyboardButton("ویرایش ✏️", callback_data="edit")],
            [InlineKeyboardButton("لغو ❌", callback_data="cancel")]
        ]
    )
    return to_send


def add_sheba_button():
    to_send = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("افزودن شبا برای کانال های بدون شبا", callback_data="add_sheba")]
        ]
    )
    return to_send


def campaign_push_reply_markup(campaign_push_user, selected_channels=()):
    buttons = []
    _selected_channels_ids = {int(x["id"]) for x in selected_channels}
    for sheba, channels_info in campaign_push_user.get_push_data().items():
        for channel_info in channels_info:
            if channel_info["id"] in _selected_channels_ids:
                text = f'{channel_info["tag"]} _ {convert_en_numbers(channel_info["tariff"])} کایی ✅'
            else:
                text = f'{channel_info["tag"]} _ {convert_en_numbers(channel_info["tariff"])} کایی '

            callback_data = f'push_{campaign_push_user.id}_{channel_info["id"]}_{channel_info["tariff"]}'
            buttons.append([InlineKeyboardButton(text=text, callback_data=callback_data)])

        buttons.append(
            [InlineKeyboardButton(f' شبا 💳 {sheba[:5]}XXX{sheba[-5:]}', callback_data='push_campaign_sheba')]
        )

    buttons.append(
        [
            InlineKeyboardButton(text=f'نمی خوام ❌', callback_data=f'push_campaign_cancel_{campaign_push_user.id}'),
            InlineKeyboardButton(text=f'دریافت 📥', callback_data=f'push_campaign_get_{campaign_push_user.id}')
        ]
    )
    return InlineKeyboardMarkup(buttons)
