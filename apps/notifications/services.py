import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.events.exceptions import BusinessError
from apps.events.models import Event, Registration
from apps.users.models import User

logger = logging.getLogger(__name__)

TELEGRAM_API_TIMEOUT = 10.0

UZBEK_MONTHS: dict[int, str] = {
    1: "yanvar",
    2: "fevral",
    3: "mart",
    4: "aprel",
    5: "may",
    6: "iyun",
    7: "iyul",
    8: "avgust",
    9: "sentabr",
    10: "oktabr",
    11: "noyabr",
    12: "dekabr",
}


def format_uzbek_datetime(dt: datetime) -> str:
    """Sanani mahalliy vaqt mintaqasida o'zbekcha ko'rinishga keltiradi ("5-dekabr, 14:00")."""
    # Bazadan UTC qaytgan vaqtni foydalanuvchiga Asia/Tashkent vaqtida ko'rsatamiz
    local_dt = timezone.localtime(dt) if timezone.is_aware(dt) else dt
    month_name = UZBEK_MONTHS[local_dt.month]
    return f"{local_dt.day}-{month_name}, {local_dt:%H:%M}"


def create_telegram_link(user: User) -> str:
    """Foydalanuvchi uchun bir martalik bog'lash tokeni va Telegram havolasini yaratadi."""
    token = secrets.token_urlsafe(16)
    user.telegram_link_token = token
    user.save(update_fields=["telegram_link_token"])
    bot_username = settings.TELEGRAM_BOT_USERNAME.lstrip("@")
    return f"https://t.me/{bot_username}?start={token}"


def confirm_telegram_link(*, token: str, chat_id: int) -> User:
    """Bog'lash tokenini tekshirib, telegram_chat_id ni saqlaydi va tokenni o'chiradi."""
    with transaction.atomic():
        user = User.objects.select_for_update().filter(telegram_link_token=token).first()
        if user is None:
            raise BusinessError(
                detail="Bog'lash tokeni yaroqsiz yoki eskirgan.",
                code="invalid_token",
            )

        # Bitta Telegram chat_id faqat bitta foydalanuvchiga bog'lanishi mumkin
        if User.objects.filter(telegram_chat_id=chat_id).exclude(pk=user.pk).exists():
            raise BusinessError(
                detail="Bu Telegram hisobi boshqa foydalanuvchiga bog'langan.",
                code="telegram_already_linked",
            )

        user.telegram_chat_id = chat_id
        user.telegram_link_token = None
        try:
            with transaction.atomic():
                user.save(update_fields=["telegram_chat_id", "telegram_link_token"])
        except IntegrityError as exc:
            raise BusinessError(
                detail="Bu Telegram hisobi boshqa foydalanuvchiga bog'langan.",
                code="telegram_already_linked",
            ) from exc
        return user


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


def _build_user_registration_text(event: Event) -> str:
    formatted_date = format_uzbek_datetime(event.start_at)
    return (
        "✅ Siz tadbirga muvaffaqiyatli yozildingiz!\n\n"
        f"📌 {event.title}\n"
        f"🗓 {formatted_date}\n"
        f"📍 {event.location}"
    )


def _build_admin_registration_text(user: User, event: Event, active_count: int) -> str:
    full_name = user.get_full_name().strip() or user.email
    participant = f"{full_name} ({user.phone_number})" if user.phone_number else full_name
    seats = (
        f"{active_count} / {event.capacity}"
        if event.capacity is not None
        else f"{active_count} / cheklanmagan"
    )
    return f"🆕 Yangi qatnashuvchi\n\n👤 {participant}\n📌 {event.title}\n👥 Band joylar: {seats}"


def _safe_send_message(chat_id: int, text: str) -> None:
    # send_message ichida xato tutiladi, lekin tashqi/mock xatolar ham oqimni buzmasligi kerak
    try:
        send_message(chat_id, text)
    except Exception as exc:
        logger.error(
            "Telegram xabarnoma yuborishda xatolik (chat_id=%s, xato=%s).",
            chat_id,
            type(exc).__name__,
        )


def notify_registration(registration_id: int) -> None:
    """Yangi ro'yxatdan o'tish haqida foydalanuvchi va bog'langan adminlarga xabar yuboradi."""
    registration = (
        Registration.objects.select_related("user", "event").filter(pk=registration_id).first()
    )
    if registration is None:
        logger.warning("Xabarnoma uchun Registration topilmadi (id=%s).", registration_id)
        return

    user = registration.user
    event = registration.event

    if user.telegram_chat_id is not None:
        _safe_send_message(user.telegram_chat_id, _build_user_registration_text(event))

    admin_chat_ids = list(
        User.objects.filter(
            role=User.Role.ADMIN,
            telegram_chat_id__isnull=False,
        ).values_list("telegram_chat_id", flat=True)
    )
    if not admin_chat_ids:
        return

    active_count = Registration.objects.filter(
        event=event,
        status=Registration.Status.ACTIVE,
    ).count()
    admin_text = _build_admin_registration_text(user, event, active_count)
    for chat_id in admin_chat_ids:
        _safe_send_message(chat_id, admin_text)


def get_due_reminder_registrations(
    *,
    now: datetime | None = None,
    hours_before: int | None = None,
) -> QuerySet[Registration]:
    """Eslatma yuborish vaqti kelgan faol ro'yxatdan o'tishlarni qaytaradi."""
    current_time = now if now is not None else timezone.now()
    reminder_hours = hours_before if hours_before is not None else settings.REMINDER_HOURS_BEFORE
    deadline = current_time + timedelta(hours=reminder_hours)

    # N+1 so'rovlar bo'lmasligi uchun user va event bitta SQL JOIN bilan olinadi
    return (
        Registration.objects.select_related("user", "event")
        .filter(
            status=Registration.Status.ACTIVE,
            reminder_sent=False,
            event__status=Event.Status.OPEN,
            event__start_at__gt=current_time,
            event__start_at__lte=deadline,
            user__telegram_chat_id__isnull=False,
        )
        .order_by("event__start_at", "id")
    )


def build_event_reminder_text(event: Event) -> str:
    """Tadbir boshlanishidan oldingi eslatma (T2) xabar matnini tayyorlaydi."""
    formatted_date = format_uzbek_datetime(event.start_at)
    return (
        "⏰ Eslatma!\n\n"
        "Ertaga siz yozilgan tadbir bo‘lib o‘tadi:\n"
        f"📌 {event.title}\n"
        f"🗓 {formatted_date}\n"
        f"📍 {event.location}\n\n"
        "Kechikmang! 🙂"
    )


def send_event_reminder(registration: Registration) -> bool:
    """Bitta ro'yxatdan o'tish uchun Telegram eslatma xabarini yuboradi."""
    chat_id = registration.user.telegram_chat_id
    if chat_id is None:
        return False

    text = build_event_reminder_text(registration.event)
    try:
        return bool(send_message(chat_id, text))
    except Exception as exc:
        # Bitta foydalanuvchidagi Telegram xatosi qolgan eslatmalarni to'xtatmasligi kerak
        logger.error(
            "Telegram eslatma yuborishda xatolik (registration_id=%s, xato=%s).",
            registration.pk,
            type(exc).__name__,
        )
        return False


@dataclass(frozen=True)
class ReminderStats:
    sent: int = 0
    failed: int = 0
    skipped: int = 0


def process_due_reminders(
    *,
    now: datetime | None = None,
    hours_before: int | None = None,
) -> ReminderStats:
    """Vaqti kelgan barcha tadbir eslatmalarini yuboradi va natija sonini qaytaradi."""
    sent = 0
    failed = 0
    registrations = get_due_reminder_registrations(now=now, hours_before=hours_before)
    for registration in registrations:
        if send_event_reminder(registration):
            registration.reminder_sent = True
            registration.save(update_fields=["reminder_sent"])
            sent += 1
        else:
            failed += 1
    return ReminderStats(sent=sent, failed=failed)
