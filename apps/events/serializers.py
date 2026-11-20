from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.events.exceptions import BusinessError
from apps.events.models import Event, Registration


class BusinessErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()
    code = serializers.CharField()


class EventBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = ("id", "title", "start_at", "location")
        read_only_fields = fields


class RegistrationSerializer(serializers.ModelSerializer):
    event = EventBriefSerializer(read_only=True)

    class Meta:
        model = Registration
        fields = ("id", "event", "status", "created_at")
        read_only_fields = fields


class MyRegistrationSerializer(serializers.ModelSerializer):
    event = EventBriefSerializer(read_only=True)

    class Meta:
        model = Registration
        fields = ("id", "event", "status", "created_at", "cancelled_at")
        read_only_fields = fields


class ParticipantSerializer(serializers.ModelSerializer):
    registration_id = serializers.IntegerField(source="id", read_only=True)
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    full_name = serializers.SerializerMethodField()
    email = serializers.EmailField(source="user.email", read_only=True)
    phone_number = serializers.CharField(source="user.phone_number", read_only=True)
    registered_at = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = Registration
        fields = (
            "registration_id",
            "user_id",
            "full_name",
            "email",
            "phone_number",
            "registered_at",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_full_name(self, obj: Registration) -> str:
        return f"{obj.user.first_name} {obj.user.last_name}".strip()


class BaseEventSerializer(serializers.ModelSerializer):
    registered_count = serializers.IntegerField(read_only=True, default=0)
    available_seats = serializers.SerializerMethodField()
    is_finished = serializers.SerializerMethodField()
    is_registered = serializers.BooleanField(read_only=True, default=False)

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_available_seats(self, obj: Event) -> int | None:
        # BR-2: capacity null bo'lsa bo'sh joylar soni ham cheklanmagan (null) bo'ladi
        if obj.capacity is None:
            return None
        registered_count = getattr(obj, "registered_count", 0)
        return max(obj.capacity - registered_count, 0)

    @extend_schema_field(serializers.BooleanField())
    def get_is_finished(self, obj: Event) -> bool:
        return bool(obj.end_at < timezone.now())


class EventListSerializer(BaseEventSerializer):
    """Ro'yxat endpointi uchun qisqa serializer."""

    class Meta:
        model = Event
        fields = (
            "id",
            "title",
            "event_type",
            "location",
            "start_at",
            "capacity",
            "registered_count",
            "available_seats",
            "status",
            "is_finished",
            "is_registered",
        )
        read_only_fields = fields


class EventDetailSerializer(BaseEventSerializer):
    class Meta:
        model = Event
        fields = (
            "id",
            "title",
            "description",
            "event_type",
            "location",
            "start_at",
            "end_at",
            "capacity",
            "registered_count",
            "available_seats",
            "status",
            "is_finished",
            "is_registered",
            "created_by",
            "created_at",
            "updated_at",
        )
        # status alohida close endpointi orqali o'zgaradi, created_by esa view'da avtomatik yoziladi
        read_only_fields = (
            "id",
            "registered_count",
            "available_seats",
            "status",
            "is_finished",
            "is_registered",
            "created_by",
            "created_at",
            "updated_at",
        )

    def validate_capacity(self, value: int | None) -> int | None:
        # PositiveIntegerField 0 ni ham qabul qilgani uchun kamida 1 ta joy bo'lishini tekshiramiz
        if value is not None and value < 1:
            raise serializers.ValidationError(
                "Joylar soni kamida 1 bo'lishi yoki cheklanmagan (null) qoldirilishi kerak."
            )

        # BR-9: Tahrirlashda capacity faol qatnashuvchilar sonidan kam bo'lmasligi shart
        if self.instance is not None and value is not None:
            active_count = self.instance.registrations.filter(
                status=Registration.Status.ACTIVE,
            ).count()
            if value < active_count:
                raise BusinessError(
                    detail="Joylar soni hozirgi qatnashuvchilar sonidan kam bo'lishi mumkin emas.",
                    code="capacity_too_low",
                )
        return value

    def validate(self, attrs: dict) -> dict:
        # BR-8: Yangi tadbir o'tgan sanaga yaratilmasligi shart
        if self.instance is None and "start_at" in attrs:
            if attrs["start_at"] <= timezone.now():
                raise serializers.ValidationError(
                    {"start_at": "Yangi tadbirning boshlanish vaqti kelajakda bo'lishi kerak."}
                )

        # BR-7: Create va partial update (PATCH) da ham end_at > start_at bo'lishi shart
        start_at = attrs.get("start_at", getattr(self.instance, "start_at", None))
        end_at = attrs.get("end_at", getattr(self.instance, "end_at", None))
        if start_at is not None and end_at is not None and end_at <= start_at:
            raise serializers.ValidationError(
                {"end_at": "Tugash vaqti boshlanish vaqtidan keyin bo'lishi kerak."}
            )

        return attrs
