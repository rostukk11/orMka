"""Ціни з DEX через публічний API DexScreener (без ключів).

DEX не має поняття "ввід/вивід" — токени просто лежать у гаманці,
тож для DEX статус депозиту/виводу не повертаємо.
"""
from __future__ import annotations

import asyncio
import logging

import aiohttp

log = logging.getLogger(__name__)

_SEARCH_URL = "https://api.dexscreener.com/latest/dex/search"
# беремо найліквіднішу пару токена проти стейбла на найбільшому DEX
_STABLES = {"USDT", "USDC", "DAI", "BUSD"}


class DexConnector:
    def __init__(self, quote: str = "USDT"):
        self.quote = quote.upper()
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15)
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def fetch_prices(self, tokens: list[str]) -> dict[str, dict[str, dict]]:
        """token -> { "DEX:<chain>/<dex>" -> {"bid","ask","last", "dex":True} }."""
        result: dict[str, dict[str, dict]] = {t: {} for t in tokens}
        await asyncio.gather(
            *(self._one(t, result) for t in tokens), return_exceptions=True
        )
        return result

    async def _one(self, token: str, result: dict) -> None:
        try:
            session = await self._get_session()
            async with session.get(_SEARCH_URL, params={"q": f"{token}/{self.quote}"}) as resp:
                if resp.status != 200:
                    return
                data = await resp.json()
        except Exception as exc:  # noqa: BLE001
            log.debug("DexScreener fail %s: %s", token, exc)
            return

        pairs = data.get("pairs") or []
        best = None
        for pair in pairs:
            base = (pair.get("baseToken") or {}).get("symbol", "").upper()
            quote_sym = (pair.get("quoteToken") or {}).get("symbol", "").upper()
            if base != token.upper():
                continue
            if quote_sym not in _STABLES:
                continue
            price = pair.get("priceUsd")
            liquidity = (pair.get("liquidity") or {}).get("usd") or 0
            if not price:
                continue
            if best is None or liquidity > best[1]:
                best = (pair, float(liquidity), float(price))

        if best is None:
            return
        pair, _liq, price = best
        chain = pair.get("chainId", "?")
        dex_id = pair.get("dexId", "dex")
        key = f"DEX:{dex_id}@{chain}"
        # На DEX немає окремих bid/ask — ціна одна (з урахуванням сліпеджу).
        result[token][key] = {"bid": price, "ask": price, "last": price, "dex": True}
