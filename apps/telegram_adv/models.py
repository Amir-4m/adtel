import re

from django.db import models
from django.urls import reverse
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import User
from django.utils.html import format_html
from django.utils.translation import ugettext_lazy as _
from django.utils.safestring import mark_safe
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db.models import Case, When, F, IntegerField, Max, Sum
from django.db.models.functions import Coalesce
from django.contrib.postgres.fields import JSONField

from khayyam import JalaliDatetime
from persian import convert_en_numbers

from apps.utils.url_encoder import UrlEncoder

url_encoder = UrlEncoder()


def validate_sheba_number(sheba_number):
    if re.match('^IR[0-9]{24}$', sheba_number):
        return True
    raise ValidationError(_('incorrect sheba number'), code='invalid')


class BankAccount(models.Model):
    created_time = models.DateTimeField(_('created time'), auto_now_add=True)
    updated_time = models.DateTimeField(_('update time'), auto_now=True)
    sheba_number = models.CharField(_('sheba'), max_length=26, unique=True, validators=[validate_sheba_number])
    sheba_owner = models.CharField(_('sheba owner'), max_length=100)

    class Meta:
        db_table = 'bank_account'

    def __str__(self):
        return f'{self.sheba_number} - {self.sheba_owner}'


class TelegramChannel(models.Model):
    created_time = models.DateTimeField(_('created time'), auto_now_add=True)
    updated_time = models.DateTimeField(_('update time'), auto_now=True)
    tag = models.CharField(_('channel tag'), max_length=32)
    title = models.CharField(_('channel title'), max_length=255, blank=True)
    channel_id = models.BigIntegerField(_('channel id'), unique=True, null=True, blank=True)
    member_no = models.PositiveIntegerField(_('channel members'), null=True, blank=True)
    view_efficiency = models.PositiveIntegerField(_('view efficiency'), default=1000)

    sheba = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name="channels")
    admins = models.ManyToManyField('telegram_user.TelegramUser', blank=True)

    class Meta:
        db_table = 'telegram_channel'

    def __str__(self):
        return f"#{self.id} - {self.tag}"


class TelegramAgent(models.Model):
    created_time = models.DateTimeField(_('created time'), auto_now_add=True)
    updated_time = models.DateTimeField(_('last update time'), auto_now=True)
    bot_name = models.CharField(_('bot name'), max_length=100)
    bot_token = models.CharField(_('bot token'), max_length=100, unique=True)
    specific_mark = models.CharField(_('agent mark'), max_length=50, unique=True)

    class Meta:
        db_table = 'telegram_agent'

    def __str__(self):
        return self.bot_name


class FinancialManager(models.Manager):
    def user_invoices(self, user_id):
        return self.select_related('adv').filter(
            user_id=user_id,
            approve_time__isnull=False,
        ).exclude(
            screen_shot=''
        )


class ReceiverChannel(models.Model):
    created_time = models.DateTimeField(_('created time'), auto_now_add=True)
    updated_time = models.DateTimeField(_('last update time'), auto_now=True)
    title = models.CharField(_('channel title'), max_length=255)
    tag = models.CharField(_('channel tag'), max_length=32, blank=True)
    chat_id = models.BigIntegerField(_('chat id'), blank=True, null=True)

    class Meta:
        db_table = 'telegram_receiver_channel'

    def __str__(self):
        return self.title

    def clean(self):
        """
        Require at least one of tag or chat_id to be set
        """
        if not (self.tag or self.chat_id):
            raise ValidationError(_("A tag or invite_link is required"), code='invalid')

    @property
    def get_id_or_tag(self):
        return self.chat_id or self.tag


class Campaign(models.Model):
    STATUS_WAITING = 'waiting'
    STATUS_TEST = 'test'
    STATUS_APPROVED = 'approved'
    STATUS_CLOSE = 'close'
    STATUS_REJECTED = 'rejected'

    STATUS_TYPES = (
        (STATUS_WAITING, _('waiting')),
        (STATUS_TEST, _('test')),
        (STATUS_APPROVED, _('approved')),
        (STATUS_CLOSE, _('close')),
        (STATUS_REJECTED, _('rejected'))
    )
    created_time = models.DateTimeField(_('created time'), auto_now_add=True)
    updated_time = models.DateTimeField(_('updated time'), auto_now=True)
    title = models.CharField(_('title'), max_length=150)
    status = models.CharField(_('status'), max_length=15, choices=STATUS_TYPES, default=STATUS_WAITING)
    post_limit = models.PositiveIntegerField(default=5)
    max_view = models.PositiveIntegerField(_('max view'))
    is_enable = models.BooleanField(_("is enable"), default=False)
    start_datetime = models.DateTimeField(_('start datetime'))
    end_datetime = models.DateTimeField(_('end datetime'))

    publishers = models.ManyToManyField(TelegramChannel, through="CampaignPublisher")
    receiver_agents = models.ManyToManyField('TelegramAgent', verbose_name='receiver agent')

    class Meta:
        db_table = "campaigns"
        ordering = ['-id']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._b_status = self.status

    def __str__(self):
        return f'c_{self.id} - {self.title}'

    def text_display(self):
        start_time = convert_en_numbers(JalaliDatetime(self.start_datetime).strftime("%m/%d"))
        return f"{start_time} - {self.title}"

    def text_get_ad(self):
        tariif = self.publishers.aggregate(pt=Max('campaignpublisher__tariff'))
        return f"بنر {self.title} - کایی {convert_en_numbers(tariif['pt'])} - محدودیت " \
               f"{convert_en_numbers(self.post_limit)} پست"

    def url_encode(self):
        return url_encoder.encode_id(self.id)

    def total_contents_views(self):
        """
        max Campaign total contents views
        * views is same for all CampaignUser then max of views if enough
            1 - their views field if is not null
            2 - else last CampaignPostLog of that CampaignPost views

        :return: list of Content name and it's views
        """
        return list(self.contents.filter(
            view_type=CampaignContent.TYPE_VIEW_TOTAL,
            campaignpost__is_enable=True,
        ).annotate(
            views=Max(
                Case(
                    When(campaignpost__views__isnull=False, then=F("campaignpost__views")),
                    output_field=IntegerField(),
                    default=F("campaignpost__logs__banner_views"),
                ), output_field=IntegerField()
            )
        ).values("id", "display_text", "views"))

    def partial_contents_views(self):
        """
        Sum Campaign partial contents views
            condition CampaignPost views:
                1 - their views field if is not null
                2 - else last CampaignPostLog of that CampaignPost views
            then:
                Sum views together

        :return: list of Content name and it's views
        """

        campaign_contents_info = {
            x['id']: dict(text=x['display_text'], views=x['views'])
            for x in self.contents.filter(
                view_type=CampaignContent.TYPE_VIEW_PARTIAL,
                campaignpost__is_enable=True,
                campaignpost__views__isnull=False,
            ).annotate(
                views=Sum("campaignpost__views")
            ).values("id", "display_text", "views")
        }

        for cp in CampaignPost.objects.select_related('campaign_content').filter(
                campaign_content__campaign=self,
                campaign_content__view_type=CampaignContent.TYPE_VIEW_PARTIAL,
                is_enable=True,
                views__isnull=True,
        ):
            views = getattr(cp.logs.last(), 'banner_views', 0)
            cc = cp.campaign_content
            if cc.id in campaign_contents_info:
                campaign_contents_info[cc.id]['views'] += views
            else:
                campaign_contents_info[cc.id] = dict(id=cc.id, display_text=cc.display_text, views=views)

        return list(campaign_contents_info.values())

    def shortlink_views(self):
        links = list(
            self.contents.filter(
                links__isnull=False
            ).prefetch_related(
                "links__short_links__logs"
            ).values(
                'id', 'display_text'
            ).annotate(
                ip_count=Sum('links__short_links__logs__ip_count'),
                hit_count=Sum('links__short_links__logs__hit_count')
            )
        )
        return links

    @property
    def report_link(self):
        return settings.BASE_REPORT_URL + reverse('advertiser-report', args=[self.url_encode()])

    @staticmethod
    def url_decode(decode_string):
        return url_encoder.decode_id(decode_string)


class CampaignPublisher(models.Model):
    created_time = models.DateTimeField(_('created time'), auto_now_add=True)
    publisher = models.ForeignKey(TelegramChannel, on_delete=models.PROTECT)
    campaign = models.ForeignKey(Campaign, on_delete=models.PROTECT)
    tariff = models.PositiveIntegerField(_('tariff'))

    class Meta:
        db_table = 'campaign_publishers'
        constraints = [
            models.UniqueConstraint(fields=('publisher', 'campaign'), name='campaign_publish')
        ]

    def __str__(self):
        return f"campaign: #{self.campaign_id} campaign publisher: {self.publisher_id} tariff: {self.tariff}"


class CampaignContent(models.Model):
    TYPE_VIEW_TOTAL = 'total'
    TYPE_VIEW_PARTIAL = 'partial'

    VIEW_TYPES = (
        (TYPE_VIEW_TOTAL, _('total')),
        (TYPE_VIEW_PARTIAL, _('partial')),
    )

    created_time = models.DateTimeField(_('created time'), auto_now_add=True)
    updated_time = models.DateTimeField(_('updated time'), auto_now=True)
    display_text = models.CharField(_('display text'), max_length=150)
    content = models.TextField(_('content'), blank=True, null=True)
    extra_data = JSONField(default=dict, editable=False)
    view_type = models.CharField(_('view type'), max_length=7, choices=VIEW_TYPES)
    message_id = models.PositiveIntegerField(_('message id'), null=True, blank=True)
    post_link = models.URLField(
        _('post link'), null=True, blank=True,
        validators=[
            RegexValidator(
                regex=r"(?:https?:)?//(?:t(?:elegram)?\.me|telegram\.org)/[a-zA-Z_]+/[0-9]+(/([0-9]+)?/?)?",
                message=_("this link is not a valid telegram post link")
            )
        ]
    )
    is_sticker = models.BooleanField(_('is sticker'), default=False)

    campaign = models.ForeignKey(Campaign, on_delete=models.PROTECT, related_name="contents")
    mother_channel = models.ForeignKey(ReceiverChannel, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        db_table = "campaigns_contents"

    def __str__(self):
        return f"c_{self.campaign_id} - {self.display_text}"

    def clean(self):
        if self.content:
            count_markup_chars = [self.content.count('*'), self.content.count('_'), self.content.count('`')]
            if any(count for count in count_markup_chars if count % 2 != 0):
                raise ValidationError(
                    _("your template has invalid markdown tags check your text where has: [* ` _ ```]"),
                    code='invalid'
                )

        if all([self.content, self.is_sticker]) or not any([self.content, self.is_sticker]):
            raise ValidationError(_('one of content or is_sticker should fill'), code='invalid')


class CampaignLink(models.Model):
    created_time = models.DateTimeField(_('created time'), auto_now_add=True)
    updated_time = models.DateTimeField(_('last update time'), auto_now=True)
    link = models.URLField(_('link'))
    extra_data = JSONField(default=dict)

    campaign_content = models.ForeignKey(CampaignContent, on_delete=models.PROTECT, related_name="links")

    class Meta:
        db_table = 'campaign_link'

    def __str__(self):
        return f"content: #{self.campaign_content_id} {self.link}"

    def is_inline(self):
        return bool(self.inline)


class ShortLink(models.Model):
    created_time = models.DateTimeField(_('created time'), auto_now_add=True)
    updated_time = models.DateTimeField(_('last update time'), auto_now=True)
    link = models.CharField(_('short link'), max_length=60)
    reference_id = models.PositiveIntegerField(_('reference id'), blank=True)

    campaign_link = models.ForeignKey(CampaignLink, on_delete=models.PROTECT, related_name="short_links")
    campaign_post = models.ForeignKey("CampaignPost", on_delete=models.PROTECT, related_name="links", null=True)

    class Meta:
        db_table = 'telegram_short_links'

    def __str__(self):
        return f"id: #{self.id} {self.link}"


class ShortLinkLog(models.Model):
    created_time = models.DateTimeField(_('created time'), auto_now_add=True)
    hit_count = models.PositiveIntegerField(_('hit count'), default=0)
    ip_count = models.PositiveIntegerField(_('ip count'), default=0)

    short_link = models.ForeignKey(ShortLink, on_delete=models.PROTECT, related_name="logs")

    class Meta:
        db_table = 'telegram_short_links_logs'

    def __str__(self):
        return f"{self.short_link} ip count: {self.ip_count} hit count: {self.hit_count}"


class CampaignFile(models.Model):
    TYPE_PHOTO = 'photo'
    TYPE_VIDEO = 'video'
    TYPE_AUDIO = 'audio'
    TYPE_DOCUMENT = 'document'

    FILE_TYPES = (
        (TYPE_PHOTO, _('photo')),
        (TYPE_VIDEO, _('video')),
        (TYPE_AUDIO, _('audio')),
        (TYPE_DOCUMENT, _('document')),
    )

    created_time = models.DateTimeField(_('created time'), auto_now_add=True)
    updated_time = models.DateTimeField(_('updated time'), auto_now=True)
    name = models.CharField(_('name'), max_length=200)
    file = models.FileField(_('file'), blank=True)
    telegram_file_hash = models.TextField(_('telegram file hash'), blank=True)
    file_type = models.CharField(_('file type'), max_length=8, choices=FILE_TYPES)

    campaign_content = models.ForeignKey(CampaignContent, on_delete=models.CASCADE, related_name="files", null=True)
    campaign = models.OneToOneField(Campaign, on_delete=models.PROTECT, related_name="file", null=True)

    class Meta:
        db_table = "campaigns_files"

    def __str__(self):
        return self.name

    def clean(self):
        if not any([self.telegram_file_hash, self.file]):
            raise ValidationError(_("you should fill file or telegram file hash"), code='invalid')

    def get_file(self):
        return self.telegram_file_hash or self.file


class InlineKeyboard(models.Model):
    created_time = models.DateTimeField(_('created time'), auto_now_add=True)
    updated_time = models.DateTimeField(_('updated time'), auto_now=True)
    text = models.CharField(_('panel text'), max_length=100)
    row = models.PositiveIntegerField(_('panel row'))
    column = models.PositiveIntegerField(_('panel column'))
    link = models.URLField(_('link'))

    campaign_link = models.OneToOneField(CampaignLink, on_delete=models.PROTECT, related_name="inline", null=True, blank=True)
    campaign_content = models.ForeignKey(CampaignContent, related_name="inlines", on_delete=models.CASCADE)

    class Meta:
        db_table = 'campaigns_inline_keyboards'
        unique_together = ('row', 'column', 'campaign_content')

    def __str__(self):
        return f"{self.text} content: #{self.campaign_content_id}"

    def clean(self):
        if not any([self.link, self.campaign_link]):
            raise ValidationError(_('one of link or campaign link should be fill'), code='invalid')

    @property
    def has_tracker(self):
        return bool(self.campaign_link)


class CampaignUserManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related(
            'campaign'
        ).filter(
            channels__isnull=False,
            campaignpost__is_enable=True,
            campaignpost__campaign_content__view_type=CampaignContent.TYPE_VIEW_PARTIAL
        ).distinct()


class CampaignUser(models.Model):
    created_time = models.DateTimeField(_('created time'), auto_now_add=True)
    updated_time = models.DateTimeField(_('updated time'), auto_now=True)
    receipt_price = models.PositiveIntegerField(_('receipt price'), null=True, blank=True)
    receipt_date = models.DateField(_('receipt date'), null=True, blank=True)
    receipt_code = models.CharField(_('receipt code'), max_length=50, blank=True)
    sheba_number = models.CharField(_('sheba number'), max_length=26)
    sheba_owner = models.CharField(_('sheba owner'), max_length=100)
    tariff = models.PositiveIntegerField(_('tariff'), null=True, blank=True)

    campaign = models.ForeignKey(Campaign, on_delete=models.PROTECT)
    user = models.ForeignKey('telegram_user.TelegramUser', on_delete=models.PROTECT)
    agent = models.ForeignKey(TelegramAgent, on_delete=models.PROTECT)
    channels = models.ManyToManyField(TelegramChannel)

    objects = models.Manager()
    report = CampaignUserManager()

    class Meta:
        db_table = "campaigns_users"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._b_receipt_date = self.receipt_date

    def __str__(self):
        return f"{self.campaign} user: `{self.user}`"

    @property
    def paid(self):
        return bool(self.receipt_date)

    @property
    def channel_tags(self):
        return " ".join(self.channels.values_list('tag', flat=True).distinct())

    @property
    def channel_titles(self):
        return " | ".join(self.channels.values_list('title', flat=True).distinct())

    def push_channels_context(self):
        return "\n".join(self.channels.values_list('tag', flat=True).distinct())

    def get_jalali_created_time(self):
        return JalaliDatetime(self.created_time).strftime('%C')

    def get_jalali_receipt_date(self):
        if self.receipt_date:
            return JalaliDatetime(self.receipt_date).strftime('%Y/%m/%d')
        return '-'

    def calculate_price(self):
        views = self.campaignpost_set.filter(
            campaign_content__view_type=CampaignContent.TYPE_VIEW_PARTIAL,
            views__isnull=False,
            is_enable=True
        ).aggregate(
            views=Coalesce(Max('views'), 0)
        )['views']

        return int(self.tariff * views / 1000) * 10

    def has_receipt_date_changed(self):
        return self._b_receipt_date is None and self._b_receipt_date != self.receipt_date


class CampaignPost(models.Model):
    def shot_directory_path(self, filename):
        ext = filename.split('.')[-1]
        return f'shot_{self.id}.{ext}'

    created_time = models.DateTimeField(_('created time'), auto_now_add=True)
    updated_time = models.DateTimeField(_('updated time'), auto_now=True)
    message_id = models.PositiveIntegerField(_('message id'), null=True)
    views = models.PositiveIntegerField(null=True, blank=True)
    screen_shot = models.ImageField(_('screen shot'), upload_to=shot_directory_path, blank=True)
    screen_time = models.DateTimeField(_('screen shot time'), null=True, editable=False)
    approve_time = models.DateTimeField(_('approve time'), null=True, editable=False)

    campaign_content = models.ForeignKey(CampaignContent, on_delete=models.PROTECT)
    campaign_file = models.ForeignKey(CampaignFile, on_delete=models.PROTECT, related_name="posts", null=True,
                                      blank=True)
    campaign_user = models.ForeignKey(CampaignUser, on_delete=models.PROTECT)

    description = models.TextField(_('description'), blank=True)
    is_enable = models.BooleanField(_('is enable'), default=True)

    class Meta:
        db_table = "campaigns_posts"

    def __str__(self):
        return f"cp_{self.id} - {self.campaign_content.display_text}"

    def save(self, *args, **kwargs):
        if self.screen_shot and not self.screen_time:
            self.screen_time = timezone.now()

        super().save(*args, **kwargs)

    @property
    def has_screen_shot(self):
        return self.screen_shot and self.screen_shot != 'no_shot'

    @property
    def _is_approved(self):
        return bool(self.approve_time)

    @property
    def _has_tariff(self):
        return self.campaign_content.view_type == CampaignContent.TYPE_VIEW_PARTIAL

    @property
    def has_tracker(self):
        return self.links.exists()

    def _screen_preview(self):
        if not self.screen_shot:
            return '-'

        elif self.screen_shot == 'no_shot':
            return format_html('<img src="/static/admin/img/icon-deletelink.svg" alt="no_video">')

        else:
            return mark_safe(
                '<a href={} class="nowrap" onclick="return windowpop(this.href, this.width, this.height)"><span class="viewlink" title="View Screenshot"></span>{}</a>'.format(
                    self.screen_shot.url,
                    self.screen_time.strftime('%y/%m/%d %H:%M')
                )
            )


class CampaignPostLog(models.Model):
    created_time = models.DateTimeField(_('created time'), auto_now_add=True)
    banner_views = models.PositiveIntegerField(_('banner views'))

    campaign_post = models.ForeignKey(CampaignPost, on_delete=models.CASCADE, related_name='logs')

    class Meta:
        db_table = "campaigns_posts_logs"

    def __str__(self):
        return f"{self.campaign_post_id}"
