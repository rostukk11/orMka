"""Форматування повідомлень для Telegram (HTML)."""
from __future__ import annotations

from config import config
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


def format_alert(signals: list[Signal]) -> str:
    return "\n\n➖➖➖➖➖\n\n".join(format_signal(s) for s in signals)


def format_list(signals: list[Signal], limit: int = 10) -> str:
    if not signals:
        return "Нічого не знайшов 🤷 — сигналів вище порогу зараз немає."
    return format_alert(signals[:limit])
