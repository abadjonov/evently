from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.events.serializers import BusinessErrorSerializer
from apps.notifications import services
from apps.notifications.permissions import HasBotSecret
from apps.notifications.serializers import (
    TelegramConfirmResponseSerializer,
    TelegramConfirmSerializer,
    TelegramLinkSerializer,
)

TELEGRAM_LINK_EXAMPLE = OpenApiExample(
    "Telegram bog'lash havolasi",
    value={"link": "https://t.me/EventlyBot?start=Xk3pQ9vT2mLw8aR1"},
    response_only=True,
    status_codes=["200"],
)

TELEGRAM_CONFIRM_REQUEST_EXAMPLE = OpenApiExample(
    "Telegram bog'lashni tasdiqlash",
    value={"token": "Xk3pQ9vT2mLw8aR1", "chat_id": 123456789},
    request_only=True,
)

TELEGRAM_CONFIRM_ERROR_EXAMPLE = OpenApiExample(
    "Yaroqsiz token",
    value={"detail": "Bog'lash tokeni yaroqsiz yoki eskirgan.", "code": "invalid_token"},
    response_only=True,
    status_codes=["400"],
)


class TelegramLinkView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        tags=["telegram"],
        summary="Telegram hisobini bog'lash havolasini olish",
        description=(
            "Joriy foydalanuvchi uchun tasodifiy bog'lash tokenini yaratib saqlaydi "
            "va Telegram botga o'tish havolasini qaytaradi."
        ),
        request=None,
        responses={
            200: TelegramLinkSerializer,
            401: OpenApiResponse(description="Avtorizatsiya talab qilinadi"),
        },
        examples=[TELEGRAM_LINK_EXAMPLE],
    )
    def post(self, request: Request) -> Response:
        link = services.create_telegram_link(user=request.user)
        serializer = TelegramLinkSerializer({"link": link})
        return Response(serializer.data, status=status.HTTP_200_OK)


class TelegramConfirmView(APIView):
    # Bot JWT tokeni emas, faqat X-Bot-Secret header'i orqali avtorizatsiya qilinadi
    authentication_classes = ()
    permission_classes = (HasBotSecret,)

    @extend_schema(
        tags=["telegram"],
        auth=[],
        summary="Telegram hisobini tasdiqlash (faqat Bot)",
        description=(
            "Bot `/start <token>` buyrug'idan olingan token va `chat_id` ni yuboradi. "
            "Backend `telegram_chat_id` ni saqlaydi va bir martalik tokenni o'chiradi."
        ),
        parameters=[
            OpenApiParameter(
                name="X-Bot-Secret",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.HEADER,
                required=True,
                description="Bot va backend o'rtasidagi maxfiy kalit.",
            ),
        ],
        request=TelegramConfirmSerializer,
        responses={
            200: TelegramConfirmResponseSerializer,
            400: BusinessErrorSerializer,
            403: OpenApiResponse(description="X-Bot-Secret noto'g'ri yoki yuborilmagan"),
        },
        examples=[TELEGRAM_CONFIRM_REQUEST_EXAMPLE, TELEGRAM_CONFIRM_ERROR_EXAMPLE],
    )
    def post(self, request: Request) -> Response:
        serializer = TelegramConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.confirm_telegram_link(
            token=serializer.validated_data["token"],
            chat_id=serializer.validated_data["chat_id"],
        )
        response_serializer = TelegramConfirmResponseSerializer(
            {"detail": "Telegram hisobi muvaffaqiyatli bog'landi.", "email": user.email}
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)
