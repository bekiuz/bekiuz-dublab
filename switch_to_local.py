import asyncio
import os
import socket
from urllib.parse import urlsplit

from aiogram import Bot
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
LOCAL_API_URL = os.getenv("TELEGRAM_API_BASE_URL", "").strip()
LOCAL_MODE = os.getenv("TELEGRAM_LOCAL_MODE", "false").strip().lower() in {
    "1", "true", "yes", "on"
}


async def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN .env faylida topilmadi.")
    if not LOCAL_MODE or not LOCAL_API_URL:
        raise SystemExit(
            "Avval .env ichida TELEGRAM_API_BASE_URL va TELEGRAM_LOCAL_MODE=true "
            "sozlamalarini kiriting."
        )

    parsed = urlsplit(LOCAL_API_URL)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SystemExit("TELEGRAM_API_BASE_URL noto‘g‘ri. Masalan: http://127.0.0.1:8081")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    # Confirm that the local server is listening before logging out from Telegram cloud.
    try:
        with socket.create_connection((parsed.hostname, port), timeout=3):
            pass
    except OSError as exc:
        raise SystemExit(
            "Local Bot API server manzili ochilmadi. Avval telegram-bot-api serverini "
            "ishga tushiring; cloud API'dan hali logout qilinmadi."
        ) from exc

    print("Local Bot API server porti javob beryapti.")
    print("Diqqat: keyingi qadam botni Telegram standart cloud API'dan chiqaradi.")
    print("Buni faqat Local Bot API serverni ishlatishga tayyor bo‘lsangiz bajaring.")
    confirmation = input("Davom etish uchun LOGOUT deb yozing: ").strip()
    if confirmation != "LOGOUT":
        print("Bekor qilindi. Bot cloud API'da qoladi.")
        return

    bot = Bot(token=BOT_TOKEN)
    try:
        me = await bot.get_me()
        print(f"Bot tekshirildi: @{me.username or me.id}")
        await bot.log_out()
        print(
            "✅ Cloud Bot API'dan chiqildi. Endi python bot.py buyrug‘i "
            "orqali Local Bot API serverga ulanadi."
        )
        print("Cloud API'ga qayta kirish uchun Telegram 10 daqiqalik kutish oynasini qo‘yadi.")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
