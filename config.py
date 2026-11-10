import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()

# Telegram developer API credentials. These let Telethon connect as the bot
# account over MTProto; no personal phone session is stored by this feature.
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "").strip()
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "").strip()

# Optional self-hosted Telegram Local Bot API endpoint.
# Example: http://127.0.0.1:8081
TELEGRAM_API_BASE_URL = os.getenv("TELEGRAM_API_BASE_URL", "").strip().rstrip("/")
TELEGRAM_LOCAL_MODE = os.getenv("TELEGRAM_LOCAL_MODE", "false").strip().lower() in {
    "1", "true", "yes", "on"
}

DATA_DIR = Path(os.getenv("DATA_DIR", "data")).expanduser()
UPLOADS_DIR = DATA_DIR / "uploads"
SESSIONS_FILE = DATA_DIR / "sessions.json"


def validate_config() -> None:
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")

    if missing:
        names = ", ".join(missing)
        raise RuntimeError(
            f".env faylida quyidagi qiymatlar kiritilmagan: {names}. "
            "README.md dagi sozlash yo‘riqnomasini ko‘ring."
        )

    if bool(TELEGRAM_API_ID) != bool(TELEGRAM_API_HASH):
        raise RuntimeError(
            "Katta fayllar uchun TELEGRAM_API_ID va TELEGRAM_API_HASH ikkalasi ham kiritilishi kerak."
        )

    if TELEGRAM_API_ID and not TELEGRAM_API_ID.isdigit():
        raise RuntimeError("TELEGRAM_API_ID faqat raqamlardan iborat bo‘lishi kerak.")

    if TELEGRAM_LOCAL_MODE and not TELEGRAM_API_BASE_URL:
        raise RuntimeError(
            "TELEGRAM_LOCAL_MODE=true, lekin TELEGRAM_API_BASE_URL bo‘sh. "
            "Local Bot API server manzilini .env faylida kiriting."
        )

    if TELEGRAM_LOCAL_MODE and not TELEGRAM_API_ID:
        raise RuntimeError(
            "Local Bot API uchun TELEGRAM_API_ID va TELEGRAM_API_HASH kerak."
        )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
