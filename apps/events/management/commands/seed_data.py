from datetime import timedelta

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction
from django.utils import timezone

from apps.events.models import Event, Registration
from apps.users.models import User

SEED_ADMINS = [
    ("seed.admin1@evently.local", "Sardor", "Aliyev", "+998901110001"),
    ("seed.admin2@evently.local", "Dilnoza", "Karimova", "+998901110002"),
]

SEED_USERS = [
    ("seed.user1@evently.local", "Aziz", "Rahimov", "+998901230001"),
    ("seed.user2@evently.local", "Malika", "Tursunova", "+998901230002"),
    ("seed.user3@evently.local", "Jasur", "Qodirov", "+998901230003"),
    ("seed.user4@evently.local", "Madina", "Nazarova", "+998901230004"),
    ("seed.user5@evently.local", "Bekzod", "Usmonov", "+998901230005"),
    ("seed.user6@evently.local", "Zilola", "Xolmatova", "+998901230006"),
    ("seed.user7@evently.local", "Otabek", "Yuldashev", "+998901230007"),
    ("seed.user8@evently.local", "Sevara", "Ismoilova", "+998901230008"),
    ("seed.user9@evently.local", "Shohrux", "Mirzayev", "+998901230009"),
    ("seed.user10@evently.local", "Nilufar", "Saidova", "+998901230010"),
]

# (title, event_type, location, days_offset, duration_hours, capacity, status)
SEED_EVENTS = [
    (
        "Django REST Framework asoslari",
        Event.EventType.MASTERCLASS,
        "IT Park, 3-qavat, 301-xona",
        1,
        3,
        30,
        Event.Status.OPEN,
    ),
    (
        "PostgreSQL indekslar va optimizatsiya",
        Event.EventType.SEMINAR,
        "IT Park, 2-qavat, 204-xona",
        2,
        2,
        25,
        Event.Status.OPEN,
    ),
    (
        "Python Asyncio va aiogram 3 amaliyoti",
        Event.EventType.TRAINING,
        "Najot Ta'lim, Chilonzor filiali",
        3,
        4,
        20,
        Event.Status.OPEN,
    ),
    (
        "JWT autentifikatsiya va API xavfsizligi",
        Event.EventType.SEMINAR,
        "IT Park, 3-qavat, 305-xona",
        4,
        2,
        None,
        Event.Status.OPEN,
    ),
    (
        "Docker va container asoslari",
        Event.EventType.MASTERCLASS,
        "C-Space Coworking, 1-zal",
        5,
        3,
        15,
        Event.Status.OPEN,
    ),
    (
        "Pytest bilan avtomatik testlash",
        Event.EventType.TRAINING,
        "IT Park, 4-qavat, 402-xona",
        6,
        3,
        20,
        Event.Status.OPEN,
    ),
    (
        "Clean Architecture: Django servis qatlami",
        Event.EventType.SEMINAR,
        "PDP Academy, B-blok",
        7,
        2,
        40,
        Event.Status.OPEN,
    ),
    (
        "Git Flow va jamoaviy kod review",
        Event.EventType.MASTERCLASS,
        "IT Park, 2-qavat, 201-xona",
        8,
        2,
        None,
        Event.Status.OPEN,
    ),
    (
        "REST API hujjatlashtirish: OpenAPI va Swagger",
        Event.EventType.SEMINAR,
        "Impact.t Hub, Konferensiya zali",
        9,
        2,
        35,
        Event.Status.OPEN,
    ),
    (
        "Backend tizimlarda race condition va tranzaksiyalar",
        Event.EventType.TRAINING,
        "IT Park, 3-qavat, 301-xona",
        10,
        3,
        18,
        Event.Status.OPEN,
    ),
    (
        "Redis caching strategiyalari",
        Event.EventType.MASTERCLASS,
        "Astrum IT Academy, 2-zal",
        12,
        3,
        25,
        Event.Status.OPEN,
    ),
    (
        "Linux va Cron bilan fon vazifalari",
        Event.EventType.TRAINING,
        "IT Park, 1-qavat, 105-xona",
        14,
        2,
        20,
        Event.Status.CLOSED,
    ),
    (
        "Junior Backend suhbatga tayyorgarlik",
        Event.EventType.SEMINAR,
        "C-Space Coworking, Asosiy zal",
        15,
        2,
        50,
        Event.Status.CLOSED,
    ),
    (
        "Python 3.11 yangiliklari va typing",
        Event.EventType.SEMINAR,
        "IT Park, 2-qavat, 202-xona",
        -3,
        2,
        30,
        Event.Status.OPEN,
    ),
    (
        "SQL JOIN va N+1 muammosini yechish",
        Event.EventType.MASTERCLASS,
        "IT Park, 3-qavat, 303-xona",
        -1,
        3,
        20,
        Event.Status.OPEN,
    ),
]


def _seed_user_group(
    records: list[tuple[str, str, str, str]],
    *,
    role: str,
    is_staff: bool,
    password: str,
) -> tuple[list[User], int]:
    users: list[User] = []
    created_count = 0
    for email, first_name, last_name, phone in records:
        existing = User.objects.filter(email=email).first()
        if existing is not None:
            users.append(existing)
            continue
        user = User.objects.create_user(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone,
            role=role,
            is_staff=is_staff,
        )
        users.append(user)
        created_count += 1
    return users, created_count


def _seed_events(admins: list[User]) -> tuple[list[Event], int]:
    now = timezone.now().replace(minute=0, second=0, microsecond=0)
    events: list[Event] = []
    created_count = 0
    for idx, item in enumerate(SEED_EVENTS):
        title, event_type, location, days_offset, duration, capacity, status = item
        start_at = now + timedelta(days=days_offset, hours=2)
        event, created = Event.objects.get_or_create(
            title=title,
            defaults={
                "description": f"{title} bo'yicha amaliy o'quv mashg'uloti.",
                "event_type": event_type,
                "location": location,
                "start_at": start_at,
                "end_at": start_at + timedelta(hours=duration),
                "capacity": capacity,
                "status": status,
                "created_by": admins[idx % len(admins)],
            },
        )
        events.append(event)
        if created:
            created_count += 1
    return events, created_count


def _seed_registrations(users: list[User], events: list[Event]) -> int:
    open_upcoming = [e for e in events if e.status == Event.Status.OPEN][:5]
    created_count = 0
    for event_idx, event in enumerate(open_upcoming):
        for user in users[event_idx : event_idx + 3]:
            _, created = Registration.objects.get_or_create(
                user=user,
                event=event,
                defaults={"status": Registration.Status.ACTIVE},
            )
            if created:
                created_count += 1
    return created_count


class Command(BaseCommand):
    help = (
        "Lokal sinov va demo uchun namunaviy ma'lumotlarni yaratadi (2 admin, 10 user, 15 tadbir)."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--password",
            default="EventlyDemo123!",
            help="Seed foydalanuvchilari uchun lokal demo parol.",
        )

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        password: str = options["password"]
        admins, admins_created = _seed_user_group(
            SEED_ADMINS,
            role=User.Role.ADMIN,
            is_staff=True,
            password=password,
        )
        users, users_created = _seed_user_group(
            SEED_USERS,
            role=User.Role.USER,
            is_staff=False,
            password=password,
        )
        events, events_created = _seed_events(admins)
        regs_created = _seed_registrations(users, events)

        self.stdout.write(
            self.style.SUCCESS(
                "Seed yakunlandi — yangi yaratildi: "
                f"{admins_created} admin, {users_created} user, "
                f"{events_created} tadbir, {regs_created} yozilish."
            )
        )
