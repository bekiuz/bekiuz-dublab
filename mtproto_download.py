import asyncio
import logging
from pathlib import Path

from telethon import TelegramClient, utils
from telethon.tl.types import Document, Photo

from config import BOT_TOKEN, DATA_DIR, TELEGRAM_API_HASH, TELEGRAM_API_ID

logger = logging.getLogger("bekiuz-dublab.mtproto")

_client: TelegramClient | None = None
_download_lock = asyncio.Lock()


def is_mtproto_ready() -> bool:
    return _client is not None and _client.is_connected()


async def start_mtproto() -> bool:
    """Connect the same bot account over MTProto; no user phone login is used."""
    global _client

    if not TELEGRAM_API_ID and not TELEGRAM_API_HASH:
        logger.info("MTProto yuklash o‘chiq: TELEGRAM_API_ID/HASH kiritilmagan.")
        return False

    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
        raise RuntimeError("MTProto uchun TELEGRAM_API_ID va TELEGRAM_API_HASH ikkalasi ham kerak.")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    session_path = DATA_DIR / "dublab-mtproto-bot"

    _client = TelegramClient(
        str(session_path),
        int(TELEGRAM_API_ID),
        TELEGRAM_API_HASH,
        receive_updates=False,
    )
    await _client.start(bot_token=BOT_TOKEN)

    identity = await _client.get_me()
    if identity is None or not getattr(identity, "bot", False):
        await _client.disconnect()
        _client = None
        raise RuntimeError(
            "Telethon sessiyasi bot akkaunti emas. Yangi, alohida sessiya bilan qayta urinib ko‘ring."
        )

    logger.info("MTProto bot ulanishi tayyor (@%s).", identity.username or identity.id)
    return True


async def stop_mtproto() -> None:
    global _client
    if _client is not None:
        await _client.disconnect()
        _client = None


async def download_bot_file(
    file_id: str,
    destination: Path,
    file_size: int | None = None,
) -> bool:
    """Download a Bot API file_id directly through Telegram's MTProto file API."""
    if not is_mtproto_ready():
        return False

    media = utils.resolve_bot_file_id(file_id)
    if media is None or not isinstance(media, (Document, Photo)):
        raise RuntimeError("Telegram file_id MTProto formatiga aylantirilmadi.")

    dc_id, location = utils.get_input_location(media)
    if dc_id is None:
        raise RuntimeError("Telegram faylining data-center ma’lumoti topilmadi.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)

    async with _download_lock:
        await _client.download_file(
            location,
            file=str(destination),
            dc_id=dc_id,
            file_size=file_size if file_size and file_size > 0 else None,
        )

    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError("MTProto faylni yuklab olmadi.")

    return True
