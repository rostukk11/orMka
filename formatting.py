"""Форматування повідомлень для Telegram (HTML)."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import config
from links import cex_button_label, cex_url, dex_button_label
from scanner import Signal


def _flag(status: bool | None) -> str:
    if status is True:
        return "✅"
    if status is False:
        return "⛔"
    return "❔"


def _money(value: float) -> str:
    """1234567.8 -> '1 234 568' (пробіли між тисячами)."""
    return f"{int(round(value)):,}".replace(",", " ")


def _price(value: float) -> str:
    return f"{value:.8f}"


def format_signal(s: Signal) -> str:
    bullet = "🟢" if s.direction == "LONG" else "🔴"
    quote = config.quote

    # два рядки цін, дорожчий зверху
    dex_line = f"🔹 DEX: {_price(s.dex.price)} {quote}"
    cex_line = f"🔹 {s.cex_name.capitalize()}: {_price(s.cex_price)} {quote}"
    if s.cex_price > s.dex.price:
        prices = f"{cex_line}\n{dex_line}"
    else:
        prices = f"{dex_line}\n{cex_line}"

    st = s.stats
    return (
        f"📈 <b>Сигнал {s.direction} для {s.token}</b>\n\n"
        f"{prices}\n\n"
        f"{bullet} <b>Разница: {s.diff_pct:.2f}%</b>\n\n"
        f"<b>{s.cex_name.capitalize()} {s.cex_market}:</b>\n"
        f"🔹 Объём (24ч): {_money(s.cex_volume)} {quote}\n"
        f"🔹 Депозит: {_flag(s.cex_deposit)}\n"
        f"🔹 Вывод: {_flag(s.cex_withdraw)}\n\n"
        f"<b>DEX:</b>\n"
        f"🔹 Объём: {_money(s.dex.volume_h24)} {quote}\n"
        f"🔹 Ликвидность: {_money(s.dex.liquidity_usd)} {quote}\n"
        f"🔹 Сеть: {s.dex.chain}\n"
        f"🔹 Контракт: <code>{s.dex.address}</code>\n\n"
        f"<b>{s.token}</b>\n"
        f"🔹 Сигналов за день: {st.get('signals', 0)}\n"
        f"✅ Успешных сигналов: {st.get('success', 0)} ❌ Неудачных: {st.get('fail', 0)}"
    )


def build_keyboard(s: Signal) -> InlineKeyboardMarkup | None:
    """Кнопки під сигналом: DexScreener + CEX (Futures/Spot)."""
    rows: list[list[InlineKeyboardButton]] = []

    market_type = "swap" if s.cex_market.lower() == "futures" else "spot"
    cex_link = cex_url(s.cex_name, s.token, config.quote, market_type)
    if cex_link:
        rows.append([InlineKeyboardButton(
            text=cex_button_label(s.cex_name, s.token, config.quote, market_type),
            url=cex_link,
        )])

    if s.dex.pair_url:
        rows.append([InlineKeyboardButton(
            text=dex_button_label(s.dex.dex_id, s.dex.chain),
            url=s.dex.pair_url,
        )])

    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def format_list(signals: list[Signal], limit: int = 10) -> str:
    if not signals:
        return "Нічого не знайшов 🤷 — сигналів вище порогу зараз немає."
    head = signals[:limit]
    body = "\n\n➖➖➖➖➖\n\n".join(format_signal(s) for s in head)
    tail = f"\n\n…і ще {len(signals) - limit}" if len(signals) > limit else ""
    return body + tail
