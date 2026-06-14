"""Ціни та метадані з DEX через публічний API DexScreener (без ключів)."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import aiohttp

log = logging.getLogger(__name__)

_SEARCH_URL = "https://api.dexscreener.com/latest/dex/search"
_STABLES = {"USDT", "USDC", "DAI", "BUSD", "USD"}


@dataclass
class DexInfo:
    price: float          # ціна в USD
    volume_h24: float     # обсяг за 24г, USD
    liquidity_usd: float  # ліквідність пулу, USD
    chain: str            # мережа (bsc, ethereum, solana, ...)
    dex_id: str           # назва DEX (uniswap, pancakeswap, raydium, ...)
    address: str          # адреса контракту токена


class DexConnector:
    def __init__(self, quote: str = "USDT"):
        self.quote = quote.upper()
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def fetch(self, tokens: list[str]) -> dict[str, DexInfo | None]:
        result: dict[str, DexInfo | None] = {t: None for t in tokens}
        await asyncio.gather(*(self._one(t, result) for t in tokens), return_exceptions=True)
        return result

    async def _one(self, token: str, result: dict) -> None:
        try:
            session = await self._get_session()
            async with session.get(_SEARCH_URL, params={"q": f"{token} {self.quote}"}) as resp:
                if resp.status != 200:
                    return
                data = await resp.json()
        except Exception as exc:  # noqa: BLE001
            log.debug("DexScreener fail %s: %s", token, exc)
            return

        best: DexInfo | None = None
        best_liq = -1.0
        for pair in data.get("pairs") or []:
            base = (pair.get("baseToken") or {}).get("symbol", "").upper()
            quote_sym = (pair.get("quoteToken") or {}).get("symbol", "").upper()
            if base != token.upper() or quote_sym not in _STABLES:
                continue
            price = pair.get("priceUsd")
            if not price:
                continue
            liquidity = float((pair.get("liquidity") or {}).get("usd") or 0)
            # обираємо найліквіднішу пару
            if liquidity <= best_liq:
                continue
            best_liq = liquidity
            best = DexInfo(
                price=float(price),
                volume_h24=float((pair.get("volume") or {}).get("h24") or 0),
                liquidity_usd=liquidity,
                chain=pair.get("chainId", "?"),
                dex_id=pair.get("dexId", "dex"),
                address=(pair.get("baseToken") or {}).get("address", ""),
            )

        result[token] = best
