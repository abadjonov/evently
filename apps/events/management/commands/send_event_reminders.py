from django.core.management.base import BaseCommand

from apps.notifications.services import process_due_reminders


class Command(BaseCommand):
    help = "Yaqinlashayotgan tadbirlar uchun Telegram eslatmalarini yuboradi."

    def handle(self, *args, **options) -> None:
        stats = process_due_reminders()
        self.stdout.write(
            self.style.SUCCESS(f"Eslatmalar yuborildi: {stats.sent}, xatolik: {stats.failed}.")
        )
