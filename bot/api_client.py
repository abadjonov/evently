import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_REQUEST_TIMEOUT = 10.0


@dataclass(frozen=True)
class ConfirmLinkResult:
    success: bool
    status_code: int | None = None
    detail: str = ""
    code: str = ""


def _parse_json_safe(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def _build_confirm_result(response: httpx.Response, chat_id: int) -> ConfirmLinkResult:
    data = _parse_json_safe(response)
    if response.status_code == 200:
        return ConfirmLinkResult(
            success=True,
            status_code=200,
            detail=str(data.get("detail", "")),
        )

    if response.status_code == 400:
        return ConfirmLinkResult(
            success=False,
            status_code=400,
            detail=str(data.get("detail", "Bog'lash tokeni yaroqsiz.")),
            code=str(data.get("code", "")),
        )

    logger.error(
        "Backend /telegram/confirm/ kutilmagan javob (chat_id=%s, status=%s).",
        chat_id,
        response.status_code,
    )
    return ConfirmLinkResult(
        success=False,
        status_code=response.status_code,
        detail="Backend server bilan bog'lanishda xatolik yuz berdi.",
    )


class BackendAPIClient:
    """Bot bazaga to'g'ridan-to'g'ri ulanmaydi, faqat backend API orqali ishlaydi."""

    def __init__(
        self,
        *,
        base_url: str,
        bot_api_secret: str,
        timeout: float = DEFAULT_REQUEST_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.bot_api_secret = bot_api_secret
        self.timeout = timeout

    async def confirm_telegram_link(self, *, token: str, chat_id: int) -> ConfirmLinkResult:
        url = f"{self.base_url}/telegram/confirm/"
        headers = {"X-Bot-Secret": self.bot_api_secret}
        payload = {"token": token, "chat_id": chat_id}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            logger.error(
                "Backend /telegram/confirm/ tarmoq xatosi (chat_id=%s, xato=%s).",
                chat_id,
                type(exc).__name__,
            )
            return ConfirmLinkResult(
                success=False,
                detail="Server bilan aloqa o'rnatilmadi. Birozdan so'ng urinib ko'ring.",
            )

        return _build_confirm_result(response, chat_id)
