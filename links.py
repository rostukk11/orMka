"""Білдери URL до сторінок торгової пари на CEX.

Окремі шаблони для futures (swap) і spot. Якщо біржі немає у мапі,
повертаємо fallback на головну сторінку.
"""
from __future__ import annotations

# token, quote (нижнього й верхнього регістру) підставляться шаблоном
_FUTURES: dict[str, str] = {
    "binance":  "https://www.binance.com/en/futures/{T}{Q}",
    "bybit":    "https://www.bybit.com/trade/usdt/{T}{Q}",
    "okx":      "https://www.okx.com/trade-swap/{t}-{q}-swap",
    "kucoin":   "https://www.kucoin.com/futures/trade/{T}{Q}M",
    "gate":     "https://www.gate.io/futures/{Q}/{T}_{Q}",
    "mexc":     "https://futures.mexc.com/exchange/{T}_{Q}",
    "bitget":   "https://www.bitget.com/futures/usdt/{T}{Q}",
    "htx":      "https://www.htx.com/futures/linear_swap/exchange/?contract_code={T}-{Q}",
    "kraken":   "https://futures.kraken.com/trade/futures/PF_{T}USD",
    "coinbase": "https://www.coinbase.com/advanced-trade/spot/{T}-{Q}",  # у Coinbase Pro немає ф'ючерсів
}

_SPOT: dict[str, str] = {
    "binance":  "https://www.binance.com/en/trade/{T}_{Q}",
    "bybit":    "https://www.bybit.com/en-US/trade/spot/{T}/{Q}",
    "okx":      "https://www.okx.com/trade-spot/{t}-{q}",
    "kucoin":   "https://www.kucoin.com/trade/{T}-{Q}",
    "gate":     "https://www.gate.io/trade/{T}_{Q}",
    "mexc":     "https://www.mexc.com/exchange/{T}_{Q}",
    "bitget":   "https://www.bitget.com/spot/{T}{Q}",
    "htx":      "https://www.htx.com/en-us/trade/{t}_{q}/",
    "kraken":   "https://pro.kraken.com/app/trade/{t}-{q}",
    "coinbase": "https://www.coinbase.com/advanced-trade/spot/{T}-{Q}",
}


def cex_url(exchange: str, token: str, quote: str, market_type: str = "swap") -> str:
    table = _FUTURES if market_type == "swap" else _SPOT
    template = table.get(exchange.lower())
    if not template:
        return f"https://www.google.com/search?q={exchange}+{token}+{quote}+{market_type}"
    return template.format(
        T=token.upper(), Q=quote.upper(),
        t=token.lower(), q=quote.lower(),
    )


def cex_button_label(exchange: str, token: str, quote: str, market_type: str = "swap") -> str:
    market = "Futures" if market_type == "swap" else "Spot"
    return f"📈 {exchange.capitalize()} {market}: {token.upper()}/{quote.upper()}"


def dex_button_label(dex_id: str, chain: str) -> str:
    return f"📊 DexScreener: {dex_id} @ {chain}"
