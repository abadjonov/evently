import logging
from datetime import timedelta
from unittest.mock import patch

import httpx
import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework import status

from apps.events.models import Event, Registration
from apps.notifications.services import send_message
from apps.users.models import User

TELEGRAM_LINK_URL = "/api/v1/telegram/link/"
TELEGRAM_CONFIRM_URL = "/api/v1/telegram/confirm/"


def _create_upcoming_event(admin_user: User, capacity: int | None = 10) -> Event:
    now = timezone.now()
    return Event.objects.create(
        title="Django REST Framework asoslari",
        description="Amaliy master-klass",
        event_type=Event.EventType.MASTERCLASS,
        location="IT Park, 3-qavat, 301-xona",
        start_at=now + timedelta(days=2),
        end_at=now + timedelta(days=2, hours=3),
        capacity=capacity,
        created_by=admin_user,
    )


@pytest.mark.django_db
def test_telegram_link_requires_authentication(api_client):
    response = api_client.post(TELEGRAM_LINK_URL)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
@override_settings(TELEGRAM_BOT_USERNAME="EventlyBot")
def test_telegram_link_creates_token_and_returns_url(api_client, user):
    api_client.force_authenticate(user=user)

    response = api_client.post(TELEGRAM_LINK_URL)

    assert response.status_code == status.HTTP_200_OK
    user.refresh_from_db()
    assert user.telegram_link_token
    assert response.data["link"] == f"https://t.me/EventlyBot?start={user.telegram_link_token}"


@pytest.mark.django_db
@override_settings(BOT_API_SECRET="super-secret")
def test_telegram_confirm_rejects_invalid_or_missing_bot_secret(api_client, user):
    user.telegram_link_token = "valid-token"
    user.save(update_fields=["telegram_link_token"])
    payload = {"token": "valid-token", "chat_id": 123456789}

    missing_resp = api_client.post(TELEGRAM_CONFIRM_URL, payload, format="json")
    assert missing_resp.status_code == status.HTTP_403_FORBIDDEN

    wrong_resp = api_client.post(
        TELEGRAM_CONFIRM_URL,
        payload,
        format="json",
        HTTP_X_BOT_SECRET="wrong-secret",
    )
    assert wrong_resp.status_code == status.HTTP_403_FORBIDDEN

    user.refresh_from_db()
    assert user.telegram_chat_id is None
    assert user.telegram_link_token == "valid-token"


@pytest.mark.django_db
@override_settings(BOT_API_SECRET="super-secret")
def test_telegram_confirm_saves_chat_id_and_clears_token(api_client, user):
    user.telegram_link_token = "valid-token"
    user.save(update_fields=["telegram_link_token"])
    payload = {"token": "valid-token", "chat_id": 123456789}

    response = api_client.post(
        TELEGRAM_CONFIRM_URL,
        payload,
        format="json",
        HTTP_X_BOT_SECRET="super-secret",
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["email"] == user.email

    user.refresh_from_db()
    assert user.telegram_chat_id == 123456789
    assert user.telegram_link_token is None

    # Bir martalik token o'chirilgani uchun qayta ishlatib bo'lmaydi
    reuse_resp = api_client.post(
        TELEGRAM_CONFIRM_URL,
        payload,
        format="json",
        HTTP_X_BOT_SECRET="super-secret",
    )
    assert reuse_resp.status_code == status.HTTP_400_BAD_REQUEST
    assert reuse_resp.data["code"] == "invalid_token"


@pytest.mark.django_db
def test_registration_calls_notify_after_commit(
    api_client,
    user,
    admin_user,
    django_capture_on_commit_callbacks,
):
    user.telegram_chat_id = 1001
    user.save(update_fields=["telegram_chat_id"])
    admin_user.telegram_chat_id = 2002
    admin_user.save(update_fields=["telegram_chat_id"])
    User.objects.create_user(
        email="unlinked-admin@example.com",
        password="StrongPassword123!",
        role=User.Role.ADMIN,
    )
    event = _create_upcoming_event(admin_user, capacity=10)
    api_client.force_authenticate(user=user)

    with patch("apps.notifications.services.send_message") as mock_send:
        with django_capture_on_commit_callbacks(execute=True) as callbacks:
            response = api_client.post(f"/api/v1/events/{event.id}/register/")
            assert response.status_code == status.HTTP_201_CREATED
            # Xabarnoma commit'dan oldin emas, faqat on_commit bosqichida yuborilishi kerak
            assert mock_send.call_count == 0

        assert len(callbacks) == 1
        assert mock_send.call_count == 2
        user_call, admin_call = mock_send.call_args_list
        assert user_call.args[0] == 1001
        assert "✅ Siz tadbirga muvaffaqiyatli yozildingiz!" in user_call.args[1]
        assert event.title in user_call.args[1]
        assert event.location in user_call.args[1]

        assert admin_call.args[0] == 2002
        assert "🆕 Yangi qatnashuvchi" in admin_call.args[1]
        assert "Test User (+998901234567)" in admin_call.args[1]
        assert "1 / 10" in admin_call.args[1]


@pytest.mark.django_db
def test_failed_registration_does_not_schedule_notify(
    api_client,
    user,
    admin_user,
    django_capture_on_commit_callbacks,
):
    user.telegram_chat_id = 1001
    user.save(update_fields=["telegram_chat_id"])
    event = _create_upcoming_event(admin_user, capacity=10)
    event.status = Event.Status.CLOSED
    event.save(update_fields=["status"])
    api_client.force_authenticate(user=user)

    with patch("apps.notifications.services.send_message") as mock_send:
        with django_capture_on_commit_callbacks(execute=True) as callbacks:
            response = api_client.post(f"/api/v1/events/{event.id}/register/")
            assert response.status_code == status.HTTP_400_BAD_REQUEST

        assert callbacks == []
        mock_send.assert_not_called()


@pytest.mark.django_db
def test_registration_succeeds_even_when_telegram_send_fails(
    api_client,
    user,
    admin_user,
    django_capture_on_commit_callbacks,
    caplog,
):
    user.telegram_chat_id = 1001
    user.save(update_fields=["telegram_chat_id"])
    admin_user.telegram_chat_id = 2002
    admin_user.save(update_fields=["telegram_chat_id"])
    event = _create_upcoming_event(admin_user, capacity=10)
    api_client.force_authenticate(user=user)

    with (
        patch(
            "apps.notifications.services.send_message",
            side_effect=RuntimeError("Telegram API ishlamayapti"),
        ) as mock_send,
        caplog.at_level(logging.ERROR, logger="apps.notifications"),
    ):
        with django_capture_on_commit_callbacks(execute=True):
            response = api_client.post(f"/api/v1/events/{event.id}/register/")

        assert response.status_code == status.HTTP_201_CREATED
        assert Registration.objects.filter(
            user=user,
            event=event,
            status=Registration.Status.ACTIVE,
        ).exists()
        assert mock_send.call_count == 2
        assert len(caplog.records) == 2
        assert "RuntimeError" in caplog.text


@override_settings(TELEGRAM_BOT_TOKEN="123456:TOP_SECRET_TOKEN")
def test_send_message_logs_error_without_exposing_token(caplog):
    with (
        patch(
            "apps.notifications.services.httpx.post",
            side_effect=httpx.TimeoutException("timeout"),
        ),
        caplog.at_level(logging.ERROR, logger="apps.notifications"),
    ):
        result = send_message(1001, "Salom")

    assert result is False
    assert len(caplog.records) == 1
    assert "TOP_SECRET_TOKEN" not in caplog.text
