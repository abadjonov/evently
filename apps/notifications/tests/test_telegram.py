import pytest
from django.test import override_settings
from rest_framework import status

TELEGRAM_LINK_URL = "/api/v1/telegram/link/"
TELEGRAM_CONFIRM_URL = "/api/v1/telegram/confirm/"


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
