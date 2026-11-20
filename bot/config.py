from dataclasses import dataclass
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class BotConfig:
    bot_token: str
    bot_api_secret: str
    backend_api_url: str


def load_config() -> BotConfig:
    """Bot sozlamalarini loyiha .env faylidan Django'ga ulanmasdan o'qiydi."""
    env = environ.Env(
        TELEGRAM_BOT_TOKEN=(str, ""),
        BOT_API_SECRET=(str, ""),
        BACKEND_API_URL=(str, "http://localhost:8000/api/v1"),
    )
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        environ.Env.read_env(env_path)

    bot_token = env("TELEGRAM_BOT_TOKEN").strip()
    bot_api_secret = env("BOT_API_SECRET").strip()
    backend_api_url = env("BACKEND_API_URL").strip().rstrip("/")

    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN .env faylida sozlanmagan.")
    if not bot_api_secret:
        raise ValueError("BOT_API_SECRET .env faylida sozlanmagan.")

    return BotConfig(
        bot_token=bot_token,
        bot_api_secret=bot_api_secret,
        backend_api_url=backend_api_url,
    )
