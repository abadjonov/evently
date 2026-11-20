from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.users.models import User
from apps.users.serializers import MeSerializer, RegisterSerializer

REGISTER_REQUEST_EXAMPLE = OpenApiExample(
    "Ro'yxatdan o'tish misoli",
    value={
        "email": "aziz@example.com",
        "password": "StrongPass123!",
        "password_confirm": "StrongPass123!",
        "first_name": "Aziz",
        "last_name": "Karimov",
        "phone_number": "+998901234567",
    },
    request_only=True,
)

REGISTER_RESPONSE_EXAMPLE = OpenApiExample(
    "Muvaffaqiyatli ro'yxatdan o'tish",
    value={
        "id": 7,
        "email": "aziz@example.com",
        "first_name": "Aziz",
        "last_name": "Karimov",
        "phone_number": "+998901234567",
        "role": "user",
    },
    response_only=True,
    status_codes=["201"],
)

LOGIN_REQUEST_EXAMPLE = OpenApiExample(
    "Login misoli",
    value={
        "email": "aziz@example.com",
        "password": "StrongPass123!",
    },
    request_only=True,
)


@extend_schema(
    tags=["auth"],
    summary="Yangi foydalanuvchi ro'yxatdan o'tishi",
    description=(
        "Email va parol orqali ro'yxatdan o'tish. "
        "Yangi foydalanuvchiga har doim 'user' roli beriladi."
    ),
    examples=[REGISTER_REQUEST_EXAMPLE, REGISTER_RESPONSE_EXAMPLE],
    responses={
        201: RegisterSerializer,
        400: OpenApiResponse(description="Validatsiya xatosi"),
    },
)
class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = (AllowAny,)


@extend_schema(
    tags=["auth"],
    summary="Tizimga kirish (JWT token olish)",
    description="Email va parol orqali `access` va `refresh` JWT tokenlarini qaytaradi.",
    examples=[LOGIN_REQUEST_EXAMPLE],
)
class LoginView(TokenObtainPairView):
    pass


@extend_schema(
    tags=["auth"],
    summary="Access tokenni yangilash",
    description="Yaroqli `refresh` token yordamida yangi `access` token oladi.",
)
class RefreshTokenView(TokenRefreshView):
    pass


@extend_schema_view(
    get=extend_schema(
        tags=["auth"],
        summary="Joriy foydalanuvchi profilini ko'rish",
        description="Avtorizatsiyadan o'tgan foydalanuvchi o'z profil ma'lumotlarini oladi.",
        responses={
            200: MeSerializer,
            401: OpenApiResponse(description="Token berilmagan yoki yaroqsiz"),
        },
    ),
    patch=extend_schema(
        tags=["auth"],
        summary="Joriy foydalanuvchi profilini tahrirlash",
        description=(
            "Foydalanuvchi o'zining `first_name`, `last_name` va `phone_number` "
            "maydonlarini yangilashi mumkin (`email` va `role` o'zgarmaydi)."
        ),
        responses={
            200: MeSerializer,
            400: OpenApiResponse(description="Validatsiya xatosi"),
            401: OpenApiResponse(description="Token berilmagan yoki yaroqsiz"),
        },
    ),
)
class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = MeSerializer
    permission_classes = (IsAuthenticated,)
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self) -> User:
        return self.request.user
