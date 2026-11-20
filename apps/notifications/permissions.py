import secrets

from django.conf import settings
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


class HasBotSecret(BasePermission):
    """Bot so'rovlaridagi X-Bot-Secret header'ini timing-safe usulda tekshiradi."""

    message = "Bot maxfiy kaliti noto'g'ri yoki yuborilmagan."

    def has_permission(self, request: Request, view: APIView) -> bool:
        expected = settings.BOT_API_SECRET
        provided = request.headers.get("X-Bot-Secret", "")
        # Sozlanmagan yoki bo'sh secret bilan tasodifiy kirishga yo'l qo'yilmaydi
        if not expected or not provided:
            return False
        return secrets.compare_digest(provided, expected)
