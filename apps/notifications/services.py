import logging
import secrets

import httpx
from django.conf import settings

from apps.users.models import User

logger = logging.getLogger(__name__)

TELEGRAM_API_TIMEOUT = 10.0


def create_telegram_link(user: User) -> str:
    """Foydalanuvchi uchun bir martalik bog'lash tokeni va Telegram havolasini yaratadi."""
    token = secrets.token_urlsafe(16)
    user.telegram_link_token = token
    user.save(update_fields=["telegram_link_token"])
    bot_username = settings.TELEGRAM_BOT_USERNAME.lstrip("@")
    return f"https://t.me/{bot_username}?start={token}"


def send_message(chat_id: int, text: str) -> bool:
    """Telegram Bot API orqali foydalanuvchiga xabar yuboradi."""
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN sozlanmagan, xabar yuborilmadi (chat_id=%s).", chat_id)
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        response = httpx.post(
            url,
            json={"chat_id": chat_id, "text": text},
            timeout=TELEGRAM_API_TIMEOUT,
        )
        response.raise_for_status()
        return True
    except httpx.HTTPStatusError as exc:
        # Bot tokeni URL ichida bo'lgani uchun log'ga to'liq exception matni yozilmaydi
        logger.error(
            "Telegram sendMessage HTTP xatosi (chat_id=%s, status=%s).",
            chat_id,
            exc.response.status_code,
        )
    except httpx.TimeoutException:
        logger.error("Telegram sendMessage vaqt chegarasidan oshdi (chat_id=%s).", chat_id)
    except httpx.RequestError as exc:
        logger.error(
            "Telegram sendMessage tarmoq xatosi (chat_id=%s, xato=%s).",
            chat_id,
            type(exc).__name__,
        )
    except Exception as exc:
        # Telegram xatosi hech qachon asosiy so'rovni buzmasligi kerak
        logger.error(
            "Telegram sendMessage kutilmagan xato (chat_id=%s, xato=%s).",
            chat_id,
            type(exc).__name__,
        )
    return False
