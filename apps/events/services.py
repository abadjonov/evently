from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError, transaction
from django.db.models import BooleanField, Count, Exists, OuterRef, Q, QuerySet, Value
from django.utils import timezone

from apps.events.exceptions import BusinessError
from apps.events.models import Event, Registration
from apps.notifications import services as notification_services
from apps.users.models import User


def get_events_queryset(*, user: User | AnonymousUser | None) -> QuerySet[Event]:
    """Tadbirlar ro'yxatini N+1'siz hisoblanadigan maydonlar bilan qaytaradi."""
    if user and user.is_authenticated:
        is_registered_expr = Exists(
            Registration.objects.filter(
                event=OuterRef("pk"),
                user=user,
                status=Registration.Status.ACTIVE,
            )
        )
    else:
        is_registered_expr = Value(False, output_field=BooleanField())

    # N+1 muammosi bo'lmasligi uchun hisoblanadigan maydonlar bitta SQL so'rovda olinadi
    return Event.objects.annotate(
        registered_count=Count(
            "registrations",
            filter=Q(registrations__status=Registration.Status.ACTIVE),
        ),
        is_registered=is_registered_expr,
    ).order_by("start_at")


def get_active_participants_queryset(*, event: Event) -> QuerySet[Registration]:
    """Tadbirning faol qatnashuvchilarini user ma'lumotlari bilan bitta JOIN'da oladi."""
    return (
        event.registrations.filter(status=Registration.Status.ACTIVE)
        .select_related("user")
        .order_by("-created_at")
    )


def get_user_registrations_queryset(*, user: User) -> QuerySet[Registration]:
    """BR-10: Foydalanuvchining faqat o'z ro'yxatdan o'tishlarini event bilan oladi."""
    return Registration.objects.filter(user=user).select_related("event").order_by("-created_at")


def validate_capacity_not_below_active(*, event: Event, capacity: int) -> None:
    """BR-9: capacity qiymati faol qatnashuvchilar sonidan kam bo'lmasligini tekshiradi."""
    active_count = event.registrations.filter(status=Registration.Status.ACTIVE).count()
    if capacity < active_count:
        raise BusinessError(
            detail="Joylar soni hozirgi qatnashuvchilar sonidan kam bo'lishi mumkin emas.",
            code="capacity_too_low",
        )


def _validate_event_available(event: Event) -> None:
    if event.status == Event.Status.CLOSED:
        raise BusinessError(detail="Tadbir yopilgan.", code="event_closed")

    if event.start_at <= timezone.now():
        raise BusinessError(
            detail="Tadbir allaqachon boshlangan.",
            code="event_started",
        )


def _check_event_capacity(event: Event) -> None:
    if event.capacity is None:
        return
    active_count = Registration.objects.filter(
        event=event,
        status=Registration.Status.ACTIVE,
    ).count()
    if active_count >= event.capacity:
        raise BusinessError(detail="Bo'sh joy qolmagan.", code="event_full")


def _create_or_reactivate_registration(
    *,
    user: User,
    event: Event,
    existing: Registration | None,
) -> Registration:
    # BR-1: Ilgari chiqib ketgan bo'lsa yangi yozuv emas, mavjudini qayta active qilamiz
    if existing:
        existing.status = Registration.Status.ACTIVE
        existing.cancelled_at = None
        existing.save(update_fields=["status", "cancelled_at"])
        return existing

    try:
        with transaction.atomic():
            return Registration.objects.create(
                user=user,
                event=event,
                status=Registration.Status.ACTIVE,
            )
    except IntegrityError as exc:
        raise BusinessError(
            detail="Siz bu tadbirga allaqachon yozilgansiz.",
            code="already_registered",
        ) from exc


def register_for_event(*, user: User, event: Event) -> Registration:
    # Oxirgi bo'sh joy uchun race condition bo'lmasligi uchun tadbir qatorini bloklaymiz
    with transaction.atomic():
        locked_event = Event.objects.select_for_update().get(pk=event.pk)
        _validate_event_available(locked_event)

        existing = Registration.objects.filter(user=user, event=locked_event).first()
        if existing and existing.status == Registration.Status.ACTIVE:
            raise BusinessError(
                detail="Siz bu tadbirga allaqachon yozilgansiz.",
                code="already_registered",
            )

        _check_event_capacity(locked_event)
        registration = _create_or_reactivate_registration(
            user=user,
            event=locked_event,
            existing=existing,
        )

        # Xabarnoma faqat DB tranzaksiyasi commit bo'lgandan keyin yuboriladi
        reg_id = registration.id
        transaction.on_commit(lambda: notification_services.notify_registration(reg_id))
        return registration


def unregister_from_event(*, user: User, event: Event) -> Registration:
    with transaction.atomic():
        registration = (
            Registration.objects.select_for_update()
            .filter(
                user=user,
                event=event,
                status=Registration.Status.ACTIVE,
            )
            .first()
        )
        if registration is None:
            raise BusinessError(
                detail="Siz bu tadbirga yozilmagansiz.",
                code="not_registered",
            )

        # BR-6: Tadbir boshlangandan keyin undan chiqib bo'lmaydi
        if event.start_at <= timezone.now():
            raise BusinessError(
                detail="Tadbir allaqachon boshlangan.",
                code="event_started",
            )

        registration.status = Registration.Status.CANCELLED
        registration.cancelled_at = timezone.now()
        registration.save(update_fields=["status", "cancelled_at"])
        return registration


def close_event(*, event: Event) -> Event:
    # BR-5: Tadbirni yopish (yopilgan tadbirga hech kim yozila olmaydi)
    if event.status != Event.Status.CLOSED:
        event.status = Event.Status.CLOSED
        event.save(update_fields=["status", "updated_at"])
    return event
