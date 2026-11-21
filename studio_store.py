import json
import logging
import os
from pathlib import Path
from typing import Any

from config import DATA_DIR, UPLOADS_DIR

logger = logging.getLogger(__name__)
STUDIO_SESSIONS_FILE = DATA_DIR / "studio_sessions.json"


def _read_all() -> dict[str, dict[str, Any]]:
    if not STUDIO_SESSIONS_FILE.exists():
        return {}
    try:
        data = json.loads(STUDIO_SESSIONS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        logger.exception("Dublyaj Studio sessiyalarini o‘qib bo‘lmadi")
        return {}


def _write_all(data: dict[str, dict[str, Any]]) -> None:
    STUDIO_SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STUDIO_SESSIONS_FILE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, STUDIO_SESSIONS_FILE)


def get_studio_session(user_id: int) -> dict[str, Any] | None:
    return _read_all().get(str(user_id))


def save_studio_session(user_id: int, session: dict[str, Any]) -> None:
    data = _read_all()
    data[str(user_id)] = session
    _write_all(data)


def clear_studio_session(user_id: int) -> dict[str, Any] | None:
    data = _read_all()
    previous = data.pop(str(user_id), None)
    _write_all(data)

    if not previous:
        return None

    paths = [previous.get("video_path"), previous.get("output_path")]
    paths.extend(item.get("file_path") for item in previous.get("recordings", []))
    uploads_root = UPLOADS_DIR.resolve()

    for path_value in paths:
        if not path_value:
            continue
        try:
            path = Path(path_value).resolve()
            if uploads_root in path.parents and path.is_file():
                path.unlink()
        except OSError:
            logger.warning("Dublyaj Studio faylini o‘chirib bo‘lmadi: %s", path_value)

    return previous
