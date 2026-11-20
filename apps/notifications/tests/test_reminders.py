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
