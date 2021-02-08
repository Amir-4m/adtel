from rest_framework import serializers
from rest_framework.exceptions import ParseError

from django.utils.translation import ugettext_lazy as _

from .validators import validate_link_utm

from apps.telegram_adv.models import (
    Campaign,
    CampaignPublisher,
    CampaignContent,
    CampaignFile,
    CampaignLink,
    InlineKeyboard,
    TelegramChannel,
    ReceiverChannel,
    TelegramAgent,
    CampaignUser,
    CampaignPost,
    CampaignPostLog
)


class InlineKeyboardSerializer(serializers.ModelSerializer):
    utm_source = serializers.CharField(write_only=True, required=False)
    utm_campaign = serializers.CharField(write_only=True, required=False)
    utm_content = serializers.CharField(write_only=True, required=False)
    utm_medium = serializers.CharField(write_only=True, required=False)
    utm_term = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = InlineKeyboard
        fields = (
            'id', 'text', 'column',
            'row', 'link', 'utm_source',
            'utm_campaign', 'utm_content',
            'utm_medium', 'utm_term'
        )

    def validate(self, attrs):
        utm_source = attrs.get('utm_source', False)
        if utm_source:
            if not all((
                    attrs.get('utm_campaign', False),
                    attrs.get('utm_content', True),  # utm content is not required
                    attrs.get('utm_medium', False),
                    attrs.get('utm_term', False)
            )):
                raise ParseError(_('utm_source, utm_campaign, utm_medium, utm_term should define for shortlink'))

        return attrs


class CampaignFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CampaignFile
        fields = (
            'id', 'name', 'telegram_file_hash', 'file',
            'file_type', 'campaign_content', 'campaign'
        )
        read_only_fields = ('id',)
        extra_kwargs = {
            'campaign_content': {'write_only': True},
            'campaign': {'write_only': True},
            'file': {'write_only': True}
        }

    def validate(self, attrs):
        campaign = attrs.get('campaign', False)
        if campaign and attrs['file_type'] != CampaignFile.TYPE_PHOTO:
            raise ParseError(_('campaign just accept photo type files'))

        relations = [campaign, attrs.get('campaign_content', False)]
        if not any(relations) or all(relations):
            raise ParseError(_('one of campaign or campaign content should be fill'))

        if not any([attrs.get('file', False), attrs.get('telegram_file_hash', False)]):
            raise ParseError(_('file or telegram_file_hash is required'))

        return attrs


class CampaignContentSerializer(serializers.ModelSerializer):
    inlines = InlineKeyboardSerializer(many=True, required=False)
    files = CampaignFileSerializer(many=True, read_only=True, required=False)
    links = serializers.ListField(child=serializers.JSONField(validators=[validate_link_utm]), write_only=True,
                                  required=False, allow_empty=True)
    mother_channel = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = CampaignContent
        fields = (
            'id', 'display_text', 'content',
            'view_type', 'is_sticker', 'links',
            'campaign', 'inlines', 'files',
            'mother_channel', 'post_link'
        )
        read_only_fields = ('id',)
        extra_kwargs = {
            'campaign': {'write_only': True}
        }

    def validate(self, attrs):
        links = attrs.get('links', [])
        content = attrs.get('content')
        is_sticker = attrs.get('is_sticker', False)
        post_link = attrs.get('post_link')
        view_type = attrs.get('view_type')
        mother_channel = attrs.get('mother_channel')

        if not any([is_sticker, content, post_link]):
            raise ParseError(_('one of is sticker or content or post link should fill'))

        elif post_link:  # post is already exists in it's channel then nothing is needed user should forward himself
            if view_type == CampaignContent.TYPE_VIEW_PARTIAL:
                raise ParseError(_('content with post link only can be total view type'))
            attrs.pop('inlines', None)
            attrs.pop('links', None)
            attrs.pop('content', None)
            attrs.pop('is_sticker', None)

        else:
            if mother_channel is not None and not ReceiverChannel.objects.filter(chat_id=mother_channel).exists():
                raise ParseError(_('mother channel id is not valid!'))

            if not mother_channel:
                raise ParseError(_('mother channel can only be empty when post link is filled'))

            elif content:
                # if links, all of them should exists in content for replace them with shortlink
                if any(link_data['link'] for link_data in links if link_data['link'] not in content):
                    raise ParseError(_('your links should be exist in your content'))

            elif is_sticker:  # content is sticker
                attrs.pop('inlines', None)
                attrs.pop('links', None)
                attrs.pop('content', None)
                attrs.pop('post_link', None)

        return attrs

    def create(self, validated_data):
        inlines = validated_data.pop('inlines', [])
        links = validated_data.pop('links', [])
        mother_channel = validated_data.pop('mother_channel', None)
        if mother_channel:  # if pass post link no mother channel needed
            validated_data.update({'mother_channel': ReceiverChannel.objects.get(chat_id=mother_channel)})
        campaign_content = super().create(validated_data)

        for inline_data in inlines:
            campaign_link = None
            utm_source = inline_data.pop('utm_source', False)
            if utm_source:
                # means InlineKeyBoard has shortlink and need to create CampaignLink with it's utm params
                extra_data = dict(
                    utm_source=utm_source,
                    utm_campaign=inline_data.pop('utm_campaign'),
                    utm_medium=inline_data.pop('utm_medium'),
                    utm_term=inline_data.pop('utm_term')
                )
                utm_content = inline_data.pop('utm_content', False)
                if utm_content:
                    extra_data.update(utm_content=utm_content)

                campaign_link = CampaignLink.objects.create(
                    campaign_content=campaign_content,
                    link=inline_data['link'],
                    extra_data=extra_data
                )

            InlineKeyboard.objects.create(
                campaign_content=campaign_content,
                campaign_link=campaign_link,
                **inline_data
            )

        for link_data in links:
            CampaignLink.objects.create(
                campaign_content=campaign_content,
                link=link_data.pop('link'),
                extra_data=link_data
            )

        return campaign_content


class CampaignPublisherSerializer(serializers.ModelSerializer):
    class Meta:
        model = CampaignPublisher
        fields = (
            'id', 'title', 'status', 'is_enable', 'start_datetime',
            'end_datetime', 'publishers', 'contents', 'max_view'
        )


class CampaignSerializer(serializers.ModelSerializer):
    contents = CampaignContentSerializer(many=True, read_only=True)
    publishers = serializers.ListField(
        child=serializers.ListField(),
        write_only=True,
        allow_null=False,
        allow_empty=False
    )
    agents = serializers.ListField(
        child=serializers.CharField(),
        write_only=True,
        allow_null=False,
        allow_empty=False
    )
    file = CampaignFileSerializer(read_only=True)

    class Meta:
        model = Campaign
        fields = (
            'id', 'title', 'status', 'is_enable',
            'start_datetime', 'end_datetime', 'publishers',
            'contents', 'max_view', 'agents', 'file'
        )
        read_only_fields = ('id', 'file')

    def validate(self, attrs):
        if self.partial:
            if not getattr(self.instance, 'file', False):
                raise ParseError(_('campaign file is empty yet first you have to upload your file'))

            return {'is_enable': attrs.get('is_enable', False)}

        else:
            publishers = attrs.get('publishers', None)
            _publishers_count = TelegramChannel.objects.filter(
                id__in=[p[0] for p in publishers]
            ).count()

            if _publishers_count != len(publishers):
                raise ParseError(_('some of publishers are not in database! please re-check'))

        return attrs

    def create(self, validated_data):
        publishers = validated_data.pop('publishers', ())
        agents = validated_data.pop('agents', ())
        campaign = super().create(validated_data)
        campaign.receiver_agents.set(TelegramAgent.objects.filter(bot_name__in=agents))
        publishers = [
            CampaignPublisher(campaign=campaign, publisher_id=publisher, tariff=tariff)
            for publisher, tariff in publishers
        ]
        CampaignPublisher.objects.bulk_create(publishers)

        return campaign

    def to_representation(self, instance):
        campaign = super().to_representation(instance)
        campaign.update({'report_link': instance.report_link})
        return campaign


class CampaignPostSerializer(serializers.ModelSerializer):
    views = serializers.SerializerMethodField()
    title = serializers.CharField(source='campaign_content.display_text')

    class Meta:
        model = CampaignPost
        fields = (
            'views', 'screen_shot', 'title'
        )

    def get_views(self, obj):
        if not obj.views:
            return getattr(obj.logs.last(), 'banner_views', 0)

        return obj.views


class CampaignUserSerializer(serializers.ModelSerializer):
    username = serializers.ReadOnlyField(source="user.username")
    channels = serializers.ReadOnlyField(source="channel_tags")
    channel_ids = serializers.SerializerMethodField()
    posts = CampaignPostSerializer(source='campaignpost_set', many=True, read_only=True)

    class Meta:
        model = CampaignUser
        fields = (
            'created_time', 'username',
            'channels', 'receipt_price', 'posts', 'channel_ids'
        )

    def get_channel_ids(self, obj):
        return obj.channels.values_list('id', flat=True)


class TelegramChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelegramChannel
        fields = (
            'id', 'tag', 'title', 'member_no', 'view_efficiency'
        )


class CampaignPostLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = CampaignPostLog
        fields = '__all__'
