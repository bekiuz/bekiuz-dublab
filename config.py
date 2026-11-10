import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()

DATA_DIR = Path(os.getenv("DATA_DIR", "data")).expanduser()
UPLOADS_DIR = DATA_DIR / "uploads"
SESSIONS_FILE = DATA_DIR / "sessions.json"

try:
    MAX_MEDIA_MB = max(1, min(18, int(os.getenv("MAX_MEDIA_MB", "18"))))
except ValueError:
    MAX_MEDIA_MB = 18

MAX_MEDIA_BYTES = MAX_MEDIA_MB * 1024 * 1024


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

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
