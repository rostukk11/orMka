"""Збереження підписників, налаштувань і статистики сигналів у JSON."""
from __future__ import annotations

import json
import logging
import threading
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

_PATH = Path(__file__).parent / "data" / "state.json"
_lock = threading.RLock()


def _load() -> dict:
    if not _PATH.exists():
        return {"subscribers": [], "settings": {}, "stats": {}}
    try:
        data = json.loads(_PATH.read_text("utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("Не вдалося прочитати state.json: %s", exc)
        return {"subscribers": [], "settings": {}, "stats": {}}
    data.setdefault("subscribers", [])
    data.setdefault("settings", {})
    data.setdefault("stats", {})
    return data


def _save(state: dict) -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")


# ---------- підписники ----------
def add_subscriber(chat_id: int) -> bool:
    with _lock:
        state = _load()
        subs = state["subscribers"]
        if chat_id in subs:
            return False
        subs.append(chat_id)
        _save(state)
        return True


def remove_subscriber(chat_id: int) -> bool:
    with _lock:
        state = _load()
        subs = state["subscribers"]
        if chat_id not in subs:
            return False
        subs.remove(chat_id)
        _save(state)
        return True


def get_subscribers() -> list[int]:
    return list(_load().get("subscribers", []))


# ---------- налаштування ----------
def get_setting(key: str, default=None):
    return _load().get("settings", {}).get(key, default)


def set_setting(key: str, value) -> None:
    with _lock:
        state = _load()
        state["settings"][key] = value
        _save(state)


# ---------- статистика сигналів ----------
def _today() -> str:
    return date.today().isoformat()


def _token_stats(state: dict, token: str) -> dict:
    day = state["stats"].setdefault(_today(), {})
    return day.setdefault(token.upper(), {"signals": 0, "success": 0, "fail": 0})


def record_signal(token: str) -> None:
    with _lock:
        state = _load()
        _token_stats(state, token)["signals"] += 1
        _save(state)


def record_outcome(token: str, success: bool) -> None:
    with _lock:
        state = _load()
        stats = _token_stats(state, token)
        stats["success" if success else "fail"] += 1
        _save(state)


def get_stats(token: str) -> dict:
    state = _load()
    day = state["stats"].get(_today(), {})
    return day.get(token.upper(), {"signals": 0, "success": 0, "fail": 0})
