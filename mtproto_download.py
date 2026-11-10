import asyncio
import logging
from pathlib import Path

from telethon import TelegramClient, utils

from config import BOT_TOKEN, DATA_DIR, TELEGRAM_API_HASH, TELEGRAM_API_ID

logger = logging.getLogger("bekiuz-dublab.mtproto")

_client: TelegramClient | None = None
_download_lock = asyncio.Lock()


def is_mtproto_ready() -> bool:
    return _client is not None and _client.is_connected()


async def start_mtproto() -> bool:
    """Connect the bot account over MTProto without a personal phone login."""
    global _client

    if not TELEGRAM_API_ID and not TELEGRAM_API_HASH:
        logger.info("MTProto yuklash o‘chiq: TELEGRAM_API_ID/HASH kiritilmagan.")
        return False

    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
        raise RuntimeError(
            "MTProto uchun TELEGRAM_API_ID va TELEGRAM_API_HASH ikkalasi ham kerak."
        )

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
        raise RuntimeError("Telethon sessiyasi bot akkaunti emas.")

    logger.info("MTProto bot ulanishi tayyor (@%s).", identity.username or identity.id)
    return True


async def stop_mtproto() -> None:
    global _client
    if _client is not None:
        await _client.disconnect()
        _client = None


async def _download_from_message(
    message_id: int,
    chat_id: int,
    destination: Path,
    file_size: int | None = None,
) -> bool:
    """Fetch the original incoming message by ID, then download its media.

    This avoids relying on Telethon's legacy Bot API file_id decoder.
    messages.getMessages is available to bot accounts; messages.getHistory is not.
    """
    if not is_mtproto_ready():
        return False

    original = await _client.get_messages(None, ids=int(message_id))
    if original is None:
        raise RuntimeError("MTProto xabar ID bo‘yicha asl xabarni topmadi.")

    # Only permit private-chat media; the Bot API handler enforces this too.
    original_chat_id = getattr(original, "chat_id", None)
    if original_chat_id is None or int(original_chat_id) != int(chat_id):
        raise RuntimeError(
            "MTProto topgan xabar kutilgan shaxsiy chatga tegishli emas."
        )

    if not getattr(original, "media", None):
        raise RuntimeError("Topilgan Telegram xabarida media mavjud emas.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)

    # Telegram ruxsat bergan eng katta 512 KB bo‘laklardan foydalanamiz.
    # Bu 128 KB standart bo‘laklarga nisbatan so‘rovlar sonini 4 baravar kamaytiradi.
    media = getattr(original, "document", None) or getattr(original, "photo", None)
    if media is None:
        raise RuntimeError("Telegram xabaridagi video/audio fayl turi aniqlanmadi.")
    dc_id, location = utils.get_input_location(media)
    await _client.download_file(
        location,
        file=str(destination),
        part_size_kb=512,
        file_size=file_size,
        dc_id=dc_id,
    )
    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError("MTProto asl xabardan media faylni yuklay olmadi.")

    return True


async def _download_from_legacy_file_id(
    file_id: str,
    destination: Path,
    file_size: int | None,
) -> bool:
    """Compatibility fallback for Bot API file_id values Telethon can decode."""
    media = utils.resolve_bot_file_id(file_id)
    if media is None:
        return False

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)

    dc_id, location = utils.get_input_location(media)
    if dc_id is None:
        return False

    await _client.download_file(
        location,
        file=str(destination),
        dc_id=dc_id,
        file_size=file_size if file_size and file_size > 0 else None,
        part_size_kb=512,
    )

    return destination.is_file() and destination.stat().st_size > 0


async def download_bot_file(
    file_id: str,
    destination: Path,
    file_size: int | None = None,
    message_id: int | None = None,
    chat_id: int | None = None,
) -> bool:
    """Download a bot-received media item through MTProto."""
    if not is_mtproto_ready():
        return False

    async with _download_lock:
        if message_id is not None and chat_id is not None:
            try:
                if await _download_from_message(message_id, chat_id, destination, file_size):
                    logger.info(
                        "Media asl xabar orqali MTProto'dan yuklandi (%s bytes).",
                        destination.stat().st_size,
                    )
                    return True
            except Exception:
                logger.exception(
                    "MTProto original message download failed "
                    "(chat_id=%s, message_id=%s).",
                    chat_id,
                    message_id,
                )
                # Try the legacy file_id route below if it is decodable.

        try:
            if await _download_from_legacy_file_id(file_id, destination, file_size):
                logger.info(
                    "Media legacy file_id orqali MTProto'dan yuklandi (%s bytes).",
                    destination.stat().st_size,
                )
                return True
        except Exception:
            logger.exception("Telethon legacy file_id yuklash usuli muvaffaqiyatsiz.")

    raise RuntimeError(
        "MTProto media faylni yuklay olmadi. Asl xabar yoki file_id usuli ishlamadi."
    )
