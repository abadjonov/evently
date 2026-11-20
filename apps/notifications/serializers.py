from rest_framework import serializers


class TelegramLinkSerializer(serializers.Serializer):
    link = serializers.URLField(read_only=True)


class TelegramConfirmSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=64, allow_blank=False)
    chat_id = serializers.IntegerField()


class TelegramConfirmResponseSerializer(serializers.Serializer):
    detail = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
