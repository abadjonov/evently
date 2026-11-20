from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.events.exceptions import BusinessError
from apps.events.models import Event, Registration
from apps.users.models import User


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
                    event=locked_event,
                    status=Registration.Status.ACTIVE,
                )
        except IntegrityError as exc:
            raise BusinessError(
                detail="Siz bu tadbirga allaqachon yozilgansiz.",
                code="already_registered",
            ) from exc


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
