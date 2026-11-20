import pytest
from django.test import override_settings
from rest_framework import status

TELEGRAM_LINK_URL = "/api/v1/telegram/link/"


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
