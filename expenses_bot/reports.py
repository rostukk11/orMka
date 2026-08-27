"""Підсумки за період і форматування повідомлень."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from db import Entry

BAR_WIDTH = 10
MONTHS = [
    "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
]


def money(value: float) -> str:
    """1234.5 → '1 234,50'; 250.0 → '250'."""
    text = f"{value:,.2f}".replace(",", " ").replace(".", ",")
    return text[:-3] if text.endswith(",00") else text


def now(tz: str) -> datetime:
    return datetime.now(ZoneInfo(tz))


def period_bounds(period: str, tz: str) -> tuple[int, int, str]:
    """Межі періоду (unix-час) і його назва."""
    zone = ZoneInfo(tz)
    current = datetime.now(zone)
    today = current.replace(hour=0, minute=0, second=0, microsecond=0)

    if period == "day":
        start, end = today, today + timedelta(days=1)
        label = f"сьогодні, {start.day} {MONTHS[start.month - 1]}"
    elif period == "yesterday":
        start, end = today - timedelta(days=1), today
        label = f"вчора, {start.day} {MONTHS[start.month - 1]}"
    elif period == "week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=7)
        label = f"тиждень з {start.day} {MONTHS[start.month - 1]}"
    else:  # month
        start = today.replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1)
        label = f"{MONTHS[start.month - 1]} {start.year}"

    return int(start.timestamp()), int(end.timestamp()), label


def month_bounds(tz: str) -> tuple[int, int]:
    start, end, _ = period_bounds("month", tz)
    return start, end


def _bar(share: float) -> str:
    filled = max(1, round(share * BAR_WIDTH)) if share > 0 else 0
    return "▰" * filled + "▱" * (BAR_WIDTH - filled)


def format_report(
    entries: list[Entry],
    label: str,
    currency: str,
    emojis: dict[str, str],
    limit: float = 0.0,
    limit_spent: float | None = None,
) -> str:
    expenses = [entry for entry in entries if entry.kind == "expense"]
    incomes = [entry for entry in entries if entry.kind == "income"]
    total = sum(entry.amount for entry in expenses)

    if not entries:
        return f"📊 <b>{label}</b>\n\nЗаписів немає. Надішли, наприклад: <code>250 їжа обід</code>"

    lines = [f"📊 <b>{label}</b>", ""]

    if expenses:
        by_category: dict[str, float] = {}
        for entry in expenses:
            by_category[entry.category] = by_category.get(entry.category, 0) + entry.amount
        for category, amount in sorted(by_category.items(), key=lambda item: -item[1]):
            share = amount / total if total else 0
            emoji = emojis.get(category, "📦")
            lines.append(
                f"{emoji} <b>{category}</b> — {money(amount)} {currency}  "
                f"<i>{share * 100:.0f}%</i>\n{_bar(share)}"
            )
        lines.append("")
        lines.append(f"💸 <b>Разом витрат: {money(total)} {currency}</b>")

    if incomes:
        income_total = sum(entry.amount for entry in incomes)
        lines.append(f"💰 Доходи: +{money(income_total)} {currency}")
        lines.append(f"⚖️ Баланс: {money(income_total - total)} {currency}")

    if limit > 0:
        spent = total if limit_spent is None else limit_spent
        share = spent / limit
        icon = "🟢" if share < 0.8 else ("🟡" if share <= 1 else "🔴")
        left = limit - spent
        left_text = (
            f"лишилось {money(left)} {currency}"
            if left >= 0
            else f"перевитрата {money(-left)} {currency}"
        )
        lines.append("")
        lines.append(
            f"{icon} Місячний ліміт: {money(spent)} / {money(limit)} {currency} "
            f"({share * 100:.0f}%) — {left_text}"
        )

    return "\n".join(lines)


def format_added(
    entry_id: int,
    amount: float,
    kind: str,
    category: str,
    note: str,
    emoji: str,
    currency: str,
    month_spent: float,
    limit: float,
) -> str:
    sign = "+" if kind == "income" else "−"
    head = "💰 Дохід" if kind == "income" else "✅ Записав"
    lines = [
        f"{head}: {sign}{money(amount)} {currency} · {emoji} <b>{category}</b>"
        + (f"\n<i>{note}</i>" if note else "")
    ]

    if kind == "expense":
        lines.append(f"\nЗа місяць: {money(month_spent)} {currency}")
        if limit > 0:
            share = month_spent / limit
            if share > 1:
                lines.append(f"🔴 Ліміт перевищено на {money(month_spent - limit)} {currency}!")
            elif share >= 0.8:
                lines.append(f"🟡 Витрачено {share * 100:.0f}% ліміту, лишилось {money(limit - month_spent)} {currency}")
            else:
                lines.append(f"🟢 Лишилось {money(limit - month_spent)} {currency} до ліміту")

    lines.append(f"\n<code>/del {entry_id}</code> — видалити")
    return "\n".join(lines)
