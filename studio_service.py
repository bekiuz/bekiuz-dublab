import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

import imageio_ffmpeg
from google.genai import types

from ai_service import (
    _delete_uploaded_files,
    _generate_with_fallback,
    _new_client,
    _upload,
)

logger = logging.getLogger("bekiuz-dublab.studio")

DIALOGUE_PROMPT = """
Sen professional dublyaj rejissyori va o‘zbekcha tarjimonisan. Berilgan videoni boshidan oxirigacha tahlil qil.

QAT’IY TIL TALABI:
- Manba video qaysi tilda bo‘lishidan qat’i nazar, foydalanuvchiga faqat O‘ZBEK TILIDA (lotin yozuvida) replika tayyorla.
- Original tildagi transkripsiyani, jumlani, subtitrni yoki til nomini natijada qaytarma.
- Har bir dub_text tabiiy, ravon va mazmunni saqlagan o‘zbekcha tarjima bo‘lsin.
- Ismlar va zarur atamalar asl talaffuzda qolishi mumkin, qolgan hamma gap o‘zbekcha bo‘lsin.
- Emotsiya va ovoz ko‘rsatmalari ham faqat o‘zbek tilida bo‘lsin.

Maqsad: foydalanuvchi har bir replika uchun alohida o‘zbekcha ovoz yozadi, keyin ular videodagi original dialog o‘rniga joylanadi.

Faqat videoda HAQIQATAN ESHITILADIGAN inson/personaj nutqini ketma-ket ajrat. Musiqa, effekt, nafas, kulgi yoki noaniq shovqinni dialog deb to‘qima. Bir-birining ustiga tushgan replikalarni alohida qaytar; vaqtlarini iloji boricha aniq belgilagin.

Har bir replika uchun:
- start: videoning boshidan boshlab boshlanish vaqti, soniya ko‘rinishida, kasrli son
- end: replika tugash vaqti, soniya ko‘rinishida
- speaker: kadr va kontekstdan ajrata olsang Personaj 1, Personaj 2 kabi barqaror nom; bilmasang Personaj
- dub_text: faqat o‘zbekcha (lotin) tabiiy tarjima; original tildagi matnni yozma
- emotion: sog‘inch, quvonch, g‘azab, qo‘rquv, hayrat, qayg‘u, xotirjamlik kabi emotsiya nomi
- intensity: emotsiya kuchi 0 dan 10 gacha BUTUN SON; ovoz balandligi emas, hissiyot kuchi
- delivery: foydalanuvchi qanday ovoz berishi kerakligi haqida faqat o‘zbekcha qisqa va aniq ko‘rsatma (tezlik, ohang, urg‘u, pauza, ovoz kuchi)

JAVOB FAQAT VALID JSON BO‘LSIN. Markdown, izoh yoki code block ishlatma. Aynan quyidagi shakl:
{
  "dialogue": [
    {
      "start": 1.2,
      "end": 2.8,
      "speaker": "Personaj 1",
      "dub_text": "Seni sog‘indim.",
      "emotion": "sog‘inch",
      "intensity": 9,
      "delivery": "Sekin va yumshoq ayt; 'sog‘indim' so‘zida hissiy urg‘u ber."
    }
  ]
}

Qoidalar:
- Dialoglarni videodagi vaqt tartibida joylashtir.
- Vaqtlar taxminiy bo‘lsa ham, real video vaqtiga mos va ketma-ket bo‘lsin.
- Eshitilmagan so‘zlarni uydirma; noaniq nutqni ro‘yxatdan chiqar.
- Ekrandagi subtitrni nutq deb qabul qilma; avval audioda eshitilganini tekshir.
- Dialog yo‘q bo‘lsa dialogue bo‘sh massiv bo‘lsin.
- dialogue ichida 80 tadan ortiq replika qaytarma.
- JSON ichidagi qiymatlarning barchasi (kalitlardan tashqari) o‘zbek tilida bo‘lsin.
"""


def _extract_json(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    text = re.sub(r"^\s*[\x60]{3}(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*[\x60]{3}\s*$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("AI dialog tahlilini JSON shaklida qaytarmadi. Videoni qayta yubor.")
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError("AI dialog ro‘yxatini o‘qib bo‘lmadi. Videoni qayta tahlil qilib ko‘r.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("AI dialog tahlili noto‘g‘ri formatda qaytdi.")
    return parsed


def _to_seconds(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        value = value.strip()
        if ":" in value:
            total = 0.0
            for part in value.split(":"):
                total = total * 60 + float(part)
            return total
        return float(value)
    raise ValueError("Dialog vaqt belgisi noto‘g‘ri.")


def analyze_dubbing_video(video_path: str, mime_type: str | None = None) -> dict[str, Any]:
    path = Path(video_path)
    if not path.is_file():
        raise FileNotFoundError("Dublyaj uchun video fayl topilmadi.")

    client = _new_client()
    uploaded_files = []
    try:
        uploaded = _upload(client, path, uploaded_files)
        video_part = types.Part.from_uri(
            file_uri=uploaded.uri,
            mime_type=getattr(uploaded, "mime_type", None) or mime_type or "video/mp4",
        )
        raw = _generate_with_fallback(
            client,
            contents=[DIALOGUE_PROMPT, video_part],
        )
        parsed = _extract_json(raw)
        source_lines = parsed.get("dialogue")
        if not isinstance(source_lines, list):
            raise ValueError("AI videodan dialog ro‘yxatini topa olmadi.")

        dialogue: list[dict[str, Any]] = []
        for item in source_lines[:80]:
            if not isinstance(item, dict):
                continue
            try:
                start = max(0.0, _to_seconds(item.get("start")))
                end = _to_seconds(item.get("end"))
            except (TypeError, ValueError):
                continue

            dub_text = str(item.get("dub_text") or "").strip()
            if not dub_text or end <= start:
                continue

            try:
                intensity = int(round(float(item.get("intensity", 5))))
            except (TypeError, ValueError):
                intensity = 5
            intensity = max(0, min(10, intensity))

            dialogue.append(
                {
                    "id": len(dialogue) + 1,
                    "start": round(start, 2),
                    "end": round(end, 2),
                    "speaker": str(item.get("speaker") or "Personaj").strip()[:80],
                    "dub_text": dub_text[:1200],
                    "emotion": str(item.get("emotion") or "aniqlanmagan").strip()[:80],
                    "intensity": intensity,
                    "delivery": str(item.get("delivery") or "Tabiiy va ravon ovozda ayt.").strip()[:500],
                }
            )

        dialogue.sort(key=lambda line: (line["start"], line["id"]))
        for index, line in enumerate(dialogue, start=1):
            line["id"] = index

        return {"dialogue": dialogue}
    finally:
        _delete_uploaded_files(client, uploaded_files)
        client.close()


def render_dubbed_video(
    video_path: str,
    recordings: list[dict[str, Any]],
    output_path: str,
) -> str:
    source = Path(video_path)
    output = Path(output_path)
    if not source.is_file():
        raise FileNotFoundError("Asl video fayli topilmadi.")
    if not recordings:
        raise ValueError("Videoga joylash uchun ovoz yozuvlari mavjud emas.")

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [ffmpeg, "-y", "-i", str(source)]
    for item in recordings:
        audio_path = Path(item["file_path"])
        if not audio_path.is_file():
            raise FileNotFoundError("Replika ovoz fayllaridan biri topilmadi.")
        command.extend(["-i", str(audio_path)])

    filters: list[str] = []
    labels: list[str] = []
    for index, item in enumerate(recordings, start=1):
        delay_ms = max(0, int(round(float(item.get("start", 0.0)) * 1000)))
        label = f"voice{index}"
        slot_duration = max(
            0.1,
            float(item.get("end", 0.0)) - float(item.get("start", 0.0)),
        )
        recorded_duration = float(item.get("duration", 0.0) or 0.0)
        tempo_filter = ""
        if recorded_duration > 0:
            tempo_ratio = recorded_duration / slot_duration
            # Only make gentle corrections; extreme stretching harms voice quality.
            if 0.80 <= tempo_ratio <= 1.25 and abs(tempo_ratio - 1.0) >= 0.04:
                tempo_filter = f"atempo={tempo_ratio:.3f},"
        filters.append(
            f"[{index}:a]aresample=48000,"
            f"aformat=channel_layouts=stereo,"
            f"asetpts=PTS-STARTPTS,"
            f"{tempo_filter}"
            f"adelay={delay_ms}|{delay_ms}[{label}]"
        )
        labels.append(f"[{label}]")

    if len(labels) == 1:
        filters.append(f"{labels[0]}alimiter=limit=0.95,apad[dubbed_audio]")
    else:
        joined = "".join(labels)
        filters.append(
            f"{joined}amix=inputs={len(labels)}:duration=longest:"
            "dropout_transition=0:normalize=0,"
            "alimiter=limit=0.95,apad[dubbed_audio]"
        )

    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "0:v:0",
            "-map",
            "[dubbed_audio]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            "-shortest",
            str(output),
        ]
    )

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=1200,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output.unlink(missing_ok=True)
        raise RuntimeError("Videoni yig‘ish 20 daqiqadan oshdi. Qisqaroq video bilan sinab ko‘r.") from exc

    if completed.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
        output.unlink(missing_ok=True)
        error = (completed.stderr or "FFmpeg noma’lum xato qaytardi.")[-1800:]
        logger.error("Dublyaj videosini yig‘ishda FFmpeg xatosi: %s", error)
        raise RuntimeError("Tayyor videoni yig‘ib bo‘lmadi. Format yoki audio fayllarni tekshirib ko‘r.")

    return str(output)
