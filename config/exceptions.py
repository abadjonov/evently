from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler

STATUS_DEFAULT_CODES: dict[int, str] = {
    401: "authentication_failed",
    403: "permission_denied",
    404: "not_found",
}


def custom_exception_handler(exc: Exception, context: dict) -> Response | None:
    """401/403/404 xatolarini ham yagona {"detail", "code"} formatiga keltiradi."""
    response = exception_handler(exc, context)
    if response is None:
        return None

    # 400 field validation xatolari DRF standart formatida qoladi (README 10.2)
    if response.status_code in STATUS_DEFAULT_CODES and isinstance(response.data, dict):
        default_code = STATUS_DEFAULT_CODES[response.status_code]
        if "detail" in response.data and "code" not in response.data:
            code = exc.get_codes() if isinstance(exc, APIException) else default_code
            response.data["code"] = code if isinstance(code, str) else default_code
        elif "detail" not in response.data:
            response.data = {
                "detail": str(response.data),
                "code": default_code,
            }

    return response
