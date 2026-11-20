from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.events.views import EventViewSet, MyRegistrationListView

router = DefaultRouter()
router.register(r"events", EventViewSet, basename="event")

urlpatterns = [
    path("me/registrations/", MyRegistrationListView.as_view(), name="my-registrations"),
    *router.urls,
]
