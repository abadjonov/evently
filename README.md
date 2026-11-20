# Evently Backend

O‘quv markazi uchun tadbirlarni (seminar, master-klass, trening) boshqarish platformasining **REST API** va **Telegram bot** backend qismi.

## Asosiy imkoniyatlar

- **Authentication (JWT):** email + parol orqali ro‘yxatdan o‘tish, login, access/refresh token yangilash, profilni ko‘rish va tahrirlash (`role` va `email` API orqali o‘zgarmaydi).
- **Tadbirlar boshqaruvi (Admin):** tadbir yaratish, qisman tahrirlash (`PATCH`), o‘chirish, yopish (`close`), faol qatnashuvchilar ro‘yxatini ko‘rish.
- **Ro‘yxatdan o‘tish va biznes qoidalar (BR-1…BR-10):**
  - Bir foydalanuvchi bir tadbirga faqat bir marta yoziladi (`UniqueConstraint(user, event)` + servis tekshiruvi); chiqib qayta yozilganda mavjud yozuv qayta `active` qilinadi.
  - Oxirgi bo‘sh joy uchun race condition himoyasi (`transaction.atomic()` + `Event.objects.select_for_update()`).
  - Barcha ro‘yxat endpointlarida N+1 yo‘q (`annotate`, `Exists`, `select_related`).
- **Telegram integratsiyasi:**
  - Deep-link orqali hisobni bog‘lash (`/telegram/link/` → bot `/start <token>` → `/telegram/confirm/` + `X-Bot-Secret`).
  - Ro‘yxatdan o‘tish tasdig‘i (foydalanuvchi va bog‘langan adminlarga — T1) `transaction.on_commit(...)` ichida yuboriladi; Telegram xatosi ro‘yxatdan o‘tishni buzmaydi.
  - Tadbir oldidan eslatmalar (T2) `send_event_reminders` management command va atomik `update()` dublikat himoyasi bilan ishlaydi.

## Texnologiyalar

| Texnologiya | Versiya | Vazifasi |
| --- | --- | --- |
| **Python** | 3.11+ | Asosiy dasturlash tili |
| **Django** | 5.1.15 | Web framework va ORM |
| **Django REST Framework** | 3.17.2 | REST API |
| **PostgreSQL** (`psycopg[binary]`) | 3.3.9 | Ma’lumotlar bazasi |
| **djangorestframework-simplejwt** | 5.5.1 | JWT authentication |
| **drf-spectacular** | 0.30.0 | OpenAPI 3 / Swagger UI hujjatlari |
| **django-filter** | 25.1 | Tadbir va ro‘yxatdan o‘tish filtrlari |
| **django-cors-headers** | 4.9.0 | Frontend uchun CORS sozlamalari |
| **django-environ** | 0.14.0 | `.env` muhit o‘zgaruvchilarini o‘qish |
| **httpx** | 0.28.1 | Telegram Bot API va bot → backend HTTP so‘rovlari |
| **aiogram** | 3.24.0 | Telegram bot (alohida jarayon) |
| **pytest / pytest-django** | 8.4.2 / 4.14.0 | Avtomatik testlar |
| **ruff** | 0.17.5 | Lint va kod formatlash |

## Loyiha tuzilmasi

```text
evently/
├── config/                    # Django sozlamalari, URL'lar, custom exception handler
├── apps/
│   ├── users/                 # Custom User modeli, JWT auth, IsAdmin/IsAdminOrReadOnly
│   ├── events/                # Event, Registration, services.py, filters.py, send_event_reminders
│   └── notifications/         # Telegram bog'lash endpointlari, HasBotSecret, T1/T2 servislari
├── bot/                       # aiogram 3 bot (bazaga ulanmaydi, faqat API orqali ishlaydi)
├── docs/TASK.md               # Dastlabki topshiriq hujjati
├── conftest.py                # Umumiy pytest fixture'lari
├── manage.py
├── pyproject.toml
├── requirements.txt
└── .env.example
```

## ER diagramma

```mermaid
erDiagram
    USER ||--o{ REGISTRATION : "yoziladi"
    EVENT ||--o{ REGISTRATION : "qatnashuvchilari"
    USER ||--o{ EVENT : "yaratadi (admin)"

    USER {
        bigint id PK
        string email UK
        string first_name
        string last_name
        string phone_number
        string role "admin | user"
        bigint telegram_chat_id UK "null bo'lishi mumkin"
        string telegram_link_token UK "null bo'lishi mumkin"
        datetime date_joined
    }

    EVENT {
        bigint id PK
        string title
        text description
        string event_type "seminar | masterclass | training"
        string location
        datetime start_at
        datetime end_at
        int capacity "null = cheklanmagan"
        string status "open | closed"
        bigint created_by FK
        datetime created_at
        datetime updated_at
    }

    REGISTRATION {
        bigint id PK
        bigint user_id FK "Unique(user_id, event_id)"
        bigint event_id FK "Unique(user_id, event_id)"
        string status "active | cancelled"
        bool reminder_sent
        datetime created_at
        datetime cancelled_at "null bo'lishi mumkin"
    }
```
