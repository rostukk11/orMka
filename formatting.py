"""Форматування повідомлень для Telegram (HTML)."""
from __future__ import annotations

from scanner import SpreadResult


def _flag(status: bool | None) -> str:
    if status is True:
        return "✅"
    if status is False:
        return "⛔"
    return "❔"  # невідомо (біржа не дала даних)


def _fmt_price(p: float) -> str:
    if p >= 1:
        return f"{p:,.4f}".rstrip("0").rstrip(".")
    return f"{p:.8f}".rstrip("0").rstrip(".")


def _venue(name: str) -> str:
    return name.replace("DEX:", "🟣 ").upper() if name.startswith("DEX:") else name


def format_spread(r: SpreadResult) -> str:
    transfer = "🔁 переказ можливий" if r.transferable else "⚠️ переказ під питанням"
    return (
        f"<b>{r.token}/USDT</b>  спред <b>{r.spread_pct:.2f}%</b>\n"
        f"🟢 Купити: <b>{_venue(r.buy_ex)}</b> @ {_fmt_price(r.buy_price)}  "
        f"(вивід {_flag(r.buy_withdraw)})\n"
        f"🔴 Продати: <b>{_venue(r.sell_ex)}</b> @ {_fmt_price(r.sell_price)}  "
        f"(ввід {_flag(r.sell_deposit)})\n"
        f"{transfer} · бірж із ціною: {r.venues}"
    )


def format_alert(results: list[SpreadResult]) -> str:
    head = f"🚨 <b>Знайдено спреди</b> ({len(results)}):\n\n"
    return head + "\n\n".join(format_spread(r) for r in results)


def format_list(results: list[SpreadResult], limit: int = 15) -> str:
    if not results:
        return "Нічого не знайшов 🤷 — спредів вище порогу зараз немає."
    shown = results[:limit]
    body = "\n\n".join(format_spread(r) for r in shown)
    tail = f"\n\n…і ще {len(results) - limit}" if len(results) > limit else ""
    return f"📊 <b>Топ спредів</b> ({len(results)}):\n\n{body}{tail}"
