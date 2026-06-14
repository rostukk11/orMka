"""Робота з централізованими біржами (CEX) через ccxt.

Дає:
  * ціни (bid/ask/last) і обсяг 24г по токенах з багатьох бірж;
  * статус вводу/виводу (deposit/withdraw) монети на біржі (спот-гаманець).

Тип ринку (spot чи swap/ф'ючерси) задається у конфізі.
"""
from __future__ import annotations

import asyncio
import logging
import time

import ccxt.async_support as ccxt

log = logging.getLogger(__name__)

_CURRENCIES_TTL = 60 * 30  # 30 хв


class CexConnector:
    def __init__(self, exchange_ids: list[str], quote: str = "USDT", market_type: str = "swap"):
        self.quote = quote.upper()
        self.market_type = market_type if market_type in {"spot", "swap"} else "swap"
        self.exchanges: dict[str, ccxt.Exchange] = {}

        if len(exchange_ids) == 1 and exchange_ids[0].lower() == "all":
            exchange_ids = list(ccxt.exchanges)

        for ex_id in exchange_ids:
            try:
                klass = getattr(ccxt, ex_id)
            except AttributeError:
                log.warning("ccxt не знає біржу '%s' — пропускаю", ex_id)
                continue
            try:
                ex = klass({
                    "enableRateLimit": True,
                    "timeout": 15000,
                    "options": {"defaultType": self.market_type},
                })
                if not ex.has.get("fetchTickers") and not ex.has.get("fetchTicker"):
                    continue
                self.exchanges[ex_id] = ex
            except Exception as exc:  # noqa: BLE001
                log.warning("Не вдалося ініціалізувати %s: %s", ex_id, exc)

        self._currencies_cache: dict[str, tuple[float, dict]] = {}

    @property
    def ids(self) -> list[str]:
        return list(self.exchanges)

    @property
    def market_label(self) -> str:
        return "Futures" if self.market_type == "swap" else "Spot"

    async def close(self) -> None:
        await asyncio.gather(*(ex.close() for ex in self.exchanges.values()), return_exceptions=True)

    def _symbol(self, token: str) -> str:
        if self.market_type == "swap":
            return f"{token}/{self.quote}:{self.quote}"
        return f"{token}/{self.quote}"

    # ---------- ціни ----------
    async def fetch_prices(self, tokens: list[str]) -> dict[str, dict[str, dict]]:
        """token -> { ex_id -> {"bid","ask","last","volume"} }."""
        result: dict[str, dict[str, dict]] = {t: {} for t in tokens}
        wanted = {self._symbol(t): t for t in tokens}

        async def one(ex_id: str, ex: ccxt.Exchange) -> None:
            try:
                tickers = await self._fetch_tickers(ex, list(wanted))
            except Exception as exc:  # noqa: BLE001
                log.debug("fetch_tickers fail %s: %s", ex_id, exc)
                return
            for symbol, tick in tickers.items():
                token = wanted.get(symbol)
                if not token:
                    continue
                bid = tick.get("bid")
                ask = tick.get("ask")
                last = tick.get("last") or tick.get("close")
                if bid is None and last is not None:
                    bid = last
                if ask is None and last is not None:
                    ask = last
                if not (bid and ask):
                    continue
                volume = tick.get("quoteVolume")
                if volume is None and tick.get("baseVolume") and last:
                    volume = tick["baseVolume"] * last
                result[token][ex_id] = {
                    "bid": float(bid),
                    "ask": float(ask),
                    "last": float(last or bid),
                    "volume": float(volume or 0),
                }

        await asyncio.gather(*(one(i, e) for i, e in self.exchanges.items()), return_exceptions=True)
        return result

    async def _fetch_tickers(self, ex: ccxt.Exchange, symbols: list[str]) -> dict:
        if ex.has.get("fetchTickers"):
            try:
                return await ex.fetch_tickers(symbols)
            except Exception:  # noqa: BLE001
                return await ex.fetch_tickers()
        out: dict = {}
        for sym in symbols:
            try:
                out[sym] = await ex.fetch_ticker(sym)
            except Exception:  # noqa: BLE001
                continue
        return out

    # ---------- статус вводу/виводу ----------
    async def currency_status(self, ex_id: str, code: str) -> dict:
        currencies = await self._currencies(ex_id)
        info = currencies.get(code.upper())
        if not info:
            return {"deposit": None, "withdraw": None}
        return {"deposit": info.get("deposit"), "withdraw": info.get("withdraw")}

    async def _currencies(self, ex_id: str) -> dict:
        cached = self._currencies_cache.get(ex_id)
        if cached and time.time() - cached[0] < _CURRENCIES_TTL:
            return cached[1]

        ex = self.exchanges.get(ex_id)
        parsed: dict = {}
        if ex is not None and ex.has.get("fetchCurrencies"):
            try:
                raw = await ex.fetch_currencies() or {}
                for code, cur in raw.items():
                    if isinstance(cur, dict):
                        parsed[code.upper()] = {
                            "deposit": cur.get("deposit"),
                            "withdraw": cur.get("withdraw"),
                        }
            except Exception as exc:  # noqa: BLE001
                log.debug("fetch_currencies fail %s: %s", ex_id, exc)

        self._currencies_cache[ex_id] = (time.time(), parsed)
        return parsed
