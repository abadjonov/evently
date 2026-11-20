from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.notifications import services
from apps.notifications.serializers import TelegramLinkSerializer

TELEGRAM_LINK_EXAMPLE = OpenApiExample(
    "Telegram bog'lash havolasi",
    value={"link": "https://t.me/EventlyBot?start=Xk3pQ9vT2mLw8aR1"},
    response_only=True,
    status_codes=["200"],
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
