"""Inline-клавіатури: вибір категорії, періоди, видалення."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

PERIODS = [("Сьогодні", "day"), ("Тиждень", "week"), ("Місяць", "month")]


def category_keyboard(entry_id: int, categories: dict[str, str], current: str) -> InlineKeyboardMarkup:
    """Кнопки для зміни категорії запису + видалення."""
    buttons: list[InlineKeyboardButton] = []
    for name, emoji in categories.items():
        mark = "✅ " if name == current else ""
        buttons.append(
            InlineKeyboardButton(text=f"{mark}{emoji} {name}", callback_data=f"cat:{entry_id}:{name}")
        )
    rows = [buttons[index : index + 3] for index in range(0, len(buttons), 3)]
    rows.append([InlineKeyboardButton(text="🗑 Видалити", callback_data=f"del:{entry_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def period_keyboard(active: str = "") -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(
            text=("• " if period == active else "") + title, callback_data=f"rep:{period}"
        )
        for title, period in PERIODS
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[row, [InlineKeyboardButton(text="🗂 Категорії", callback_data="cats")]]
    )


def categories_keyboard(categories: dict[str, str]) -> InlineKeyboardMarkup:
    """Кнопки категорій: показати витрати за місяць по кожній."""
    buttons = [
        InlineKeyboardButton(text=f"{emoji} {name}", callback_data=f"info:{name}")
        for name, emoji in categories.items()
    ]
    rows = [buttons[index : index + 3] for index in range(0, len(buttons), 3)]
    rows.append([InlineKeyboardButton(text="⬅️ Звіт за місяць", callback_data="rep:month")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
