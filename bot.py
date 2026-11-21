import asyncio
import html
import logging
import mimetypes
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import FSInputFile, KeyboardButton, Message, ReplyKeyboardMarkup

from ai_service import analyze_video, delete_remote_file, evaluate_voice
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
from session_store import delete_session, delete_session_if_matches, get_session, remove_local_file, save_session
from studio_service import analyze_dubbing_video, render_dubbed_video
from studio_store import clear_studio_session, get_studio_session, save_studio_session

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
    message_id: int | None = None,
    chat_id: int | None = None,
):
    destination.parent.mkdir(parents=True, exist_ok=True)

    if not TELEGRAM_LOCAL_MODE and is_mtproto_ready():
        try:
            await download_bot_file(
                file_id,
                destination,
                file_size=file_size,
                message_id=message_id,
                chat_id=chat_id,
            )
            logger.info(
                "Media MTProto orqali yuklandi (%s bytes).",
                destination.stat().st_size,
            )
            return
        except Exception as exc:
            logger.exception("MTProto orqali faylni yuklashda xatolik")
            if file_size and file_size > BOT_API_DOWNLOAD_LIMIT:
                raise ValueError(
                    "Katta video Telegram serveridan MTProto orqali olinmadi. "
                    "Videoni qayta yuborib ko‘r; muammo takrorlansa Live Console logini tekshiramiz."
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
    # Har bir video uchun alohida fayl: parallel yuborilgan videolar bir-birini bosib ketmasin.
    path = user_folder(user.id) / f"scene_{message.message_id}{extension}"
    status = await message.answer(
        "<b>🎬 VIDEO QABUL QILINDI</b>\n\n"
        "Faylni yuklayapman, keyin sahna va personaj emotsiyasini tahlil qilaman.\n"
        "<i>Bu biroz vaqt olishi mumkin.</i>"
    )

    try:
        download_started = time.monotonic()
        await download_to_path(
            message,
            file_id,
            path,
            file_size=file_size,
            message_id=message.message_id,
            chat_id=message.chat.id,
        )
        logger.info("Telegram video yuklandi: %.1f soniya", time.monotonic() - download_started)
        await status.edit_text(
            "<b>🧠 VIDEO YUKLANDI</b>\n\n"
            "Gemini sahna va personaj emotsiyasini tahlil qilmoqda. "
            "Xizmat band bo‘lsa, avtomatik qayta urinib ko‘raman."
        )
        analysis_started = time.monotonic()
        analysis_data = await asyncio.to_thread(analyze_video, str(path), mime_type)
        logger.info("Gemini sahna tahlili tugadi: %.1f soniya", time.monotonic() - analysis_started)
        result = analysis_data["text"]
        previous = get_session(user.id)
        if previous:
            remove_local_file(previous.get("video_path"))
            if previous.get("gemini_file_name"):
                await asyncio.to_thread(delete_remote_file, previous["gemini_file_name"])

        save_session(
            user.id,
            {
                "video_path": str(path),
                "video_name": filename,
                "video_mime": mime_type,
                "analysis": result,
                "gemini_file_name": analysis_data.get("gemini_file_name"),
                "gemini_file_uri": analysis_data.get("gemini_file_uri"),
                "gemini_file_mime": analysis_data.get("gemini_file_mime"),
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
            "<b>⚠️ GEMINI TAHLILNI YAKUNLAY OLMADI</b>\n\n"
            "Video muvaffaqiyatli yuklandi, ammo AI xizmati hozir javob bermadi. "
            "Bir ozdan keyin /reset qilib videoni qayta yubor."
        )




def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🎬 AI Dublyaj Studio")]],
        resize_keyboard=True,
        input_field_placeholder="Bo‘limni tanlang",
    )


def _format_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    minutes, remainder = divmod(total_ms, 60_000)
    whole_seconds, millis = divmod(remainder, 1000)
    return f"{minutes:02d}:{whole_seconds:02d}.{millis // 10:02d}"


async def show_studio_line(message: Message, user_id: int) -> None:
    session = get_studio_session(user_id)
    if not session or session.get("status") != "recording":
        return

    dialogue = session.get("dialogue") or []
    index = int(session.get("next_index", 0))
    if index >= len(dialogue):
        session["status"] = "ready_to_render"
        save_studio_session(user_id, session)
        await finalize_studio(message, user_id)
        return

    line = dialogue[index]
    total = len(dialogue)
    start = _format_timestamp(float(line["start"]))
    end = _format_timestamp(float(line["end"]))
    original = html.escape(line.get("original_text") or "Aniqlanmadi")
    dub_text = html.escape(line.get("dub_text") or "")
    speaker = html.escape(line.get("speaker") or "Personaj")
    emotion = html.escape(line.get("emotion") or "aniqlanmagan")
    delivery = html.escape(line.get("delivery") or "Tabiiy va ravon ovozda ayt.")
    intensity = int(line.get("intensity", 5))

    await message.answer(
        f"<b>🎬 AI DUBLYAJ — {index + 1}/{total}</b>\\n\\n"
        f"<b>👤 PERSONAJ:</b> {speaker}\\n"
        f"<b>⏱ VAQT:</b> {start} — {end}\\n\\n"
        f"<b>🌐 ORIGINAL:</b> {original}\\n"
        f"<b>🎙 AYTISH KERAK:</b> {dub_text}\\n\\n"
        f"<b>🎭 EMOTSIYA:</b> {emotion}\\n"
        f"<b>🔥 EMOTSIYA KUCHI:</b> {intensity}/10\\n"
        f"<b>🎧 OVOZ KO‘RSATMASI:</b> {delivery}\\n\\n"
        "<i>Faqat shu replikani alohida voice yoki audio qilib yubor. "
        "Ovoz qabul qilinsa, keyingi replika avtomatik chiqadi.</i>"
    )


async def process_studio_video(
    message: Message,
    file_id: str,
    filename: str,
    mime_type: str,
    file_size: int | None = None,
) -> None:
    if not private_chat_only(message):
        await message.answer("Dublyaj Studio faqat shaxsiy chatda ishlaydi.")
        return
    user = message.from_user
    if user is None:
        return

    path = user_folder(user.id) / (
        f"studio_scene_{message.message_id}{safe_extension(filename, '.mp4')}"
    )
    status = await message.answer(
        "<b>🎬 AI DUBLYAJ STUDIO</b>\\n\\n"
        "Videoni yuklayapman. Keyin barcha dialoglarni vaqt va emotsiya bo‘yicha ajrataman."
    )
    try:
        await download_to_path(
            message,
            file_id,
            path,
            file_size=file_size,
            message_id=message.message_id,
            chat_id=message.chat.id,
        )
        await status.edit_text(
            "<b>🧠 VIDEO TAHLIL QILINYAPTI</b>\\n\\n"
            "AI personajlarni, gaplarni, vaqtlarini va har bir replikaning emotsiyasini aniqlayapti. "
            "Video uzunligiga qarab biroz vaqt olishi mumkin."
        )
        analysis = await asyncio.to_thread(analyze_dubbing_video, str(path), mime_type)
        dialogue = analysis.get("dialogue") or []
        if not dialogue:
            raise ValueError(
                "Videoda aniq eshitiladigan dialog topilmadi. Dialogi bor video yuborib ko‘r."
            )

        # Eski studio sessiyasi fayllarini yangi tahlil saqlangandan keyin tozalaymiz.
        clear_studio_session(user.id)
        session = {
            "status": "recording",
            "video_path": str(path),
            "video_name": filename,
            "video_mime": mime_type,
            "video_language": analysis.get("video_language", "aniqlanmadi"),
            "dialogue": dialogue,
            "next_index": 0,
            "recordings": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        save_studio_session(user.id, session)
        await status.edit_text(
            f"<b>✅ TAHLIL TAYYOR</b>\\n\\n"
            f"🌐 Video tili: {html.escape(session['video_language'])}\\n"
            f"🗣 Replikalar: {len(dialogue)} ta\\n\\n"
            "Endi har bir replikani bittadan yozib boramiz."
        )
        await message.answer(
            "<b>ℹ️ OVOZ YO‘LI</b>\\n"
            "Original dialog o‘rniga sizning ovozingiz qo‘yiladi. Ushbu ilk versiyada "
            "original audio to‘liq o‘chiriladi, shu sabab fon musiqasi va effektlar ham saqlanmaydi. "
            "Ularni alohida ajratib saqlash keyingi bosqichda qo‘shiladi."
        )
        await show_studio_line(message, user.id)
    except ValueError as exc:
        path.unlink(missing_ok=True)
        await status.edit_text(f"<b>⚠️ TAHLILNI BAJARIB BO‘LMADI</b>\\n\\n{html.escape(str(exc))}")
    except Exception:
        logger.exception("AI Dublyaj Studio video tahlilida xatolik")
        path.unlink(missing_ok=True)
        await status.edit_text(
            "<b>❌ VIDEO TAHLILIDA XATOLIK</b>\\n\\n"
            "Videoni tahlil qilishda muammo bo‘ldi. /studio orqali qayta boshlang."
        )


async def process_studio_audio(
    message: Message,
    file_id: str,
    filename: str | None,
    mime_type: str,
    file_size: int | None = None,
) -> None:
    user = message.from_user
    if user is None:
        return
    session = get_studio_session(user.id)
    if not session:
        return
    if session.get("status") != "recording":
        await message.answer("Studio hozir ovoz qabul qilmayapti. /studio_finish yoki /studio_cancel buyrug‘ini ishlating.")
        return

    index = int(session.get("next_index", 0))
    dialogue = session.get("dialogue") or []
    if index >= len(dialogue):
        session["status"] = "ready_to_render"
        save_studio_session(user.id, session)
        await finalize_studio(message, user.id)
        return

    extension = safe_extension(filename, ".ogg" if "ogg" in mime_type else ".mp3")
    voice_path = user_folder(user.id) / f"studio_voice_{message.message_id}{extension}"
    status = await message.answer(
        f"<b>🎧 {index + 1}/{len(dialogue)} — OVOZ QABUL QILINDI</b>\\n\\n"
        "Ovoz faylini saqlayapman va kerakli vaqtga joylash uchun tayyorlayapman."
    )
    saved = False
    try:
        await download_to_path(
            message,
            file_id,
            voice_path,
            file_size=file_size,
            message_id=message.message_id,
            chat_id=message.chat.id,
        )
        line = dialogue[index]
        recordings = list(session.get("recordings") or [])
        recordings.append(
            {
                "line_id": line["id"],
                "start": float(line["start"]),
                "end": float(line["end"]),
                "file_path": str(voice_path),
            }
        )
        session["recordings"] = recordings
        session["next_index"] = index + 1
        session["status"] = "recording"
        save_studio_session(user.id, session)
        saved = True
        await status.edit_text(
            f"<b>✅ {index + 1}/{len(dialogue)} — SAQLANDI</b>\\n\\n"
            "Ovozing shu replika boshlanadigan vaqtga joylanadi."
        )

        if session["next_index"] >= len(dialogue):
            session["status"] = "ready_to_render"
            save_studio_session(user.id, session)
            await finalize_studio(message, user.id)
        else:
            await show_studio_line(message, user.id)
    except ValueError as exc:
        await status.edit_text(f"<b>⚠️ OVOZNI QABUL QILIB BO‘LMADI</b>\\n\\n{html.escape(str(exc))}")
    except Exception:
        logger.exception("AI Dublyaj Studio audio qabul qilishda xatolik")
        await status.edit_text(
            "<b>❌ OVOZNI SAQLASHDA XATOLIK</b>\\n\\n"
            "Ovozni qayta yuborib ko‘r. Joriy replika hali saqlanmadi."
        )
    finally:
        if not saved:
            voice_path.unlink(missing_ok=True)


async def finalize_studio(message: Message, user_id: int) -> None:
    session = get_studio_session(user_id)
    if not session:
        await message.answer("Faol Dublyaj Studio sessiyasi topilmadi.")
        return

    if session.get("status") == "ready_to_render":
        progress = await message.answer(
            "<b>🎞 DUBLYAJ YIG‘ILMOQDA</b>\\n\\n"
            "Barcha ovozlaring vaqt bo‘yicha videoga joylanmoqda. Bu video uzunligiga bog‘liq."
        )
        output_path = user_folder(user_id) / f"studio_result_{user_id}.mp4"
        try:
            result_path = await asyncio.to_thread(
                render_dubbed_video,
                session["video_path"],
                session.get("recordings") or [],
                str(output_path),
            )
        except Exception:
            logger.exception("Dublyaj videosini render qilishda xatolik")
            await progress.edit_text(
                "<b>⚠️ VIDEONI YIG‘ISHDA XATOLIK</b>\\n\\n"
                "Ovoz yozuvlaring saqlangan. /studio_finish buyrug‘i bilan qayta urinib ko‘r."
            )
            return

        session["output_path"] = result_path
        session["status"] = "ready_to_send"
        save_studio_session(user_id, session)
        await progress.edit_text("<b>✅ VIDEO TAYYOR</b>\\n\\nTelegramga yuboryapman.")

    session = get_studio_session(user_id)
    if not session or session.get("status") != "ready_to_send":
        return
    output_path = session.get("output_path")
    if not output_path or not Path(output_path).is_file():
        await message.answer("Tayyor video fayli topilmadi. /studio_finish orqali qayta urinib ko‘ring.")
        return

    try:
        await message.answer_video(
            FSInputFile(output_path, filename="Bekiuz-DubLab-dublyaj.mp4"),
            caption=(
                "🎬 <b>AI DUBLYAJ STUDIO — TAYYOR!</b>\\n\\n"
                "Sizning ovozlaringiz videoga vaqt bo‘yicha joylandi. "
                "Original audio o‘rniga dublyaj ovozlari qo‘yildi."
            ),
        )
    except Exception:
        logger.exception("Tayyor dublyaj videosini Telegramga yuborib bo‘lmadi")
        await message.answer(
            "Video tayyor, ammo Telegramga yuborishda xatolik bo‘ldi. "
            "Video hajmi katta bo‘lishi mumkin. /studio_finish bilan qayta urinib ko‘ring."
        )
        return

    clear_studio_session(user_id)
    await message.answer(
        "<b>🧹 STUDIO FAYLLARI TOZALANDI</b>\\n\\n"
        "Dublyaj yakunlandi. Yangi loyiha uchun /studio buyrug‘ini yuboring."
    )


async def start_studio(message: Message) -> None:
    if not private_chat_only(message):
        await message.answer("AI Dublyaj Studio faqat shaxsiy chatda ishlaydi.")
        return
    user = message.from_user
    if user is None:
        return
    clear_studio_session(user.id)
    save_studio_session(user.id, {"status": "awaiting_video", "recordings": []})
    await message.answer(
        "<b>🎬 AI DUBLYAJ STUDIO</b>\\n\\n"
        "Videoni yuboring. AI uni boshidan oxirigacha tahlil qiladi va barcha gaplarni "
        "bittadan beradi. Har bir gap ostida emotsiya, emotsiya kuchi va qanday aytish "
        "kerakligi ko‘rsatiladi. Siz ovoz yuborganingizdan keyin keyingi replika chiqadi.\\n\\n"
        "Barcha replikalar tugagach, bot dublyaj qilingan MP4 videoni yig‘adi.\\n\\n"
        "<i>Bekor qilish: /studio_cancel</i>",
        reply_markup=main_keyboard(),
    )


@dp.message(Command("studio"))
async def studio_command_handler(message: Message):
    await start_studio(message)


@dp.message(Command("studio_cancel"))
async def studio_cancel_handler(message: Message):
    user = message.from_user
    if user is None:
        return
    previous = clear_studio_session(user.id)
    if previous:
        await message.answer("🧹 AI Dublyaj Studio sessiyasi va vaqtinchalik fayllari o‘chirildi.")
    else:
        await message.answer("Faol Dublyaj Studio sessiyasi yo‘q.")


@dp.message(Command("studio_finish"))
async def studio_finish_handler(message: Message):
    user = message.from_user
    if user is None:
        return
    await finalize_studio(message, user.id)

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

    studio_session = get_studio_session(user.id)
    if studio_session:
        studio_status = studio_session.get("status")
        if studio_status == "awaiting_video":
            await message.answer("Avval /studio bo‘limiga anime videosini yuboring.")
            return
        if studio_status == "recording":
            await process_studio_audio(message, file_id, filename, mime_type, file_size)
            return
        if studio_status in {"ready_to_render", "ready_to_send"}:
            await message.answer("Barcha replikalar saqlangan. Yakuniy videoni olish uchun /studio_finish yuboring.")
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
    voice_path = user_folder(user.id) / f"voice_{message.message_id}{extension}"
    status = await message.answer(
        "<b>🎧 OVOZ QABUL QILINDI</b>\n\n"
        "Ijroingni sahna emotsiyasi, ifoda, ritm va talaffuz bo‘yicha tekshiryapman.\n"
        "<i>Natija tayyor bo‘lgach shu yerga yuboraman.</i>"
    )

    try:
        await download_to_path(
            message,
            file_id,
            voice_path,
            file_size=file_size,
            message_id=message.message_id,
            chat_id=message.chat.id,
        )
        result = await asyncio.to_thread(
            evaluate_voice,
            session["video_path"],
            str(voice_path),
            session.get("video_mime"),
            mime_type,
            session.get("analysis"),
            session.get("gemini_file_uri"),
            session.get("gemini_file_mime"),
        )
        await status.edit_text("<b>✅ DUBLYAJ TAHLILI TAYYOR</b>\n\nQuyida ijroing bo‘yicha batafsil fikrlar.")
        await answer_long(message, result)

        # Baholash tugagach, ishlatilgan sahnani sessiyadan va xotiradan tozalaymiz.
        # Boshqa video shu paytda yuklangan bo‘lsa, uning yangi sessiyasiga tegmaymiz.
        removed_session = delete_session_if_matches(user.id, session["video_path"])
        remove_local_file(session.get("video_path"))
        if session.get("gemini_file_name"):
            await asyncio.to_thread(delete_remote_file, session["gemini_file_name"])
        if removed_session:
            await message.answer(
                "<b>🧹 SAHNA O‘CHIRILDI</b>\n\n"
                "Baholash tugadi va sahna fayllari tozalandi. Yana dublyaj qilish uchun "
                "videoni qayta yubor, keyin yangi ovozingni jo‘nat."
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
        "bo‘yicha fikr hamda 0 dan 10 gacha butun sonli baho ol.\n\n"
        "<b>BO‘LIMLAR</b>\n"
        "🎯 Oddiy dublyaj baholash — video + bitta ovoz va 0–10 baho.\n"
        "🎬 AI Dublyaj Studio — butun videoni replikama-replika dublyaj qilish.\n\n"
        "<b>BUYRUQLAR</b>\n"
        "/studio — AI Dublyaj Studio\n"
        "/studio_cancel — Studio sessiyasini bekor qilish\n"
        "/help — foydalanish qo‘llanmasi\n"
        "/reset — ikkala bo‘lim sessiyasini tozalash\n\n"
        "<i>Kerakli bo‘limni tanlang. ✨</i>",
        reply_markup=main_keyboard(),
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
        "📊 Har bir mezon va umumiy baho 0–10 oralig‘ida, butun son bilan beriladi.\n"
        "🎭 Emotsiya mosligi va uni ovozda yetkazish kuchi alohida baholanadi.\n"
        "⚠️ 0–5: sahnaga mos emas; 6–7: qisman mos; 8–9: yaxshi; 10: juda aniq.\n"
        "🧹 Baholash tugagach, sahna avtomatik o‘chiriladi.\n\n"
        "<b>🎬 AI DUBLYAJ STUDIO</b>\n"
        "/studio — yangi to‘liq dublyaj loyihasi\n"
        "Har bir replika alohida chiqadi; emotsiyasini ko‘rib, ovoz yuborasiz.\n"
        "/studio_finish — tayyor videoni qayta yuborish\n"
        "/studio_cancel — Studio loyihasini bekor qilish\n\n"
        "<b>FOYDALI BUYRUQLAR</b>\n"
        "/start — boshidan boshlash\n"
        "/reset — barcha sessiyalarni tozalash\n"
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
    studio_previous = clear_studio_session(user.id)
    if previous:
        remove_local_file(previous.get("video_path"))
        if previous.get("gemini_file_name"):
            await asyncio.to_thread(delete_remote_file, previous["gemini_file_name"])
    if previous or studio_previous:
        await message.answer("<b>🧹 BARCHA SESSIYALAR TOZALANDI</b>\n\nYangi loyiha yoki tahlilni boshlashingiz mumkin.")
    else:
        await message.answer("<b>📭 FAOL SESSIYA YO‘Q</b>\n\nBoshlash uchun /studio yuboring yoki anime videosini jo‘nating.")


@dp.message(F.video)
async def video_handler(message: Message):
    video = message.video
    if video is None:
        return
    filename = video.file_name or "anime_clip.mp4"
    mime_type = video.mime_type or mimetypes.guess_type(filename)[0] or "video/mp4"
    user = message.from_user
    studio_session = get_studio_session(user.id) if user else None
    if studio_session and studio_session.get("status") == "awaiting_video":
        await process_studio_video(
            message, video.file_id, filename, mime_type, file_size=video.file_size
        )
        return
    if studio_session and studio_session.get("status") in {"recording", "ready_to_render", "ready_to_send"}:
        await message.answer("Avval joriy Studio loyihasini yakunlang yoki /studio_cancel bilan bekor qiling.")
        return
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
        user = message.from_user
        studio_session = get_studio_session(user.id) if user else None
        if studio_session and studio_session.get("status") == "awaiting_video":
            await process_studio_video(
                message, document.file_id, filename, mime_type or "video/mp4",
                file_size=document.file_size,
            )
            return
        if studio_session and studio_session.get("status") in {"recording", "ready_to_render", "ready_to_send"}:
            await message.answer("Avval joriy Studio loyihasini yakunlang yoki /studio_cancel bilan bekor qiling.")
            return
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
    if (message.text or "").strip() == "🎬 AI Dublyaj Studio":
        await start_studio(message)
        return
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
