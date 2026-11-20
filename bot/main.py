import asyncio
import logging

from aiogram import Bot, Dispatcher

from bot.api_client import BackendAPIClient
from bot.config import BotConfig, load_config
from bot.handlers import router

logger = logging.getLogger(__name__)


def build_dispatcher(config: BotConfig) -> Dispatcher:
    dp = Dispatcher()
    # Handlerlar global holatsiz ishlashi uchun API client workflow data orqali beriladi
    dp["api_client"] = BackendAPIClient(
        base_url=config.backend_api_url,
        bot_api_secret=config.bot_api_secret,
    )
    dp.include_router(router)
    return dp


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(asctime)s %(name)s: %(message)s",
    )
    config = load_config()
    bot = Bot(token=config.bot_token)
    dp = build_dispatcher(config)

    logger.info("Evently Telegram bot polling rejimida ishga tushmoqda...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
