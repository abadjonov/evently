import logging
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from apps.events.models import Event, Registration
from apps.notifications.services import process_due_reminders
from apps.users.models import User


def _create_event(
    admin_user: User,
    *,
    hours_from_now: int,
    status: str = Event.Status.OPEN,
    title: str = "Django REST Framework asoslari",
) -> Event:
    start_at = timezone.now() + timedelta(hours=hours_from_now)
    return Event.objects.create(
        title=title,
        description="Amaliy master-klass",
        event_type=Event.EventType.MASTERCLASS,
        location="IT Park, 3-qavat, 301-xona",
        start_at=start_at,
        end_at=start_at + timedelta(hours=2),
        status=status,
        created_by=admin_user,
    )


@pytest.mark.django_db
@override_settings(REMINDER_HOURS_BEFORE=24)
def test_reminder_sent_only_once_when_command_runs_twice(user, admin_user):
    user.telegram_chat_id = 1001
    user.save(update_fields=["telegram_chat_id"])
    event = _create_event(admin_user, hours_from_now=5)
    registration = Registration.objects.create(
        user=user,
        event=event,
        status=Registration.Status.ACTIVE,
    )

    with patch("apps.notifications.services.send_message", return_value=True) as mock_send:
        first_out = StringIO()
        call_command("send_event_reminders", stdout=first_out)

        second_out = StringIO()
        call_command("send_event_reminders", stdout=second_out)

    assert mock_send.call_count == 1
    sent_chat_id, sent_text = mock_send.call_args.args
    assert sent_chat_id == 1001
    assert "⏰ Eslatma!" in sent_text
    assert event.title in sent_text
    assert event.location in sent_text

    registration.refresh_from_db()
    assert registration.reminder_sent is True
    assert "Eslatmalar yuborildi: 1, xatolik: 0." in first_out.getvalue()
    assert "Eslatmalar yuborildi: 0, xatolik: 0." in second_out.getvalue()


@pytest.mark.django_db
@override_settings(REMINDER_HOURS_BEFORE=24)
def test_atomic_update_skips_registration_already_claimed_by_parallel_cron(user, admin_user):
    user.telegram_chat_id = 1001
    user.save(update_fields=["telegram_chat_id"])
    event = _create_event(admin_user, hours_from_now=5)
    registration = Registration.objects.create(
        user=user,
        event=event,
        status=Registration.Status.ACTIVE,
        reminder_sent=True,
    )

    # Parallel cron yozuvni olib ulgurgan holatni modellashtiramiz
    with (
        patch(
            "apps.notifications.services.get_due_reminder_registrations",
            return_value=[registration],
        ),
        patch("apps.notifications.services.send_message", return_value=True) as mock_send,
    ):
        stats = process_due_reminders()

    assert stats.sent == 0
    assert stats.failed == 0
    assert stats.skipped == 1
    mock_send.assert_not_called()


@pytest.mark.django_db
@override_settings(REMINDER_HOURS_BEFORE=24)
def test_reminders_skip_far_cancelled_closed_started_and_unlinked_users(user, admin_user):
    user.telegram_chat_id = 1001
    user.save(update_fields=["telegram_chat_id"])
    cancelled_user = User.objects.create_user(
        email="cancelled@example.com",
        password="StrongPassword123!",
        telegram_chat_id=1002,
    )
    unlinked_user = User.objects.create_user(
        email="unlinked@example.com",
        password="StrongPassword123!",
    )

    due_event = _create_event(admin_user, hours_from_now=6, title="Yaqin ochiq tadbir")
    far_event = _create_event(admin_user, hours_from_now=48, title="Uzoq tadbir")
    started_event = _create_event(admin_user, hours_from_now=-1, title="Boshlangan tadbir")
    closed_event = _create_event(
        admin_user,
        hours_from_now=6,
        status=Event.Status.CLOSED,
        title="Yopilgan tadbir",
    )

    eligible = Registration.objects.create(user=user, event=due_event)
    skipped_regs = [
        Registration.objects.create(user=user, event=far_event),
        Registration.objects.create(user=user, event=started_event),
        Registration.objects.create(
            user=cancelled_user,
            event=due_event,
            status=Registration.Status.CANCELLED,
        ),
        Registration.objects.create(user=user, event=closed_event),
        Registration.objects.create(user=unlinked_user, event=due_event),
    ]

    with patch("apps.notifications.services.send_message", return_value=True) as mock_send:
        call_command("send_event_reminders", stdout=StringIO())

    assert mock_send.call_count == 1
    assert mock_send.call_args.args[0] == 1001
    assert "Yaqin ochiq tadbir" in mock_send.call_args.args[1]

    eligible.refresh_from_db()
    assert eligible.reminder_sent is True
    for reg in skipped_regs:
        reg.refresh_from_db()
        assert reg.reminder_sent is False


@pytest.mark.django_db
@override_settings(REMINDER_HOURS_BEFORE=24)
def test_telegram_error_does_not_stop_reminder_command(user, admin_user, caplog):
    user.telegram_chat_id = 1001
    user.save(update_fields=["telegram_chat_id"])
    second_user = User.objects.create_user(
        email="second@example.com",
        password="StrongPassword123!",
        telegram_chat_id=1002,
    )
    event = _create_event(admin_user, hours_from_now=4)
    first_reg = Registration.objects.create(user=user, event=event)
    second_reg = Registration.objects.create(user=second_user, event=event)

    out = StringIO()
    with (
        patch(
            "apps.notifications.services.send_message",
            side_effect=[RuntimeError("Telegram API uzildi"), True],
        ) as mock_send,
        caplog.at_level(logging.ERROR, logger="apps.notifications"),
    ):
        call_command("send_event_reminders", stdout=out)

    assert mock_send.call_count == 2
    first_reg.refresh_from_db()
    second_reg.refresh_from_db()
    # Xato bergan yozuv keyingi cron urinishida qayta yuborilishi uchun False qoladi
    assert first_reg.reminder_sent is False
    assert second_reg.reminder_sent is True
    assert "Eslatmalar yuborildi: 1, xatolik: 1." in out.getvalue()
    assert len(caplog.records) == 1
    assert "RuntimeError" in caplog.text
