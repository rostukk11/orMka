"""Ядро: порівнює ціну токена на DEX і CEX, формує сигнали LONG/SHORT."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from config import config
from exchanges.cex import CexConnector
from exchanges.dex import DexConnector, DexInfo

log = logging.getLogger(__name__)


@dataclass
class Signal:
    token: str
    direction: str          # "LONG" або "SHORT" (по CEX)
    diff_pct: float         # |max-min| / max * 100

    cex_name: str
    cex_price: float
    cex_market: str         # "Futures" / "Spot"
    cex_volume: float
    cex_deposit: bool | None
    cex_withdraw: bool | None

    dex: DexInfo

    stats: dict = field(default_factory=lambda: {"signals": 0, "success": 0, "fail": 0})


# відкритий сигнал для оцінки успішності
@dataclass
class _Pending:
    token: str
    start_diff: float
    ts: float


class Scanner:
    def __init__(self):
        self.cex = CexConnector(config.cex_exchanges, quote=config.quote, market_type=config.market_type)
        self.dex = DexConnector(quote=config.quote)
        self._tokens: list[str] = list(config.tokens)
        self._pending: dict[str, _Pending] = {}

    async def close(self) -> None:
        await self.cex.close()
        await self.dex.close()

    @property
    def venues(self) -> list[str]:
        return [f"{i} ({self.cex.market_label})" for i in self.cex.ids] + ["DexScreener (DEX)"]

    async def tokens(self) -> list[str]:
        if self._tokens:
            return self._tokens
        self._tokens = await self._auto_tokens()
        return self._tokens

    async def _auto_tokens(self) -> list[str]:
        from collections import Counter

        counter: Counter[str] = Counter()
        quote = config.quote

        async def load(ex_id, ex):
            try:
                markets = await ex.load_markets()
            except Exception:  # noqa: BLE001
                return
            for m in markets.values():
                if m.get("quote") == quote and m.get("active", True):
                    base = m.get("base")
                    if base:
                        counter[base] += 1

        await asyncio.gather(*(load(i, e) for i, e in self.cex.exchanges.items()), return_exceptions=True)
        result = [tok for tok, cnt in counter.most_common(200) if cnt >= 1]
        log.info("Авто-підбір токенів: %d шт.", len(result))
        return result

    async def scan(self, tokens: list[str] | None = None) -> list[Signal]:
        toks = tokens if tokens is not None else await self.tokens()
        if not toks:
            return []

        cex_prices, dex_info = await asyncio.gather(
            self.cex.fetch_prices(toks),
            self.dex.fetch(toks),
        )

        signals: list[Signal] = []
        for token in toks:
            dex = dex_info.get(token)
            if dex is None or dex.price <= 0:
                continue
            if config.min_dex_liquidity and dex.liquidity_usd < config.min_dex_liquidity:
                continue
            venues = cex_prices.get(token, {})
            if not venues:
                continue

            sig = await self._build(token, dex, venues)
            if sig:
                signals.append(sig)

        signals.sort(key=lambda s: s.diff_pct, reverse=True)
        self._evaluate_pending(signals)
        return signals

    async def _build(self, token: str, dex: DexInfo, venues: dict[str, dict]) -> Signal | None:
        # обираємо CEX з найбільшою різницею до DEX-ціни
        best_ex = max(venues, key=lambda e: abs(dex.price - venues[e]["last"]) / max(dex.price, venues[e]["last"]))
        cex = venues[best_ex]
        cex_price = cex["last"]
        if cex_price <= 0:
            return None

        hi = max(dex.price, cex_price)
        lo = min(dex.price, cex_price)
        diff = (hi - lo) / hi * 100
        if diff <= 0:
            return None
        if config.max_spread and diff > config.max_spread:
            return None

        # DEX дорожче за CEX -> ціна підтягнеться вгору -> LONG на CEX, інакше SHORT
        direction = "LONG" if dex.price > cex_price else "SHORT"

        status = await self.cex.currency_status(best_ex, token)

        from storage import get_stats  # локальний імпорт, щоб уникнути циклів
        return Signal(
            token=token,
            direction=direction,
            diff_pct=round(diff, 2),
            cex_name=best_ex,
            cex_price=cex_price,
            cex_market=self.cex.market_label,
            cex_volume=cex["volume"],
            cex_deposit=status["deposit"],
            cex_withdraw=status["withdraw"],
            dex=dex,
            stats=get_stats(token),
        )

    # ---------- оцінка успішності ----------
    def open_signal(self, signal: Signal) -> None:
        """Зафіксувати відкритий сигнал (викликається при відправці алерта)."""
        self._pending[signal.token] = _Pending(signal.token, signal.diff_pct, time.time())

    def _evaluate_pending(self, current: list[Signal]) -> None:
        """Закриваємо відкриті сигнали: різниця стиснулась -> успіх; вийшов TTL -> невдача."""
        if not self._pending:
            return
        from storage import record_outcome

        now = time.time()
        diffs = {s.token: s.diff_pct for s in current}
        done: list[str] = []
        for token, pend in self._pending.items():
            cur = diffs.get(token, 0.0)
            if cur <= pend.start_diff * config.success_convergence:
                record_outcome(token, True)
                done.append(token)
            elif now - pend.ts >= config.signal_ttl:
                record_outcome(token, False)
                done.append(token)
        for token in done:
            self._pending.pop(token, None)
