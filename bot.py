import asyncio
import html
import logging
import mimetypes
import shutil
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ChatType, ParseMode
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
    bot = Bot(
        token=BOT_TOKEN,
        session=AiohttpSession(api=telegram_api),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    logger.info(
        "Custom Telegram API server: %s (local_mode=%s)",
        TELEGRAM_API_BASE_URL,
        TELEGRAM_LOCAL_MODE,
    )
else:
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
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


def _is_heading(value: str) -> bool:
    letters = [char for char in value if char.isalpha()]
    if not letters or len(value) > 90:
        return False
    uppercase_ratio = sum(char.isupper() for char in letters) / len(letters)
    return uppercase_ratio >= 0.7


def format_ai_text(text: str) -> str:
    """Style AI headings while escaping all generated text for Telegram HTML."""
    rendered: list[str] = []
    for raw_line in text.replace("**", "").splitlines():
        line = raw_line.strip()
        if not line:
            rendered.append("")
            continue
        if line.startswith(("-", "•", "▪")):
            content = line.lstrip("-•▪ ").strip()
            rendered.append("• " + html.escape(content))
            continue
        if ":" in line:
            heading, body = line.split(":", 1)
            if _is_heading(heading.strip()):
                rendered.append(
                    f"<b>{html.escape(heading.strip())}:</b>{html.escape(body)}"
                )
                continue
        if _is_heading(line) and len(line) <= 72:
            rendered.append(f"<b>{html.escape(line)}</b>")
        else:
            rendered.append(html.escape(line))
    return "\n".join(rendered).strip()


async def answer_long(message: Message, text: str) -> None:
    for part in split_text(text, limit=3700):
        await message.answer(format_ai_text(part))

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
        await message.answer("<b>🔒 SHAXSIY CHAT</b>\n\nDubLab’dan xavfsiz foydalanish uchun botga shaxsiy chatda yozing.")
        return

    user = message.from_user
    if user is None:
        await message.answer("<b>⚠️ FOYDALANUVCHI ANIQLANMADI</b>\n\nQayta urinib ko‘ring.")
        return

    extension = safe_extension(filename, ".mp4")
    path = user_folder(user.id) / f"scene{extension}"
    status = await message.answer(
        "<b>🎬 VIDEO QABUL QILINDI</b>\n\n"
        "Faylni yuklayapman, keyin sahna va personaj emotsiyasini tahlil qilaman.\n"
        "<i>Bu biroz vaqt olishi mumkin.</i>"
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
        await status.edit_text("<b>✅ SAHNA TAHLILI TAYYOR</b>\n\nQuyida DubLab murabbiyining xulosasi.")
        await answer_long(message, result)
        await message.answer(
            "<b>🎙️ KEYINGI QADAM — SENING IJROING</b>\n\n"
            "O‘zing dublyaj qilgan ovozni voice yoki audio ko‘rinishida yubor. "
            "Men uni shu sahna bilan solishtirib baholayman.\n\n"
            "<i>Yangi video yuborsang, avvalgi sahna yangilanadi.</i>"
        )
    except ValueError as exc:
        await status.edit_text(f"<b>⚠️ TAHLILNI BAJARIB BO‘LMADI</b>\n\n{html.escape(str(exc))}")
    except Exception:
        logger.exception("Videoni tahlil qilishda xatolik")
        await status.edit_text(
            "<b>❌ VIDEO TAHLILIDA XATOLIK</b>\n\n"
            "Internet, AI API limiti yoki fayl formati bilan muammo bo‘lishi mumkin.\n"
            "Birozdan keyin qayta urinib ko‘r."
        )


async def process_audio(
    message: Message,
    file_id: str,
    filename: str | None,
    mime_type: str,
    file_size: int | None = None,
):
    if not private_chat_only(message):
        await message.answer("<b>🔒 SHAXSIY CHAT</b>\n\nDubLab’dan foydalanish uchun menga shaxsiy chatda yoz.")
        return

    user = message.from_user
    if user is None:
        await message.answer("<b>⚠️ FOYDALANUVCHI ANIQLANMADI</b>\n\nQayta urinib ko‘r.")
        return

    session = get_session(user.id)
    if not session or not session.get("video_path") or not Path(session["video_path"]).is_file():
        await message.answer(
            "<b>🎬 AVVAL SAHNANI TANLAYMIZ</b>\n\n"
            "Birinchi bo‘lib anime videosini yubor. Men undagi emotsiya va vaziyatni tahlil qilaman.\n\n"
            "Keyin o‘z dublyaj ovozingni yuborishing mumkin."
        )
        return

    extension = safe_extension(filename, ".ogg" if "ogg" in mime_type else ".mp3")
    voice_path = user_folder(user.id) / f"voice{extension}"
    status = await message.answer(
        "<b>🎧 OVOZ QABUL QILINDI</b>\n\n"
        "Ijroingni sahna emotsiyasi, ifoda, ritm va talaffuz bo‘yicha tekshiryapman.\n"
        "<i>Natija tayyor bo‘lgach shu yerga yuboraman.</i>"
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
        await status.edit_text("<b>✅ DUBLYAJ TAHLILI TAYYOR</b>\n\nQuyida ijroing bo‘yicha batafsil fikrlar.")
        await answer_long(message, result)
        await message.answer(
            "<b>🔁 YANA BIR URINISH?</b>\n\n"
            "Maslahatlarni sinab ko‘rib, yangi audio yubor. Uni shu sahna bilan yana solishtiraman."
        )
    except ValueError as exc:
        await status.edit_text(f"<b>⚠️ OVOZNI TEKSHIRIB BO‘LMADI</b>\n\n{html.escape(str(exc))}")
    except Exception:
        logger.exception("Ovoz tahlilida xatolik")
        await status.edit_text(
            "<b>❌ OVOZ TAHLILIDA XATOLIK</b>\n\n"
            "Audio faylni o‘qib bo‘lmadi yoki AI xizmati vaqtincha javob bermadi.\n"
            "Ovozli xabarni qayta yuborib ko‘r."
        )
    finally:
        voice_path.unlink(missing_ok=True)


@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "<b>🎙️ BEKIUZ DUBLAB</b>\n"
        "<i>Anime dublyaj uchun AI murabbiy</i>\n\n"
        "Xush kelibsan! Men sahna emotsiyasini tahlil qilaman va dublyaj ijroingni "
        "rivojlantirishga yordam beraman.\n\n"
        "<b>QANDAY ISHLAYDI?</b>\n"
        "🎬 <b>1. SAHNA TAHLILI</b> — anime videosini yubor. Men personaj, kayfiyat, "
        "vaziyat va videodagi ovozni tahlil qilaman.\n\n"
        "🎤 <b>2. OVOZINGNI YUBOR</b> — alohida voice yoki audio yubor.\n\n"
        "📊 <b>3. BAHO VA MASLAHAT</b> — emotsiya, ifoda, ritm, pauza va talaffuz "
        "bo‘yicha fikr hamda 100 ballik baho ol.\n\n"
        "<b>BUYRUQLAR</b>\n"
        "/help — foydalanish qo‘llanmasi\n"
        "/reset — joriy sahnani almashtirish\n\n"
        "<i>Avval anime videosini yuborishdan boshlaymiz. ✨</i>"
    )


@dp.message(Command("help"))
async def help_handler(message: Message):
    await message.answer(
        "<b>📘 BEKIUZ DUBLAB — QO‘LLANMA</b>\n\n"
        "<b>① VIDEO YUBOR</b>\n"
        "Anime sahnasini video ko‘rinishida yubor. Men kadrlar, personaj emotsiyasi "
        "va eshitiladigan nutqni tahlil qilaman.\n\n"
        "<b>② OVOZINGNI YUBOR</b>\n"
        "Video tahlilidan keyin o‘zing yozgan dublyajni voice yoki audio sifatida yubor.\n\n"
        "<b>③ NATIJANI OL</b>\n"
        "📊 Emotsiya mosligi\n"
        "🎙️ Ovoz ifodasi va niyat\n"
        "⏱️ Tezlik, ritm va pauzalar\n"
        "🗣️ Talaffuz va tushunarlilik\n"
        "🎬 Sinxronlik — faqat ishonchli o‘lchash mumkin bo‘lsa\n\n"
        "<b>FOYDALI BUYRUQLAR</b>\n"
        "/start — boshidan boshlash\n"
        "/reset — oldingi video sessiyasini tozalash\n"
        "/help — ushbu qo‘llanma\n\n"
        "<i>Eslatma: katta videolarni yuklash MTProto ulanishiga bog‘liq. "
        "Gemini va hosting limitlari ham amal qiladi.</i>"
    )


@dp.message(Command("reset"))
async def reset_handler(message: Message):
    user = message.from_user
    if user is None:
        await message.answer("<b>⚠️ FOYDALANUVCHI ANIQLANMADI</b>\n\nQayta urinib ko‘r.")
        return
    previous = delete_session(user.id)
    if previous:
        remove_local_file(previous.get("video_path"))
        await message.answer("<b>🧹 SAHNA TOZALANDI</b>\n\nYangi anime videosini yuborishing mumkin.")
    else:
        await message.answer("<b>📭 FAOL SAHNA YO‘Q</b>\n\nTahlilni boshlash uchun anime videosini yubor.")


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
            "<b>📎 FORMAT QO‘LLAB-QUVVATLANMAYDI</b>\n\n"
            "Video: MP4, MOV, WebM, MKV, AVI\n"
            "Audio: MP3, OGG, WAV, M4A, AAC, FLAC"
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
        "<b>🎬 AVVAL SAHNA, KEYIN OVOZ</b>\n\n"
        "Anime videosini yubor. Tahlildan keyin dublyaj ovozingni alohida jo‘natishing mumkin.\n\n"
        "/help — qo‘llanma"
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
