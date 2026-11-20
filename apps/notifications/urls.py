from django.urls import path

from apps.notifications.views import TelegramLinkView

urlpatterns = [
    path("telegram/link/", TelegramLinkView.as_view(), name="telegram-link"),
]
