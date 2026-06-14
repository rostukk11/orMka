"""Просте збереження підписників та налаштувань у JSON-файл."""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

log = logging.getLogger(__name__)

_PATH = Path(__file__).parent / "data" / "state.json"
_lock = threading.Lock()


def _load() -> dict:
    if not _PATH.exists():
        return {"subscribers": [], "settings": {}}
    try:
        return json.loads(_PATH.read_text("utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("Не вдалося прочитати state.json: %s", exc)
        return {"subscribers": [], "settings": {}}


def _save(state: dict) -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")


def add_subscriber(chat_id: int) -> bool:
    with _lock:
        state = _load()
        subs = state.setdefault("subscribers", [])
        if chat_id in subs:
            return False
        subs.append(chat_id)
        _save(state)
        return True


def remove_subscriber(chat_id: int) -> bool:
    with _lock:
        state = _load()
        subs = state.setdefault("subscribers", [])
        if chat_id not in subs:
            return False
        subs.remove(chat_id)
        _save(state)
        return True


def get_subscribers() -> list[int]:
    return list(_load().get("subscribers", []))


def get_setting(key: str, default=None):
    return _load().get("settings", {}).get(key, default)


def set_setting(key: str, value) -> None:
    with _lock:
        state = _load()
        state.setdefault("settings", {})[key] = value
        _save(state)
