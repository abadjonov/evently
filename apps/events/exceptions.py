from rest_framework import status
from rest_framework.exceptions import APIException


class BusinessError(APIException):
    """Biznes qoida buzilganda {"detail": "...", "code": "..."} formatida 400 qaytaradi."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Biznes qoida buzildi."
    default_code = "business_error"

    def __init__(self, detail: str | None = None, code: str | None = None) -> None:
        resolved_detail = detail or self.default_detail
        resolved_code = code or self.default_code
        self.detail = {
            "detail": resolved_detail,
            "code": resolved_code,
        }
