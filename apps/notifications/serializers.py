from rest_framework import serializers


class TelegramLinkSerializer(serializers.Serializer):
    link = serializers.URLField(read_only=True)
