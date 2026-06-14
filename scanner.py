"""Ядро: збирає ціни з усіх бірж і рахує спреди по токенах."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from config import config
from exchanges.cex import CexConnector
from exchanges.dex import DexConnector

log = logging.getLogger(__name__)


@dataclass
class SpreadResult:
    token: str
    spread_pct: float
    buy_ex: str          # де купуємо (найнижчий ask)
    buy_price: float
    sell_ex: str         # де продаємо (найвищий bid)
    sell_price: float
    # статус для арбітражу: вивід з біржі купівлі, ввід на біржу продажу
    buy_withdraw: bool | None
    sell_deposit: bool | None
    venues: int          # скільки бірж дали ціну

    @property
    def transferable(self) -> bool:
        """Чи реально перевести монету (вивід з купівлі + ввід на продаж)."""
        return bool(self.buy_withdraw) and bool(self.sell_deposit)


class Scanner:
    def __init__(self):
        self.cex = CexConnector(config.cex_exchanges, quote=config.quote)
        self.dex = DexConnector(quote=config.quote) if config.enable_dex else None
        self._tokens: list[str] = list(config.tokens)

    async def close(self) -> None:
        await self.cex.close()
        if self.dex:
            await self.dex.close()

    @property
    def venues(self) -> list[str]:
        v = list(self.cex.ids)
        if self.dex:
            v.append("DexScreener")
        return v

    async def tokens(self) -> list[str]:
        """Список токенів для сканування (із .env або авто-перетин ринків)."""
        if self._tokens:
            return self._tokens
        self._tokens = await self._auto_tokens()
        return self._tokens

    async def _auto_tokens(self) -> list[str]:
        """Якщо токени не задані — беремо найпоширеніші бази серед усіх CEX."""
        from collections import Counter

        counter: Counter[str] = Counter()
        quote = config.quote

        async def load(ex_id, ex):
            try:
                markets = await ex.load_markets()
            except Exception:  # noqa: BLE001
                return
            for sym, m in markets.items():
                if m.get("spot", True) and m.get("quote") == quote and m.get("active", True):
                    counter[m.get("base")] += 1

        await asyncio.gather(
            *(load(i, e) for i, e in self.cex.exchanges.items()), return_exceptions=True
        )
        # беремо ті, що є щонайменше на 2 біржах, топ-150 за поширеністю
        common = [tok for tok, cnt in counter.most_common() if cnt >= 2 and tok]
        result = common[:150]
        log.info("Авто-підбір токенів: %d шт.", len(result))
        return result

    async def scan(self, tokens: list[str] | None = None) -> list[SpreadResult]:
        toks = tokens if tokens is not None else await self.tokens()
        if not toks:
            return []

        cex_prices, dex_prices = await asyncio.gather(
            self.cex.fetch_prices(toks),
            self.dex.fetch_prices(toks) if self.dex else _empty(toks),
        )

        results: list[SpreadResult] = []
        for token in toks:
            quotes: dict[str, dict] = {}
            quotes.update(cex_prices.get(token, {}))
            quotes.update(dex_prices.get(token, {}))
            if len(quotes) < 2:
                continue

            res = await self._compute(token, quotes)
            if res:
                results.append(res)

        results.sort(key=lambda r: r.spread_pct, reverse=True)
        return results

    async def _compute(self, token: str, quotes: dict[str, dict]) -> SpreadResult | None:
        # купуємо там, де найнижчий ask; продаємо там, де найвищий bid
        buy_ex = min(quotes, key=lambda e: quotes[e]["ask"])
        sell_ex = max(quotes, key=lambda e: quotes[e]["bid"])
        if buy_ex == sell_ex:
            return None

        buy_price = quotes[buy_ex]["ask"]
        sell_price = quotes[sell_ex]["bid"]
        if buy_price <= 0:
            return None

        spread = (sell_price - buy_price) / buy_price * 100
        if spread <= 0:
            return None
        if config.max_spread and spread > config.max_spread:
            return None  # відсікаємо аномалії (мертві/неліквідні ринки)

        # статус вводу/виводу тільки для CEX (DEX не має такого поняття)
        buy_withdraw = None if _is_dex(buy_ex) else (
            await self.cex.currency_status(buy_ex, token)
        )["withdraw"]
        sell_deposit = None if _is_dex(sell_ex) else (
            await self.cex.currency_status(sell_ex, token)
        )["deposit"]

        return SpreadResult(
            token=token,
            spread_pct=round(spread, 2),
            buy_ex=buy_ex,
            buy_price=buy_price,
            sell_ex=sell_ex,
            sell_price=sell_price,
            buy_withdraw=buy_withdraw,
            sell_deposit=sell_deposit,
            venues=len(quotes),
        )


def _is_dex(ex_id: str) -> bool:
    return ex_id.startswith("DEX:")


async def _empty(tokens: list[str]) -> dict[str, dict]:
    return {t: {} for t in tokens}
