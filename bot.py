import asyncio
import logging
import mimetypes
import shutil
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from ai_service import analyze_video, evaluate_voice
from config import (
    BOT_TOKEN,
    TELEGRAM_API_BASE_URL,
    TELEGRAM_LOCAL_MODE,
    UPLOADS_DIR,
    validate_config,
)
from mtproto_download import (
    download_bot_file,
    is_mtproto_ready,
    start_mtproto,
    stop_mtproto,
)
from session_store import delete_session, get_session, remove_local_file, save_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("bekiuz-dublab")

validate_config()

if TELEGRAM_API_BASE_URL:
    telegram_api = TelegramAPIServer.from_base(
        TELEGRAM_API_BASE_URL,
        is_local=TELEGRAM_LOCAL_MODE,
    )
    bot = Bot(token=BOT_TOKEN, session=AiohttpSession(api=telegram_api))
    logger.info(
        "Custom Telegram API server: %s (local_mode=%s)",
        TELEGRAM_API_BASE_URL,
        TELEGRAM_LOCAL_MODE,
    )
else:
    bot = Bot(token=BOT_TOKEN)
    logger.info("Telegram cloud Bot API ishlatilmoqda.")

dp = Dispatcher()
BOT_API_DOWNLOAD_LIMIT = 20 * 1024 * 1024


def private_chat_only(message: Message) -> bool:
    return bool(message.chat and message.chat.type == ChatType.PRIVATE)


def split_text(text: str, limit: int = 3900) -> list[str]:
    text = text.strip()
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    while text:
        cut = min(limit, len(text))
        if cut < len(text):
            newline = text.rfind("\n", 0, cut)
            if newline > limit // 2:
                cut = newline
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()
    return [chunk for chunk in chunks if chunk]


async def answer_long(message: Message, text: str) -> None:
    for part in split_text(text):
        await message.answer(part)


async def download_to_path(
    message: Message,
    file_id: str,
    destination: Path,
    file_size: int | None = None,
):
    destination.parent.mkdir(parents=True, exist_ok=True)

    if not TELEGRAM_LOCAL_MODE and is_mtproto_ready():
        try:
            await download_bot_file(file_id, destination, file_size=file_size)
            logger.info(
                "Media MTProto orqali yuklandi (%s bytes).",
                destination.stat().st_size,
            )
            return
        except Exception as exc:
            logger.exception("MTProto orqali faylni yuklashda xatolik")
            if file_size and file_size > BOT_API_DOWNLOAD_LIMIT:
                raise ValueError(
                    "Katta fayl MTProto orqali yuklanmadi. TELEGRAM_API_ID/HASH "
                    "va bot sessiyasi to‘g‘ri sozlanganini tekshiring."
                ) from exc
            # Small files can still use the regular Bot API as a fallback.

    try:
        telegram_file = await bot.get_file(file_id)
    except TelegramBadRequest as exc:
        if "file is too big" in str(exc).lower():
            raise ValueError(
                "Bu fayl Telegram standart Bot API yuklab olish chegarasidan katta. "
                "20 MB dan katta fayllar uchun TELEGRAM_API_ID va TELEGRAM_API_HASH "
                "sozlanib, MTProto bot ulanishi yoqilgan bo‘lishi kerak."
            ) from exc
        raise

    if not telegram_file.file_path:
        raise RuntimeError("Telegram fayl manzilini qaytarmadi.")

    if TELEGRAM_LOCAL_MODE:
        # Local Bot API returns an absolute path on the server host.
        # The bot process must share that same filesystem.
        source = Path(telegram_file.file_path)
        if not source.is_absolute():
            raise RuntimeError(
                "Local Bot API mutlaq fayl yo‘lini qaytarmadi. "
                "Server --local rejimida ishlayotganini tekshiring."
            )
        if not source.is_file():
            raise RuntimeError(
                "Local Bot API fayl yo‘li bot ishlayotgan qurilmada topilmadi. "
                "Bot va Local Bot API server bir xil fayl tizimida ishlashi kerak."
            )
        shutil.copyfile(source, destination)
    else:
        await bot.download_file(telegram_file.file_path, destination=destination)

    if not destination.exists() or destination.stat().st_size == 0:
        raise RuntimeError("Fayl yuklab olinmadi. Qayta yuborib ko‘ring.")


def user_folder(user_id: int) -> Path:
    folder = UPLOADS_DIR / str(user_id)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def safe_extension(filename: str | None, fallback: str) -> str:
    if filename:
        suffix = Path(filename).suffix.lower()
        if suffix and len(suffix) <= 8 and suffix[1:].isalnum():
            return suffix
    return fallback


async def process_video(
    message: Message,
    file_id: str,
    filename: str,
    mime_type: str,
    file_size: int | None = None,
):
    if not private_chat_only(message):
        await message.answer("Maxfiylik uchun botdan shaxsiy chatda foydalaning.")
        return

    user = message.from_user
    if user is None:
        await message.answer("Foydalanuvchini aniqlab bo‘lmadi.")
        return

    extension = safe_extension(filename, ".mp4")
    path = user_folder(user.id) / f"scene{extension}"
    status = await message.answer(
        "🎬 Video qabul qilindi. Kadrlar, personaj emotsiyasi va videoning ichidagi "
        "ovozni tahlil qilyapman..."
    )

    try:
        await download_to_path(message, file_id, path, file_size=file_size)
        result = await asyncio.to_thread(analyze_video, str(path), mime_type)
        previous = get_session(user.id)
        if previous and previous.get("video_path") != str(path):
            remove_local_file(previous.get("video_path"))

        save_session(
            user.id,
            {
                "video_path": str(path),
                "video_name": filename,
                "video_mime": mime_type,
                "analysis": result,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        await status.edit_text("✅ Video tahlili tayyor. Natija:")
        await answer_long(message, result)
        await message.answer(
            "🎙️ Endi xohlasang, o‘zing dublyaj qilgan ovozni alohida voice yoki audio "
            "ko‘rinishida yubor. Uni shu video bilan solishtirib, baholayman.\n\n"
            "Yoki videoning o‘zidagi ovoz tahlili bilan kifoyalanishing mumkin. "
            "Yangi video yuborsang, oldingi sahna yangilanadi."
        )
    except ValueError as exc:
        await status.edit_text(f"⚠️ {exc}")
    except Exception:
        logger.exception("Videoni tahlil qilishda xatolik")
        await status.edit_text(
            "❌ Videoni tahlil qilib bo‘lmadi. Internet/API limiti yoki fayl formati "
            "bilan muammo bo‘lishi mumkin. Birozdan keyin qayta urinib ko‘r."
        )


async def process_audio(
    message: Message,
    file_id: str,
    filename: str | None,
    mime_type: str,
    file_size: int | None = None,
):
    if not private_chat_only(message):
        await message.answer("Maxfiylik uchun botdan shaxsiy chatda foydalaning.")
        return

    user = message.from_user
    if user is None:
        await message.answer("Foydalanuvchini aniqlab bo‘lmadi.")
        return

    session = get_session(user.id)
    if not session or not session.get("video_path") or not Path(session["video_path"]).is_file():
        await message.answer(
            "Avval anime videosini yubor. Men sahna emotsiyasini aniqlayman, "
            "keyin ovozingni shu video bilan solishtiraman."
        )
        return

    extension = safe_extension(filename, ".ogg" if "ogg" in mime_type else ".mp3")
    voice_path = user_folder(user.id) / f"voice{extension}"
    status = await message.answer(
        "🎧 Ovoz qabul qilindi. Uni videodagi vaziyat, emotsiya, ritm va talaffuz "
        "bilan solishtiryapman..."
    )

    try:
        await download_to_path(message, file_id, voice_path, file_size=file_size)
        result = await asyncio.to_thread(
            evaluate_voice,
            session["video_path"],
            str(voice_path),
            session.get("video_mime"),
            mime_type,
            session.get("analysis"),
        )
        await status.edit_text("✅ Ovoz tahlili yakunlandi. Natija:")
        await answer_long(message, result)
        await message.answer(
            "🔁 Yaxshilangan variantni yana yuborishing mumkin. Yangi video yubormaguningcha "
            "shu sahna bilan qayta solishtiraman."
        )
    except ValueError as exc:
        await status.edit_text(f"⚠️ {exc}")
    except Exception:
        logger.exception("Ovoz tahlilida xatolik")
        await status.edit_text(
            "❌ Ovozni tahlil qilib bo‘lmadi. Ovozli xabarni qayta yubor yoki "
            "birozdan keyin urinib ko‘r."
        )
    finally:
        voice_path.unlink(missing_ok=True)


@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "🎙️ Bekiuz DubLab ga xush kelibsan!\n\n"
        "Men anime dublyaj ijrosini tahlil qiladigan AI murabbiyman.\n\n"
        "1️⃣ Anime videosini yubor — sahna, personaj emotsiyasi va videodagi ovozni "
        "tahlil qilaman.\n"
        "2️⃣ Alohida ovozli xabar yubor — uni avvalgi video bilan solishtiraman.\n"
        "3️⃣ Emotsiya mosligi, ovoz ifodasi, tezlik, pauza va talaffuz bo‘yicha "
        "baholash hamda tavsiya olasan.\n\n"
        "Buyruqlar: /help — yordam, /reset — joriy videoni almashtirish."
    )


@dp.message(Command("help"))
async def help_handler(message: Message):
    await message.answer(
        "📘 Qanday foydalaniladi?\n\n"
        "🎬 Video yubor: bot undagi personaj va vaziyatni ko‘rib, kerakli emotsiyani "
        "va qanday gapirish kerakligini aytadi. Videodagi nutq eshitilsa, uning "
        "sahna bilan mosligini ham baholaydi.\n\n"
        "🎤 Keyin voice yoki audio yubor: bot alohida yozgan ovozingni shu video "
        "bilan taqqoslaydi.\n\n"
        "📊 Baholash: emotsiya, ovoz ifodasi, ritm/pauza, talaffuz va faqat "
        "o‘lchash mumkin bo‘lsa sinxronlik.\n\n"
        "📦 20 MB dan katta videolar uchun TELEGRAM_API_ID va TELEGRAM_API_HASH "
        "sozlangan bo‘lishi kerak. MTProto ishlamasa, Telegram standart 20 MB "
        "yuklab olish chegarasi amal qiladi."
    )


@dp.message(Command("reset"))
async def reset_handler(message: Message):
    user = message.from_user
    if user is None:
        await message.answer("Foydalanuvchini aniqlab bo‘lmadi.")
        return
    previous = delete_session(user.id)
    if previous:
        remove_local_file(previous.get("video_path"))
        await message.answer("🧹 Oldingi video sessiyasi tozalandi. Yangi video yubor.")
    else:
        await message.answer("Hozircha faol video yo‘q. Yangi video yuborishing mumkin.")


@dp.message(F.video)
async def video_handler(message: Message):
    video = message.video
    if video is None:
        return
    filename = video.file_name or "anime_clip.mp4"
    mime_type = video.mime_type or mimetypes.guess_type(filename)[0] or "video/mp4"
    await process_video(
        message, video.file_id, filename, mime_type, file_size=video.file_size
    )


@dp.message(F.document)
async def document_handler(message: Message):
    document = message.document
    if document is None:
        return

    mime_type = document.mime_type or mimetypes.guess_type(document.file_name or "")[0] or ""
    filename = document.file_name or "media"
    if mime_type.startswith("video/") or Path(filename).suffix.lower() in {
        ".mp4", ".mov", ".webm", ".mkv", ".avi"
    }:
        await process_video(
            message, document.file_id, filename, mime_type or "video/mp4",
            file_size=document.file_size,
        )
    elif mime_type.startswith("audio/") or Path(filename).suffix.lower() in {
        ".mp3", ".ogg", ".oga", ".wav", ".m4a", ".aac", ".flac"
    }:
        await process_audio(
            message, document.file_id, filename, mime_type or "audio/ogg",
            file_size=document.file_size,
        )
    else:
        await message.answer(
            "Video yoki audio fayl yubor. Formatlar: MP4, MOV, WebM, MP3, OGG, WAV."
        )


@dp.message(F.voice)
async def voice_handler(message: Message):
    voice = message.voice
    if voice is None:
        return
    await process_audio(
        message, voice.file_id, "voice.ogg", voice.mime_type or "audio/ogg",
        file_size=voice.file_size,
    )


@dp.message(F.audio)
async def audio_handler(message: Message):
    audio = message.audio
    if audio is None:
        return
    await process_audio(
        message, audio.file_id, audio.file_name or "voice.mp3",
        audio.mime_type or "audio/mpeg", file_size=audio.file_size,
    )


@dp.message(F.text)
async def text_fallback(message: Message):
    await message.answer(
        "Anime videosini yuborishdan boshlaymiz 🎬\n"
        "Video tahlilidan keyin alohida ovozli xabar yuborishing mumkin."
    )


async def main():
    logger.info("Bekiuz DubLab ishga tushmoqda...")
    await start_mtproto()
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await stop_mtproto()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to‘xtatildi.")
