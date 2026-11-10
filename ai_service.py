import logging
import mimetypes
import time
from pathlib import Path

from google import genai
from google.genai import types

from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

VIDEO_PROMPT = """
Sen Bekiuz DubLab nomli anime dublyaj murabbiyisan. Videoni ham TASVIR, ham UNING ICHIDAGI AUDIO bo‘yicha tahlil qil.

Vazifang:
1. Kadrdagi personajning yuz ifodasi, tana harakati va vaziyatidan kelib chiqib asosiy emotsiyani aniqlash.
2. Personaj nima his qilayotgani va replika qanday niyatda aytilayotganini tushuntirish.
3. Dublyajchi bu replikani qanday aytishi kerakligini aniq ko‘rsatish: ovoz kuchi, ohang, tezlik, pauza va urg‘u.
4. Videoda aniq eshitiladigan nutq bo‘lsa, ovoz ijrosi vizual vaziyatga mos keladimi — bahola. Faqat ovoz balandligiga qarab baho qo‘yma.
5. Audio yo‘q yoki nutq aniq eshitilmasa, ovoz ijrosi bo‘yicha baho to‘qima; buni ochiq ayt.

JAVOBNI O‘ZBEK TILIDA, LOTIN YOZUVDA, quyidagi tartibda yoz:
🎬 SAHNA: qisqa, jonli vaziyat tavsifi
🎭 KERAKLI EMOTSIYA: asosiy va kerak bo‘lsa ikkilamchi emotsiya
🎙️ QANDAY OVOZ BERISH KERAK: ovoz kuchi, ohang, tezlik, pauza va urg‘u
🔎 VIDEODAGI OVOZ TAHLILI: nutq eshitiladimi, ijro emotsiyaga mosmi; yetarli ma’lumot bo‘lmasa ayt
📊 MOSLIK BAHOSI: faqat aniq nutq eshitilib, baholash mumkin bo‘lsa taxminiy 100 ballik baho; aks holda “baholanmadi”
💡 MURABBIY MASLAHATI: qayta yozish uchun bitta aniq, bajarish oson ko‘rsatma
📌 ISHONCH DARAJASI: yuqori/o‘rtacha/past va nima sababdan.

JAVOB DIZAYNI:
- Har bir bo‘lim nomini alohida qatorda, katta harflar bilan yoz.
- Har bo‘lim ostida 1–3 ta qisqa, mazmunli jumla ishlat.
- Kerak joyda qisqa punktlar bilan urg‘u, pauza va tezlikni ajrat.
- Muhim tavsiyani aniq misol bilan ko‘rsat; umumiy gap bilan cheklanma.
- Javobni tartibli, professional, iliq murabbiy ohangida yoz; ortiqcha kirish va takrorlardan qoch.
- Markdown yulduzchalari yoki HTML teglarini ishlatma; bot sarlavhalarni o‘zi formatlaydi.

Shaxsni aniqlashga urinma va videodagi ovoz egasini foydalanuvchi deb taxmin qilma. Original aktyorning ovoz tembrini nusxalashni buyurma; vaziyatga mos aktyorlikni tushuntir. Tez almashuvchi kadrlar sabab ayrim mimikalar ko‘rinmasligi mumkin — noaniqlikni tan ol.
"""

VOICE_COMPARE_PROMPT = """
Sen Bekiuz DubLab anime dublyaj murabbiysan. Senga ikkita media berilgan:
- VIDEO: personaj, sahna vaziyati, mimika va harakatlar.
- AUDIO: foydalanuvchining yangi ovozli dublyaj urinishi.

Vazifa: foydalanuvchining AUDIO ijrosini videodagi sahna mazmuni va personajning ko‘rinadigan emotsiyasiga solishtir. Videodagi original ovoz boshqa tilda bo‘lishi mumkin — uning tembrini nusxalashni talab qilma. Asosiy mezon vaziyat va emotsiyaga mos aktyorlik.

100 ballik bahoni faqat eshitiladigan material yetarli bo‘lsa ber. Tavsiya etiladigan mezonlar:
- Emotsiya mosligi — 35%
- Ovoz ifodasi va niyat — 25%
- Tezlik, ritm va pauzalar — 15%
- Talaffuz va tushunarlilik — 15%
- Video bilan vaqt mosligi — 10%, faqat ishonchli tekshirish mumkin bo‘lsa.

Sinxronlikni ishonchli aniqlab bo‘lmasa, “o‘lchanmadi” deb yoz va qolgan mezonlarga qarab umumiy bahoni mutanosib hisobla. Nutq yetarli bo‘lmasa, soxta ball bermagin. Baland ovozni o‘z-o‘zidan yaxshi ijro deb hisoblama. Qaysi so‘z yoki lahzada nima xato bo‘lganini vaqt belgisi bilan faqat vaqtni aniqlay olsang ko‘rsat.

JAVOB O‘ZBEK TILIDA, LOTIN YOZUVDA:
🎭 SAHNA EMOTSIYASI: videodagi vaziyat va personaj kayfiyati
🎙️ SENING IJROING: eshitilgan emotsiya va ijro niyati
📊 UMUMIY BAHO: xx/100 yoki “baholanmadi”
📋 MEZONLAR: har biri uchun ball va qisqa, asosli sabab
✅ YAXSHI CHIQQAN JOYLAR: aniq kuchli tomonlar
🛠️ TUZATISH KERAK: aniq ibora/lahza va nima qilish kerak
🎬 QAYTA DUBL UCHUN KO‘RSATMA: qanday ohangda, tezlikda va pauza bilan aytish
📌 ISHONCH DARAJASI: yuqori/o‘rtacha/past va nima sababdan.

JAVOB DIZAYNI:
- Har bir bo‘lim nomini alohida qatorda, katta harflar bilan yoz.
- Umumiy bahodan keyin mezonlarni ixcham ro‘yxat ko‘rinishida ko‘rsat.
- Har bir tanqid yonida tuzatishning aniq usulini ber.
- Avval kuchli tomonlarni, keyin yaxshilash kerak bo‘lgan joylarni yoz.
- Ohang professional, muloyim va motivatsion bo‘lsin; sun’iy maqtov yoki qattiq tanqid bo‘lmasin.
- Markdown yulduzchalari yoki HTML teglarini ishlatma; bot sarlavhalarni o‘zi formatlaydi.

Videoda qaysi qismni dublyaj qilish kerakligi noaniq bo‘lsa, buni ayt; butun videodan taxminiy xulosa chiqarib, aniq lab-sinxronlik bor deb da’vo qilma.
"""


def _new_client() -> genai.Client:
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY sozlanmagan. Google AI Studio kalitini .env fayliga kiriting."
        )
    return genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(
                attempts=2,
                initial_delay=1.0,
                max_delay=4.0,
                exp_base=2.0,
                jitter=0.3,
                http_status_codes=[500, 502, 503, 504],
            )
        ),
    )


def _wait_until_ready(client: genai.Client, uploaded_file, timeout_seconds: int = 180):
    deadline = time.monotonic() + timeout_seconds
    current = uploaded_file

    while True:
        state = getattr(current, "state", None)
        state_name = getattr(state, "name", str(state or "")).upper()

        if state_name == "ACTIVE":
            return current
        if state_name in {"FAILED", "ERROR"}:
            raise RuntimeError("Google AI video/audio faylini qayta ishlay olmadi.")
        if time.monotonic() >= deadline:
            raise TimeoutError("Media faylni tayyorlash vaqti tugadi. Qisqaroq video yuboring.")

        time.sleep(1)
        current = client.files.get(name=current.name)


def _upload(client: genai.Client, path: Path, uploaded_files: list) :
    uploaded = client.files.upload(file=str(path))
    uploaded_files.append(uploaded)
    return _wait_until_ready(client, uploaded)


def _delete_uploaded_files(client: genai.Client, uploaded_files: list) -> None:
    for uploaded in uploaded_files:
        name = getattr(uploaded, "name", None)
        if not name:
            continue
        try:
            client.files.delete(name=name)
        except Exception:
            logger.warning("Gemini'dagi vaqtinchalik faylni o‘chirish muvaffaqiyatsiz: %s", name)


def _output_text(response) -> str:
    text = getattr(response, "text", None)
    if text and text.strip():
        return text.strip()
    raise RuntimeError("AI bo‘sh javob qaytardi. Qayta urinib ko‘ring.")


def _generate_with_fallback(client: genai.Client, contents) -> str:
    """Use GenerateContent; switch to a lighter stable model only on overload."""
    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=contents,
        )
        return _output_text(response)
    except Exception as exc:
        status_code = getattr(exc, "code", None)
        is_overloaded = (
            status_code == 503
            or "503" in str(exc)
            or "high demand" in str(exc).lower()
            or "service_unavailable" in str(exc).lower()
        )
        if not is_overloaded:
            raise

        fallback_model = "gemini-3.8-flash"
        if fallback_model == GEMINI_MODEL:
            raise

        logger.warning(
            "Asosiy Gemini modeli band (503); zaxira modelga o‘tilmoqda: %s",
            fallback_model,
        )
        response = client.models.generate_content(
            model=fallback_model,
            contents=contents,
        )
        return _output_text(response)


def analyze_video(video_path: str, mime_type: str | None = None) -> dict:
    """Upload and analyse a scene once; retain its Gemini file for later voice attempts."""
    path = Path(video_path)
    guessed_mime = mime_type or mimetypes.guess_type(path.name)[0] or "video/mp4"
    client = _new_client()
    uploaded_files = []
    keep_video = False
    try:
        logger.info("Gemini video yuklandi; tezkor GenerateContent tahlili boshlanmoqda.")
        video = _upload(client, path, uploaded_files)
        logger.info("Gemini video tayyor; GenerateContent so‘rovi yuborilmoqda.")
        video_part = types.Part.from_uri(
            file_uri=video.uri,
            mime_type=getattr(video, "mime_type", None) or guessed_mime,
        )
        result = _generate_with_fallback(client, contents=[VIDEO_PROMPT, video_part])
        keep_video = True
        logger.info("Gemini sahna tahlilini muvaffaqiyatli yakunladi.")
        return {
            "text": result,
            "gemini_file_name": video.name,
            "gemini_file_uri": video.uri,
            "gemini_file_mime": getattr(video, "mime_type", None) or guessed_mime,
        }
    finally:
        if not keep_video:
            _delete_uploaded_files(client, uploaded_files)
        client.close()


def evaluate_voice(
    video_path: str,
    voice_path: str,
    video_mime: str | None = None,
    voice_mime: str | None = None,
    scene_notes: str | None = None,
    video_file_uri: str | None = None,
    video_file_mime: str | None = None,
) -> str:
    """Compare a separate voice message with the previously uploaded video."""
    v_path = Path(video_path)
    a_path = Path(voice_path)
    v_mime = video_mime or mimetypes.guess_type(v_path.name)[0] or "video/mp4"
    a_mime = voice_mime or mimetypes.guess_type(a_path.name)[0] or "audio/ogg"

    client = _new_client()
    uploaded_files = []
    try:
        if video_file_uri:
            video_uri = video_file_uri
            video_content_mime = video_file_mime or v_mime
            logger.info("Saqlangan Gemini sahnasi qayta ishlatilmoqda; video qayta yuklanmaydi.")
        else:
            video = _upload(client, v_path, uploaded_files)
            video_uri = video.uri
            video_content_mime = getattr(video, "mime_type", None) or v_mime
        audio = _upload(client, a_path, uploaded_files)
        context = ""
        if scene_notes:
            context = "\n\nAvvalgi sahna tahlili (qo‘shimcha kontekst):\n" + scene_notes[:6000]

        video_part = types.Part.from_uri(
            file_uri=video_uri,
            mime_type=video_content_mime,
        )
        audio_part = types.Part.from_uri(
            file_uri=audio.uri,
            mime_type=getattr(audio, "mime_type", None) or a_mime,
        )
        return _generate_with_fallback(
            client,
            contents=[VOICE_COMPARE_PROMPT + context, video_part, audio_part],
        )
    finally:
        _delete_uploaded_files(client, uploaded_files)
        client.close()


def delete_remote_file(file_name: str | None) -> None:
    """Delete a retained Gemini scene file when a session is reset or replaced."""
    if not file_name or not GEMINI_API_KEY:
        return
    client = _new_client()
    try:
        client.files.delete(name=file_name)
    except Exception:
        logger.warning("Gemini sahna faylini o‘chirish muvaffaqiyatsiz: %s", file_name)
    finally:
        client.close()
