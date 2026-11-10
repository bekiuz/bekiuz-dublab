import logging
import mimetypes
import time
from pathlib import Path

from google import genai
from google.genai import types

from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

VIDEO_PROMPT = """
Sen Bekiuz DubLab anime dublyaj murabbiyisan. Videoni sahna va emotsiya bo‘yicha tahlil qil.

Vazifang:
1. Personajning yuz ifodasi, tana harakati, vaziyat va eshitiladigan original nutqdan asosiy emotsiyani aniqlash.
2. Emotsiyaning sahnadagi kuchini 0 dan 10 gacha BUTUN SON bilan bahola. Bu qahramon his-tuyg‘usining kuchi; ovoz balandligi bilan adashtirma.
3. Replika qanday niyatda aytilishini, ovoz kuchi, ohang, tezlik, pauza va urg‘uni tushuntir.
4. Dublyajchi qaysi emotsiyani va qanday darajada yetkazishi kerakligini ayt.
5. Audio yoki nutq aniq bo‘lmasa, ovoz haqida taxmin qilma; ko‘rinadigan mimika va vaziyatga tayanganingni ayt.

JAVOBNI O‘ZBEK TILIDA, LOTIN YOZUVDA:
🎬 SAHNA: qisqa vaziyat tavsifi
🎭 KERAKLI EMOTSIYA: asosiy va ikkilamchi emotsiya
🔥 SAHNADAGI EMOTSIYA KUCHI: N/10 — butun son va qisqa izoh
🎙️ QANDAY OVOZ BERISH KERAK: ovoz kuchi, ohang, tezlik, pauza va urg‘u
💡 MURABBIY MASLAHATI: qayta yozish uchun bitta aniq ko‘rsatma
📌 ISHONCH DARAJASI: yuqori/o‘rtacha/past va sababi.

BAHO QOIDASI:
- Faqat 0, 1, 2, 3, 4, 5, 6, 7, 8, 9 yoki 10. Kasr va 100 ballik tizim taqiqlanadi.
- 0–5: past emotsional moslik; qahramon kayfiyatini yetkazish uchun nimalar noto‘g‘ri ekanini muloyim, lekin ochiq ayt.
- 6–7: qisman mos.
- 8–9: juda yaxshi.
- 10: sahna emotsiyasi juda aniq va ishonarli.

JAVOB DIZAYNI:
- Bo‘lim nomlarini alohida qatorda yoz.
- Qisqa, mazmunli jumlalar ishlat; ortiqcha kirish va takrordan qoch.
- Umumiy gap emas, aniq urg‘u/pauza/tezlik misolini ber.
- Original aktyorning ovoz tembrini nusxalashni talab qilma; vaziyatga mos aktyorlikni tushuntir.
- Shaxsni aniqlashga urinma. Mimikalar noaniq yoki kadrlar tez almashsa, buni tan ol.
"""

VOICE_COMPARE_PROMPT = """
Sen Bekiuz DubLab anime dublyaj murabbiyisan. Senga ikkita media berilgan:
- VIDEO: original sahna, personaj va uning emotsiyasi.
- AUDIO: foydalanuvchining dublyaj urinishi.

ASOSIY VAZIFA:
Audio ijrosini videodagi sahna mazmuni va personajning emotsiyasiga solishtir. Original aktyorning ovoz tembrini aynan nusxalashni talab qilma. Bahola: dublyajchi kerakli emotsiyani to‘g‘ri tanladimi, uni yetarli va ishonarli darajada yetkazdimi, ohang va ritm sahnaga mosmi.

BAHOLASH SHKALASI — QAT’IY:
- Umumiy baho faqat 0/10 dan 10/10 gacha bo‘lgan BUTUN SON. Faqat 0, 1, 2, 3, 4, 5, 6, 7, 8, 9 yoki 10 ishlat. 100 ball, foiz, kasr yoki 7.5 kabi qiymat yozma.
- 0–2: UMUMAN MOS EMAS. Kerakli emotsiya noto‘g‘ri yoki deyarli sezilmaydi. Ochiq ayt: “Ijro sahnaga umuman mos kelmadi.”
- 3–5: MOS EMAS / JUDA SUST MOS. Asosiy emotsiya yoki uning kuchi yetarli chiqmagan. Ochiq ayt: “Ijro sahnaga to‘g‘ri tushmadi.”
- 6–7: QISMAN MOS. Asosiy kayfiyat seziladi, ammo intonatsiya, emotsiya kuchi yoki ritmda kamchilik bor.
- 8–9: YAXSHI MOS. Emotsiya va ijro ishonarli, faqat kichik kamchiliklar bor.
- 10: JUDA ANIQ MOS. Kerakli emotsiya, ifoda va ritm sahnaga juda ishonarli tushgan.
- Nutq eshitilmasa, audio buzilgan bo‘lsa yoki baholash uchun yetarli material bo‘lmasa, 0 qo‘yma: “BAHOLANMADI” deb yoz va sababini tushuntir.
- Har bir mezon ham 0–10 oralig‘idagi butun son bo‘lsin. Umumiy bahoni mezonlarning ahamiyatiga qarab hisobla va eng yaqin butun songa yaxlitla.

MEZONLAR:
- Emotsiya mosligi — 35%
- Emotsiyani ovozda yetkazish kuchi va ishonarliligi — 25%. Balandlikni emas, kerakli hissiyotning ta’sirini bahola.
- Intonatsiya va ohang — 20%
- Ritm, tezlik va pauzalar — 10%
- Talaffuz va tushunarlilik — 10%
Video bilan vaqt mosligini faqat aniq tekshira olsang alohida izohla; noaniq lab-sinxronlikni bahoga qo‘shma va to‘qima.

JAVOB O‘ZBEK TILIDA, LOTIN YOZUVDA:
🎭 SAHNA EMOTSIYASI: personaj nimani his qilishi kerak
🔥 OVOZ EMOTSIYA DARAJASI: N/10 — dublyajchining emotsiyani qanchalik kuchli va ishonarli yetkazgani
🎯 EMOTSIYA MOSLIGI: N/10 — ijro kerakli hissiyotga qanchalik mos
🎙️ INTONATSIYA VA OHANG: N/10 — qisqa sabab
⏱️ RITM VA PAUZALAR: N/10 — qisqa sabab
🗣️ TALAFFUZ: N/10 — qisqa sabab
📊 UMUMIY BAHO: N/10 — albatta butun son
📋 IZOH: baho 0–5 bo‘lsa, ijro sahnaga mos kelmaganini aniq ayt; 6–7 bo‘lsa qisman mosligini; 8–10 bo‘lsa yaxshi mosligini tushuntir
✅ YAXSHI CHIQQAN JOYLAR: faqat aniq kuchli tomonlar, bo‘lmasa shuni rost ayt
🛠️ TUZATISH KERAK: qaysi emotsiya/intonatsiya/so‘z ustida ishlash kerakligini aniq ayt
🎬 QAYTA DUBL UCHUN KO‘RSATMA: qanday ohang, emotsiya kuchi, tezlik va pauza bilan aytish
📌 ISHONCH DARAJASI: yuqori/o‘rtacha/past va sababi.

JAVOB QOIDALARI:
- Barcha baholar x/10 ko‘rinishida va faqat butun son bo‘lsin.
- 0–5 olgan ijroni sun’iy maqtama; mos kelmaganini rost, ammo hurmat bilan ayt.
- Ovoz balandligini emotsiya kuchi deb hisoblama. Baqirish har doim kuchli emotsiya emas.
- Avval aniq kuchli tomonlarni, keyin yaxshilash kerak bo‘lgan joylarni yoz.
- Vaqt belgilarini faqat ishonchli aniqlay olsang ko‘rsat.
- Video/sahna noaniq yoki audio yetarli bo‘lmasa, soxta ball bermagin.
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
    """Use fast Flash-Lite first, then a stronger stable model only on overload."""
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
