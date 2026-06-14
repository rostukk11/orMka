"""Робота з централізованими біржами (CEX) через ccxt.

Дає:
  * ціни (bid/ask) по токенах одразу з багатьох бірж;
  * статус вводу/виводу (deposit/withdraw) кожної монети на біржі.
"""
from __future__ import annotations

import asyncio
import logging
import time

import ccxt.async_support as ccxt

log = logging.getLogger(__name__)

# Як часто оновлювати довідник монет (статус вводу/виводу) — він міняється рідко.
_CURRENCIES_TTL = 60 * 30  # 30 хв


class CexConnector:
    def __init__(self, exchange_ids: list[str], quote: str = "USDT"):
        self.quote = quote.upper()
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
                ex = klass({"enableRateLimit": True, "timeout": 15000})
                if not ex.has.get("fetchTickers") and not ex.has.get("fetchTicker"):
                    log.info("Біржа %s не вміє читати тікери — пропускаю", ex_id)
                    continue
                self.exchanges[ex_id] = ex
            except Exception as exc:  # noqa: BLE001
                log.warning("Не вдалося ініціалізувати %s: %s", ex_id, exc)

        # кеш довідника монет: ex_id -> (timestamp, {CODE: {"deposit":bool,"withdraw":bool,"networks":..}})
        self._currencies_cache: dict[str, tuple[float, dict]] = {}

    @property
    def ids(self) -> list[str]:
        return list(self.exchanges)

    async def close(self) -> None:
        await asyncio.gather(
            *(ex.close() for ex in self.exchanges.values()), return_exceptions=True
        )

    # ---------- ціни ----------
    async def fetch_prices(self, tokens: list[str]) -> dict[str, dict[str, dict]]:
        """token -> { ex_id -> {"bid":float,"ask":float,"last":float} }."""
        result: dict[str, dict[str, dict]] = {t: {} for t in tokens}
        wanted = {f"{t}/{self.quote}": t for t in tokens}

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
                # дозволяємо працювати навіть якщо є лише last
                if bid is None and last is not None:
                    bid = last
                if ask is None and last is not None:
                    ask = last
                if bid and ask:
                    result[token][ex_id] = {"bid": float(bid), "ask": float(ask), "last": float(last or bid)}

        await asyncio.gather(*(one(i, e) for i, e in self.exchanges.items()), return_exceptions=True)
        return result

    async def _fetch_tickers(self, ex: ccxt.Exchange, symbols: list[str]) -> dict:
        if ex.has.get("fetchTickers"):
            try:
                # частина бірж не вміє фільтрувати — тоді тягнемо всі
                return await ex.fetch_tickers(symbols)
            except Exception:  # noqa: BLE001
                return await ex.fetch_tickers()
        # поодинокі запити (повільно, але працює)
        out: dict = {}
        for sym in symbols:
            try:
                out[sym] = await ex.fetch_ticker(sym)
            except Exception:  # noqa: BLE001
                continue
        return out

    # ---------- статус вводу/виводу ----------
    async def currency_status(self, ex_id: str, code: str) -> dict:
        """Повертає {"deposit":bool|None,"withdraw":bool|None} для монети на біржі."""
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
                    if not isinstance(cur, dict):
                        continue
                    parsed[code.upper()] = {
                        "deposit": cur.get("deposit"),
                        "withdraw": cur.get("withdraw"),
                        "active": cur.get("active"),
                    }
            except Exception as exc:  # noqa: BLE001
                log.debug("fetch_currencies fail %s: %s", ex_id, exc)

        self._currencies_cache[ex_id] = (time.time(), parsed)
        return parsed
