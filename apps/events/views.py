from django.db.models import BooleanField, Count, Exists, OuterRef, Q, QuerySet, Value
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import filters, generics, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.events import services
from apps.events.filters import EventFilter, RegistrationFilter
from apps.events.models import Event, Registration
from apps.events.serializers import (
    BusinessErrorSerializer,
    EventDetailSerializer,
    EventListSerializer,
    MyRegistrationSerializer,
    ParticipantSerializer,
    RegistrationSerializer,
)
from apps.users.permissions import IsAdmin, IsAdminOrReadOnly

EVENT_CREATE_EXAMPLE = OpenApiExample(
    "Tadbir yaratish misoli",
    value={
        "title": "Django REST Framework asoslari",
        "description": "API yaratish bo'yicha amaliy master-klass. Noutbuk olib keling.",
        "event_type": "masterclass",
        "location": "IT Park, 3-qavat, 301-xona",
        "start_at": "2026-12-05T14:00:00+05:00",
        "end_at": "2026-12-05T17:00:00+05:00",
        "capacity": 30,
    },
    request_only=True,
)

REGISTER_ERROR_EXAMPLES = [
    OpenApiExample(
        "Tadbir yopilgan",
        value={"detail": "Tadbir yopilgan.", "code": "event_closed"},
        response_only=True,
        status_codes=["400"],
    ),
    OpenApiExample(
        "Tadbir boshlangan",
        value={"detail": "Tadbir allaqachon boshlangan.", "code": "event_started"},
        response_only=True,
        status_codes=["400"],
    ),
    OpenApiExample(
        "Allaqachon yozilgan",
        value={
            "detail": "Siz bu tadbirga allaqachon yozilgansiz.",
            "code": "already_registered",
        },
        response_only=True,
        status_codes=["400"],
    ),
    OpenApiExample(
        "Joy qolmagan",
        value={"detail": "Bo'sh joy qolmagan.", "code": "event_full"},
        response_only=True,
        status_codes=["400"],
    ),
]

UNREGISTER_ERROR_EXAMPLES = [
    OpenApiExample(
        "Yozilmagan",
        value={"detail": "Siz bu tadbirga yozilmagansiz.", "code": "not_registered"},
        response_only=True,
        status_codes=["400"],
    ),
    OpenApiExample(
        "Tadbir boshlangan",
        value={"detail": "Tadbir allaqachon boshlangan.", "code": "event_started"},
        response_only=True,
        status_codes=["400"],
    ),
]

EVENT_LIST_PARAMETERS = [
    OpenApiParameter(
        name="page",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="Sahifa raqami (sahifada 10 ta tadbir).",
    ),
    OpenApiParameter(
        name="event_type",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        enum=[choice[0] for choice in Event.EventType.choices],
        description="Tadbir turi bo'yicha filter (`seminar`, `masterclass`, `training`).",
    ),
    OpenApiParameter(
        name="status",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        enum=[choice[0] for choice in Event.Status.choices],
        description="Tadbir holati bo'yicha filter (`open`, `closed`).",
    ),
    OpenApiParameter(
        name="upcoming",
        type=OpenApiTypes.BOOL,
        location=OpenApiParameter.QUERY,
        description="`true` bo'lsa faqat hali boshlanmagan (`start_at > hozir`) tadbirlar.",
    ),
    OpenApiParameter(
        name="search",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="`title` va `description` bo'yicha qidiruv.",
    ),
    OpenApiParameter(
        name="ordering",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        enum=["start_at", "-start_at", "created_at", "-created_at"],
        description="Saralash maydoni (`start_at`, `-start_at`, `created_at`).",
    ),
]


@extend_schema_view(
    list=extend_schema(
        tags=["events"],
        summary="Tadbirlar ro'yxati",
        description="Barcha tadbirlar ro'yxatini sahifalangan (10 tadan) holda qaytaradi.",
        parameters=EVENT_LIST_PARAMETERS,
        responses={200: EventListSerializer(many=True)},
    ),
    retrieve=extend_schema(
        tags=["events"],
        summary="Tadbir haqida batafsil ma'lumot",
        description="ID bo'yicha tadbirning barcha ma'lumotlarini qaytaradi.",
        responses={
            200: EventDetailSerializer,
            404: OpenApiResponse(description="Tadbir topilmadi"),
        },
    ),
    create=extend_schema(
        tags=["events"],
        summary="Yangi tadbir yaratish (faqat Admin)",
        description=(
            "Faqat `role='admin'` foydalanuvchilar yangi tadbir yarata oladi. "
            "`start_at` kelajakda va `end_at > start_at` bo'lishi shart."
        ),
        examples=[EVENT_CREATE_EXAMPLE],
        responses={
            201: EventDetailSerializer,
            400: OpenApiResponse(description="Validatsiya xatosi"),
            401: OpenApiResponse(description="Avtorizatsiya talab qilinadi"),
            403: OpenApiResponse(description="Faqat admin uchun ruxsat etilgan"),
        },
    ),
    partial_update=extend_schema(
        tags=["events"],
        summary="Tadbirni qisman tahrirlash (faqat Admin)",
        description="Faqat admin tadbir ma'lumotlarini `PATCH` orqali yangilay oladi.",
        responses={
            200: EventDetailSerializer,
            400: OpenApiResponse(description="Validatsiya yoki capacity_too_low xatosi"),
            401: OpenApiResponse(description="Avtorizatsiya talab qilinadi"),
            403: OpenApiResponse(description="Faqat admin uchun ruxsat etilgan"),
            404: OpenApiResponse(description="Tadbir topilmadi"),
        },
    ),
    destroy=extend_schema(
        tags=["events"],
        summary="Tadbirni o'chirish (faqat Admin)",
        description="Faqat admin tadbirni o'chira oladi.",
        responses={
            204: OpenApiResponse(description="Tadbir muvaffaqiyatli o'chirildi"),
            401: OpenApiResponse(description="Avtorizatsiya talab qilinadi"),
            403: OpenApiResponse(description="Faqat admin uchun ruxsat etilgan"),
            404: OpenApiResponse(description="Tadbir topilmadi"),
        },
    ),
)
class EventViewSet(viewsets.ModelViewSet):
    serializer_class = EventDetailSerializer
    permission_classes = (IsAdminOrReadOnly,)
    filter_backends = (
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    )
    filterset_class = EventFilter
    search_fields = ("title", "description")
    ordering_fields = ("start_at", "created_at")
    ordering = ("start_at",)
    # PUT o'rniga faqat qisman yangilash (PATCH) ruxsat etiladi
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet[Event]:
        user = self.request.user
        if user and user.is_authenticated:
            is_registered_expr = Exists(
                Registration.objects.filter(
                    event=OuterRef("pk"),
                    user=user,
                    status=Registration.Status.ACTIVE,
                )
            )
        else:
            is_registered_expr = Value(False, output_field=BooleanField())

        # N+1 muammosi bo'lmasligi uchun hisoblanadigan maydonlar bitta SQL so'rovda olinadi
        return Event.objects.annotate(
            registered_count=Count(
                "registrations",
                filter=Q(registrations__status=Registration.Status.ACTIVE),
            ),
            is_registered=is_registered_expr,
        ).order_by("start_at")

    def get_serializer_class(self) -> type[serializers.ModelSerializer]:
        if self.action == "list":
            return EventListSerializer
        if self.action in ("register", "unregister"):
            return RegistrationSerializer
        if self.action == "participants":
            return ParticipantSerializer
        return EventDetailSerializer

    def perform_create(self, serializer: EventDetailSerializer) -> None:
        serializer.save(created_by=self.request.user)

    @extend_schema(
        tags=["registrations"],
        summary="Tadbirga yozilish",
        description=(
            "Avtorizatsiyadan o'tgan foydalanuvchini tadbirga ro'yxatdan o'tkazadi. "
            "Xato kodlari: `event_closed`, `event_started`, `already_registered`, `event_full`."
        ),
        request=None,
        responses={
            201: RegistrationSerializer,
            400: BusinessErrorSerializer,
            401: OpenApiResponse(description="Avtorizatsiya talab qilinadi"),
            404: OpenApiResponse(description="Tadbir topilmadi"),
        },
        examples=REGISTER_ERROR_EXAMPLES,
    )
    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated],
    )
    def register(self, request: Request, pk: int | None = None) -> Response:
        event = self.get_object()
        registration = services.register_for_event(user=request.user, event=event)
        serializer = RegistrationSerializer(registration)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["registrations"],
        summary="Tadbirdan chiqish (ro'yxatdan chiqish)",
        description=(
            "Avtorizatsiyadan o'tgan foydalanuvchining tadbirdagi faol yozilishini bekor qiladi. "
            "Xato kodlari: `not_registered`, `event_started`."
        ),
        request=None,
        responses={
            200: RegistrationSerializer,
            400: BusinessErrorSerializer,
            401: OpenApiResponse(description="Avtorizatsiya talab qilinadi"),
            404: OpenApiResponse(description="Tadbir topilmadi"),
        },
        examples=UNREGISTER_ERROR_EXAMPLES,
    )
    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated],
    )
    def unregister(self, request: Request, pk: int | None = None) -> Response:
        event = self.get_object()
        registration = services.unregister_from_event(user=request.user, event=event)
        serializer = RegistrationSerializer(registration)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["events"],
        summary="Tadbirni yopish (faqat Admin)",
        description="Faqat admin tadbir holatini `closed` qilib yopa oladi.",
        request=None,
        responses={
            200: EventDetailSerializer,
            401: OpenApiResponse(description="Avtorizatsiya talab qilinadi"),
            403: OpenApiResponse(description="Faqat admin uchun ruxsat etilgan"),
            404: OpenApiResponse(description="Tadbir topilmadi"),
        },
    )
    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAdmin],
    )
    def close(self, request: Request, pk: int | None = None) -> Response:
        event = services.close_event(event=self.get_object())
        serializer = EventDetailSerializer(event, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["events"],
        summary="Tadbir qatnashuvchilari ro'yxati (faqat Admin)",
        description="Faqat admin tadbirga faol (`active`) yozilgan qatnashuvchilarni ko'ra oladi.",
        responses={
            200: ParticipantSerializer(many=True),
            401: OpenApiResponse(description="Avtorizatsiya talab qilinadi"),
            403: OpenApiResponse(description="Faqat admin uchun ruxsat etilgan"),
            404: OpenApiResponse(description="Tadbir topilmadi"),
        },
    )
    @action(
        detail=True,
        methods=["get"],
        permission_classes=[IsAdmin],
    )
    def participants(self, request: Request, pk: int | None = None) -> Response:
        event = self.get_object()
        # N+1 muammosi bo'lmasligi uchun user ma'lumotlari select_related bilan birga olinadi
        queryset = (
            event.registrations.filter(status=Registration.Status.ACTIVE)
            .select_related("user")
            .order_by("-created_at")
        )
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ParticipantSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = ParticipantSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=["registrations"],
    summary="O'zim yozilgan tadbirlar ro'yxati",
    description="Joriy foydalanuvchining faqat o'z ro'yxatdan o'tishlarini qaytaradi (BR-10).",
    parameters=[
        OpenApiParameter(
            name="status",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            enum=[choice[0] for choice in Registration.Status.choices],
            description="Ro'yxatdan o'tish holati bo'yicha filter (`active`, `cancelled`).",
        ),
    ],
    responses={
        200: MyRegistrationSerializer(many=True),
        401: OpenApiResponse(description="Avtorizatsiya talab qilinadi"),
    },
)
class MyRegistrationListView(generics.ListAPIView):
    serializer_class = MyRegistrationSerializer
    permission_classes = (IsAuthenticated,)
    filter_backends = (DjangoFilterBackend,)
    filterset_class = RegistrationFilter

    def get_queryset(self) -> QuerySet[Registration]:
        # BR-10: Foydalanuvchi faqat o'zining registration'larini ko'radi
        return (
            Registration.objects.filter(user=self.request.user)
            .select_related("event")
            .order_by("-created_at")
        )
