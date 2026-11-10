import json
import logging
import os
from pathlib import Path
from typing import Any

from config import SESSIONS_FILE, UPLOADS_DIR

logger = logging.getLogger(__name__)


def _read_all() -> dict[str, dict[str, Any]]:
    if not SESSIONS_FILE.exists():
        return {}
    try:
        data = json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        logger.exception("Sessiya faylini o‘qib bo‘lmadi")
        return {}


def _write_all(data: dict[str, dict[str, Any]]) -> None:
    SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = SESSIONS_FILE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, SESSIONS_FILE)


def get_session(user_id: int) -> dict[str, Any] | None:
    return _read_all().get(str(user_id))


def save_session(user_id: int, session: dict[str, Any]) -> None:
    data = _read_all()
    data[str(user_id)] = session
    _write_all(data)


def delete_session(user_id: int) -> dict[str, Any] | None:
    data = _read_all()
    previous = data.pop(str(user_id), None)
    _write_all(data)
    return previous


def delete_session_if_matches(user_id: int, expected_video_path: str) -> dict[str, Any] | None:
    """Delete a session only when it still points to the scene being evaluated."""
    data = _read_all()
    key = str(user_id)
    current = data.get(key)
    if not current or current.get("video_path") != expected_video_path:
        return None
    previous = data.pop(key)
    _write_all(data)
    return previous


def remove_local_file(path_value: str | None) -> None:
    if not path_value:
        return
    try:
        path = Path(path_value).resolve()
        uploads_root = UPLOADS_DIR.resolve()
        if uploads_root in path.parents and path.is_file():
            path.unlink()
    except OSError:
        logger.warning("Vaqtinchalik faylni o‘chirib bo‘lmadi: %s", path_value)
