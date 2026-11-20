from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.utils import timezone
from rest_framework import status

from apps.events.models import Event, Registration
from apps.users.models import User

EVENTS_URL = "/api/v1/events/"


def _create_open_event(admin_user, capacity: int | None = 10) -> Event:
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
def test_user_can_register_for_open_event(api_client, user, admin_user):
    event = _create_open_event(admin_user)
    api_client.force_authenticate(user=user)

    response = api_client.post(f"{EVENTS_URL}{event.id}/register/")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["status"] == Registration.Status.ACTIVE
    assert response.data["event"]["id"] == event.id
    assert response.data["event"]["title"] == event.title
    assert response.data["event"]["location"] == event.location
    assert Registration.objects.filter(
        user=user,
        event=event,
        status=Registration.Status.ACTIVE,
    ).exists()


@pytest.mark.django_db
def test_anonymous_user_cannot_register_for_event(api_client, admin_user):
    event = _create_open_event(admin_user)

    response = api_client.post(f"{EVENTS_URL}{event.id}/register/")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert Registration.objects.count() == 0


@pytest.mark.django_db
def test_register_nonexistent_event_returns_404(api_client, user):
    api_client.force_authenticate(user=user)

    response = api_client.post(f"{EVENTS_URL}99999/register/")

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_user_cannot_register_twice_for_same_event(api_client, user, admin_user):
    event = _create_open_event(admin_user)
    api_client.force_authenticate(user=user)

    first_resp = api_client.post(f"{EVENTS_URL}{event.id}/register/")
    assert first_resp.status_code == status.HTTP_201_CREATED

    second_resp = api_client.post(f"{EVENTS_URL}{event.id}/register/")
    assert second_resp.status_code == status.HTTP_400_BAD_REQUEST
    assert second_resp.data["code"] == "already_registered"
    assert "detail" in second_resp.data


@pytest.mark.django_db
def test_cannot_register_for_full_closed_or_started_event(api_client, user, admin_user):
    now = timezone.now()
    full_event = _create_open_event(admin_user, capacity=1)
    Registration.objects.create(
        user=admin_user,
        event=full_event,
        status=Registration.Status.ACTIVE,
    )

    closed_event = _create_open_event(admin_user)
    closed_event.status = Event.Status.CLOSED
    closed_event.save(update_fields=["status"])

    started_event = Event.objects.create(
        title="Boshlangan tadbir",
        description="Tavsif",
        event_type=Event.EventType.SEMINAR,
        location="Toshkent",
        start_at=now - timedelta(hours=1),
        end_at=now + timedelta(hours=1),
        capacity=10,
        created_by=admin_user,
    )

    api_client.force_authenticate(user=user)

    full_resp = api_client.post(f"{EVENTS_URL}{full_event.id}/register/")
    assert full_resp.status_code == status.HTTP_400_BAD_REQUEST
    assert full_resp.data["code"] == "event_full"

    closed_resp = api_client.post(f"{EVENTS_URL}{closed_event.id}/register/")
    assert closed_resp.status_code == status.HTTP_400_BAD_REQUEST
    assert closed_resp.data["code"] == "event_closed"

    started_resp = api_client.post(f"{EVENTS_URL}{started_event.id}/register/")
    assert started_resp.status_code == status.HTTP_400_BAD_REQUEST
    assert started_resp.data["code"] == "event_started"


@pytest.mark.django_db
def test_cannot_reduce_capacity_below_active_registrations(api_client, user, admin_user):
    event = _create_open_event(admin_user, capacity=5)
    Registration.objects.create(user=user, event=event, status=Registration.Status.ACTIVE)
    Registration.objects.create(
        user=admin_user,
        event=event,
        status=Registration.Status.ACTIVE,
    )

    api_client.force_authenticate(user=admin_user)
    response = api_client.patch(
        f"{EVENTS_URL}{event.id}/",
        {"capacity": 1},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "capacity_too_low"
    event.refresh_from_db()
    assert event.capacity == 5


@pytest.mark.django_db
def test_unregister_frees_seat_and_reregister_reactivates_record(api_client, user, admin_user):
    event = _create_open_event(admin_user, capacity=1)
    api_client.force_authenticate(user=user)

    reg_resp = api_client.post(f"{EVENTS_URL}{event.id}/register/")
    assert reg_resp.status_code == status.HTTP_201_CREATED
    first_id = reg_resp.data["id"]

    unreg_resp = api_client.post(f"{EVENTS_URL}{event.id}/unregister/")
    assert unreg_resp.status_code == status.HTTP_200_OK
    assert unreg_resp.data["status"] == Registration.Status.CANCELLED

    detail_resp = api_client.get(f"{EVENTS_URL}{event.id}/")
    assert detail_resp.data["available_seats"] == 1

    rereg_resp = api_client.post(f"{EVENTS_URL}{event.id}/register/")
    assert rereg_resp.status_code == status.HTTP_201_CREATED
    assert rereg_resp.data["id"] == first_id
    assert rereg_resp.data["status"] == Registration.Status.ACTIVE
    assert Registration.objects.filter(user=user, event=event).count() == 1
    assert Registration.objects.get(id=first_id).cancelled_at is None


@pytest.mark.django_db
def test_cannot_unregister_from_started_or_unregistered_event(api_client, user, admin_user):
    now = timezone.now()
    open_event = _create_open_event(admin_user)
    api_client.force_authenticate(user=user)

    not_reg_resp = api_client.post(f"{EVENTS_URL}{open_event.id}/unregister/")
    assert not_reg_resp.status_code == status.HTTP_400_BAD_REQUEST
    assert not_reg_resp.data["code"] == "not_registered"

    started_event = Event.objects.create(
        title="Boshlangan",
        description="Tavsif",
        event_type=Event.EventType.SEMINAR,
        location="Toshkent",
        start_at=now - timedelta(hours=1),
        end_at=now + timedelta(hours=2),
        created_by=admin_user,
    )
    Registration.objects.create(
        user=user,
        event=started_event,
        status=Registration.Status.ACTIVE,
    )

    started_resp = api_client.post(f"{EVENTS_URL}{started_event.id}/unregister/")
    assert started_resp.status_code == status.HTTP_400_BAD_REQUEST
    assert started_resp.data["code"] == "event_started"


@pytest.mark.django_db
def test_user_sees_only_own_registrations(api_client, user, admin_user):
    ev1 = _create_open_event(admin_user)
    ev2 = _create_open_event(admin_user)
    Registration.objects.create(user=user, event=ev1, status=Registration.Status.ACTIVE)
    Registration.objects.create(user=user, event=ev2, status=Registration.Status.CANCELLED)
    Registration.objects.create(user=admin_user, event=ev1, status=Registration.Status.ACTIVE)

    api_client.force_authenticate(user=user)
    all_resp = api_client.get("/api/v1/me/registrations/")
    assert all_resp.status_code == status.HTTP_200_OK
    assert all_resp.data["count"] == 2

    active_resp = api_client.get("/api/v1/me/registrations/?status=active")
    assert active_resp.data["count"] == 1
    assert active_resp.data["results"][0]["event"]["id"] == ev1.id


@pytest.mark.django_db
def test_regular_user_cannot_view_participants_or_close_event(api_client, user, admin_user):
    event = _create_open_event(admin_user)
    Registration.objects.create(user=user, event=event, status=Registration.Status.ACTIVE)
    Registration.objects.create(
        user=admin_user,
        event=event,
        status=Registration.Status.CANCELLED,
    )

    api_client.force_authenticate(user=user)
    part_forbidden = api_client.get(f"{EVENTS_URL}{event.id}/participants/")
    assert part_forbidden.status_code == status.HTTP_403_FORBIDDEN

    close_forbidden = api_client.post(f"{EVENTS_URL}{event.id}/close/")
    assert close_forbidden.status_code == status.HTTP_403_FORBIDDEN

    api_client.force_authenticate(user=admin_user)
    part_ok = api_client.get(f"{EVENTS_URL}{event.id}/participants/")
    assert part_ok.status_code == status.HTTP_200_OK
    assert part_ok.data["count"] == 1
    assert part_ok.data["results"][0]["email"] == user.email


@pytest.mark.django_db
def test_cannot_register_after_admin_closes_event(api_client, user, admin_user):
    event = _create_open_event(admin_user)

    api_client.force_authenticate(user=admin_user)
    close_resp = api_client.post(f"{EVENTS_URL}{event.id}/close/")
    assert close_resp.status_code == status.HTTP_200_OK
    assert close_resp.data["status"] == Event.Status.CLOSED

    api_client.force_authenticate(user=user)
    reg_resp = api_client.post(f"{EVENTS_URL}{event.id}/register/")
    assert reg_resp.status_code == status.HTTP_400_BAD_REQUEST
    assert reg_resp.data["code"] == "event_closed"


@pytest.mark.django_db
def test_anonymous_user_gets_401_on_unregister_and_my_registrations(api_client, admin_user):
    event = _create_open_event(admin_user)

    assert api_client.post(f"{EVENTS_URL}{event.id}/unregister/").status_code == 401
    assert api_client.get("/api/v1/me/registrations/").status_code == 401


@pytest.mark.django_db
def test_registration_unique_constraint_enforced_at_db_level(user, admin_user):
    event = _create_open_event(admin_user)
    Registration.objects.create(user=user, event=event)

    # BR-1: Servis chetlab o'tilsa ham DB UniqueConstraint takroriy yozuvni bloklaydi
    with pytest.raises(IntegrityError):
        Registration.objects.create(user=user, event=event)


@pytest.mark.django_db
def test_unlimited_capacity_event_allows_multiple_registrations(api_client, user, admin_user):
    event = _create_open_event(admin_user, capacity=None)

    api_client.force_authenticate(user=user)
    first_resp = api_client.post(f"{EVENTS_URL}{event.id}/register/")
    assert first_resp.status_code == status.HTTP_201_CREATED

    api_client.force_authenticate(user=admin_user)
    second_resp = api_client.post(f"{EVENTS_URL}{event.id}/register/")
    assert second_resp.status_code == status.HTTP_201_CREATED
    assert Registration.objects.filter(event=event, status=Registration.Status.ACTIVE).count() == 2


@pytest.mark.django_db
def test_participants_list_no_n_plus_one_queries(
    api_client,
    admin_user,
    django_assert_num_queries,
):
    event = _create_open_event(admin_user, capacity=50)
    for idx in range(2):
        participant = User.objects.create_user(
            email=f"part{idx}@example.com",
            password="StrongPassword123!",
            first_name=f"User{idx}",
        )
        Registration.objects.create(user=participant, event=event)

    api_client.force_authenticate(user=admin_user)
    with django_assert_num_queries(3):
        resp_2 = api_client.get(f"{EVENTS_URL}{event.id}/participants/")
        assert resp_2.status_code == status.HTTP_200_OK
        assert len(resp_2.data["results"]) == 2

    for idx in range(2, 8):
        participant = User.objects.create_user(
            email=f"part{idx}@example.com",
            password="StrongPassword123!",
            first_name=f"User{idx}",
        )
        Registration.objects.create(user=participant, event=event)

    with django_assert_num_queries(3):
        resp_8 = api_client.get(f"{EVENTS_URL}{event.id}/participants/")
        assert resp_8.status_code == status.HTTP_200_OK
        assert len(resp_8.data["results"]) == 8


@pytest.mark.django_db
def test_my_registrations_list_no_n_plus_one_queries(
    api_client,
    user,
    admin_user,
    django_assert_num_queries,
):
    for _ in range(2):
        Registration.objects.create(user=user, event=_create_open_event(admin_user))

    api_client.force_authenticate(user=user)
    with django_assert_num_queries(2):
        resp_2 = api_client.get("/api/v1/me/registrations/")
        assert resp_2.status_code == status.HTTP_200_OK
        assert len(resp_2.data["results"]) == 2

    for _ in range(6):
        Registration.objects.create(user=user, event=_create_open_event(admin_user))

    with django_assert_num_queries(2):
        resp_8 = api_client.get("/api/v1/me/registrations/")
        assert resp_8.status_code == status.HTTP_200_OK
        assert len(resp_8.data["results"]) == 8
