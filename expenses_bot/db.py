"""SQLite-сховище: користувачі, категорії, записи."""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CATEGORIES: list[tuple[str, str]] = [
    ("їжа", "🍽"),
    ("продукти", "🛒"),
    ("транспорт", "🚌"),
    ("житло", "🏠"),
    ("звязок", "📱"),
    ("здоровя", "💊"),
    ("розваги", "🎬"),
    ("одяг", "👕"),
    ("подарунки", "🎁"),
    ("інше", "📦"),
]

# Ключові слова → категорія (для автовизначення, коли категорію не вказано явно)
KEYWORDS: dict[str, tuple[str, ...]] = {
    "їжа": ("кава", "обід", "вечеря", "сніданок", "кафе", "ресторан", "піца", "шаурма", "бургер"),
    "продукти": ("сільпо", "атб", "ашан", "новус", "варус", "фора", "магазин", "супермаркет"),
    "транспорт": ("таксі", "убер", "болт", "uber", "bolt", "метро", "автобус", "маршрутка", "бензин", "паливо", "заправка"),
    "житло": ("оренда", "квартира", "комуналка", "світло", "газ", "вода"),
    "звязок": ("київстар", "лайфселл", "водафон", "інтернет", "мобільний"),
    "здоровя": ("аптека", "ліки", "лікар", "стоматолог", "аналізи"),
    "розваги": ("кіно", "концерт", "гра", "netflix", "spotify", "youtube", "підписка"),
    "одяг": ("взуття", "кросівки", "куртка", "джинси", "футболка"),
}


@dataclass
class Entry:
    id: int
    amount: float
    kind: str  # expense | income
    category: str
    note: str
    ts: int


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    chat_id       INTEGER PRIMARY KEY,
    monthly_limit REAL NOT NULL DEFAULT 0,
    created_at    INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS categories (
    chat_id INTEGER NOT NULL,
    name    TEXT    NOT NULL,
    emoji   TEXT    NOT NULL DEFAULT '📦',
    PRIMARY KEY (chat_id, name)
);
CREATE TABLE IF NOT EXISTS entries (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id  INTEGER NOT NULL,
    amount   REAL    NOT NULL,
    kind     TEXT    NOT NULL DEFAULT 'expense',
    category TEXT    NOT NULL,
    note     TEXT    NOT NULL DEFAULT '',
    ts       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entries_chat_ts ON entries (chat_id, ts);
"""


class Storage:
    def __init__(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # --- користувач і категорії ---------------------------------------

    def ensure_user(self, chat_id: int) -> None:
        cur = self.conn.execute("SELECT 1 FROM users WHERE chat_id = ?", (chat_id,))
        if cur.fetchone():
            return
        self.conn.execute(
            "INSERT INTO users (chat_id, created_at) VALUES (?, ?)", (chat_id, int(time.time()))
        )
        self.conn.executemany(
            "INSERT OR IGNORE INTO categories (chat_id, name, emoji) VALUES (?, ?, ?)",
            [(chat_id, name, emoji) for name, emoji in DEFAULT_CATEGORIES],
        )
        self.conn.commit()

    def categories(self, chat_id: int) -> dict[str, str]:
        cur = self.conn.execute(
            "SELECT name, emoji FROM categories WHERE chat_id = ? ORDER BY name", (chat_id,)
        )
        return {row["name"]: row["emoji"] for row in cur.fetchall()}

    def add_category(self, chat_id: int, name: str, emoji: str = "📦") -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO categories (chat_id, name, emoji) VALUES (?, ?, ?)",
            (chat_id, name, emoji),
        )
        self.conn.commit()

    def remove_category(self, chat_id: int, name: str) -> bool:
        cur = self.conn.execute(
            "DELETE FROM categories WHERE chat_id = ? AND name = ?", (chat_id, name)
        )
        self.conn.commit()
        return cur.rowcount > 0

    # --- ліміт ---------------------------------------------------------

    def set_limit(self, chat_id: int, value: float) -> None:
        self.ensure_user(chat_id)
        self.conn.execute("UPDATE users SET monthly_limit = ? WHERE chat_id = ?", (value, chat_id))
        self.conn.commit()

    def get_limit(self, chat_id: int) -> float:
        cur = self.conn.execute("SELECT monthly_limit FROM users WHERE chat_id = ?", (chat_id,))
        row = cur.fetchone()
        return float(row["monthly_limit"]) if row else 0.0

    # --- записи ---------------------------------------------------------

    def add_entry(
        self, chat_id: int, amount: float, category: str, note: str, kind: str, ts: int
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO entries (chat_id, amount, kind, category, note, ts) VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, amount, kind, category, note, ts),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def update_entry_category(self, chat_id: int, entry_id: int, category: str) -> bool:
        cur = self.conn.execute(
            "UPDATE entries SET category = ? WHERE chat_id = ? AND id = ?",
            (category, chat_id, entry_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def get_entry(self, chat_id: int, entry_id: int) -> Entry | None:
        cur = self.conn.execute(
            "SELECT id, amount, kind, category, note, ts FROM entries WHERE chat_id = ? AND id = ?",
            (chat_id, entry_id),
        )
        row = cur.fetchone()
        return Entry(**dict(row)) if row else None

    def delete_entry(self, chat_id: int, entry_id: int) -> bool:
        cur = self.conn.execute(
            "DELETE FROM entries WHERE chat_id = ? AND id = ?", (chat_id, entry_id)
        )
        self.conn.commit()
        return cur.rowcount > 0

    def last_entry(self, chat_id: int) -> Entry | None:
        cur = self.conn.execute(
            "SELECT id, amount, kind, category, note, ts FROM entries "
            "WHERE chat_id = ? ORDER BY id DESC LIMIT 1",
            (chat_id,),
        )
        row = cur.fetchone()
        return Entry(**dict(row)) if row else None

    def entries_between(self, chat_id: int, start_ts: int, end_ts: int) -> list[Entry]:
        cur = self.conn.execute(
            "SELECT id, amount, kind, category, note, ts FROM entries "
            "WHERE chat_id = ? AND ts >= ? AND ts < ? ORDER BY ts",
            (chat_id, start_ts, end_ts),
        )
        return [Entry(**dict(row)) for row in cur.fetchall()]

    def all_entries(self, chat_id: int) -> list[Entry]:
        cur = self.conn.execute(
            "SELECT id, amount, kind, category, note, ts FROM entries WHERE chat_id = ? ORDER BY ts",
            (chat_id,),
        )
        return [Entry(**dict(row)) for row in cur.fetchall()]
