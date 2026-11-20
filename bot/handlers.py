from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from bot.api_client import BackendAPIClient

router = Router()

LINK_SUCCESS_TEXT = (
    "✅ Hisobingiz muvaffaqiyatli bog‘landi! Endi tadbirlar haqida xabarnomalar olasiz."
)

LINK_GUIDE_TEXT = (
    "👋 Evently botiga xush kelibsiz!\n\n"
    "Telegram hisobingizni bog'lash uchun:\n"
    "1. Evently saytida hisobingizga kiring.\n"
    "2. Profil bo'limida \"Telegram bog'lash\" havolasini oling.\n"
    "3. Shu havola orqali botni ochib Start tugmasini bosing."
)

INVALID_TOKEN_TEXT = (
    "❌ Bog'lash havolasi yaroqsiz yoki eskirgan.\n\n"
    "Iltimos, Evently saytida yangi bog'lash havolasini oling va qaytadan urinib ko'ring."
)

ALREADY_LINKED_TEXT = "⚠️ Bu Telegram hisobi allaqachon boshqa foydalanuvchiga bog'langan."

HELP_TEXT = (
    "ℹ️ Evently boti sizga quyidagi xabarnomalarni yuboradi:\n"
    "• Tadbirga ro'yxatdan o'tganingizda tasdiqlash xabari\n"
    "• Tadbir boshlanishidan oldin eslatma\n\n"
    "Hisobingizni bog'lash uchun Evently saytidagi maxsus havola orqali /start yuboring."
)


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    command: CommandObject,
    api_client: BackendAPIClient,
) -> None:
    """Deep-link token bo'lsa hisobni bog'laydi, aks holda bog'lash yo'riqnomasini yuboradi."""
    token = (command.args or "").strip()
    if not token:
        await message.answer(LINK_GUIDE_TEXT)
        return

    result = await api_client.confirm_telegram_link(token=token, chat_id=message.chat.id)
    if result.success:
        await message.answer(LINK_SUCCESS_TEXT)
        return

    if result.code == "telegram_already_linked":
        await message.answer(ALREADY_LINKED_TEXT)
        return

    if result.code == "invalid_token" or result.status_code == 400:
        await message.answer(INVALID_TOKEN_TEXT)
        return

    await message.answer(result.detail or "Xatolik yuz berdi. Birozdan so'ng urinib ko'ring.")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Bot vazifasi va hisobni bog'lash haqida qisqa yo'riqnoma yuboradi."""
    await message.answer(HELP_TEXT)
