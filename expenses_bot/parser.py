"""Розбір повідомлення на суму, категорію і коментар."""
from __future__ import annotations

import re
from dataclasses import dataclass

from db import KEYWORDS

AMOUNT_RE = re.compile(r"^([+-]?\d+(?:[.,]\d+)?)([kк])?$", re.IGNORECASE)


@dataclass
class Parsed:
    amount: float
    kind: str  # expense | income
    category: str
    note: str


def normalize(word: str) -> str:
    """Прибирає апострофи і зводить до нижнього регістру: З'ВЯЗОК → звязок."""
    return re.sub(r"[’'ʼ`]", "", word.strip().lower())


def _match_category(word: str, categories: dict[str, str]) -> str | None:
    word = normalize(word)
    if not word:
        return None
    names = [normalize(name) for name in categories]
    if word in names:
        return list(categories)[names.index(word)]
    if len(word) >= 3:
        hits = [name for name, norm in zip(categories, names) if norm.startswith(word)]
        if len(hits) == 1:
            return hits[0]
    return None


def _matches_keyword(token: str, keyword: str) -> bool:
    """Слово збігається з ключовим з поправкою на відмінок: «кави» ~ «кава»,
    але «водафон» не є «вода»."""
    if token == keyword:
        return True
    stem = keyword[:-1] if len(keyword) >= 4 else keyword
    return token.startswith(stem) and len(token) <= len(keyword) + 1


def _guess_category(text: str, categories: dict[str, str]) -> str:
    tokens = [normalize(token) for token in re.split(r"[^\w]+", text) if token]
    for category, words in KEYWORDS.items():
        if category not in categories:
            continue
        if any(_matches_keyword(token, word) for token in tokens for word in words):
            return category
    return "інше" if "інше" in categories else (list(categories)[0] if categories else "інше")


def parse(text: str, categories: dict[str, str]) -> Parsed | None:
    """`250 їжа обід` / `їжа 250` / `250 кава` / `+5000 зарплата` → Parsed."""
    tokens = text.split()
    if not tokens:
        return None

    amount: float | None = None
    kind = "expense"
    rest: list[str] = []

    for token in tokens:
        match = AMOUNT_RE.match(token) if amount is None else None
        if match:
            value = float(match.group(1).replace(",", "."))
            if match.group(2):
                value *= 1000
            if value == 0:
                return None
            kind = "income" if value > 0 and token.startswith("+") else "expense"
            amount = abs(value)
            continue
        rest.append(token)

    if amount is None:
        return None

    category: str | None = None
    note_tokens: list[str] = []
    for token in rest:
        if category is None:
            found = _match_category(token, categories)
            if found:
                category = found
                continue
        note_tokens.append(token)

    note = " ".join(note_tokens).strip()
    if category is None:
        category = "дохід" if kind == "income" else _guess_category(" ".join(rest), categories)

    return Parsed(amount=amount, kind=kind, category=category, note=note)
