"""Завантаження конфігурації з оточення (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _bool(value: str, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "y"}


@dataclass
class Config:
    bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    default_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))

    quote: str = field(default_factory=lambda: os.getenv("QUOTE", "USDT").upper())
    min_spread: float = field(default_factory=lambda: float(os.getenv("MIN_SPREAD_PERCENT", "1.0")))
    max_spread: float = field(default_factory=lambda: float(os.getenv("MAX_SPREAD_PERCENT", "50")))
    scan_interval: int = field(default_factory=lambda: int(os.getenv("SCAN_INTERVAL", "60")))
    alert_cooldown: int = field(default_factory=lambda: int(os.getenv("ALERT_COOLDOWN", "900")))

    cex_exchanges: list[str] = field(
        default_factory=lambda: _split(os.getenv("CEX_EXCHANGES", "binance,bybit,okx,kucoin,gate,mexc"))
    )
    enable_dex: bool = field(default_factory=lambda: _bool(os.getenv("ENABLE_DEX"), True))

    tokens: list[str] = field(default_factory=lambda: _split(os.getenv("TOKENS", "")))

    def validate(self) -> None:
        if not self.bot_token:
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN не заданий. Скопіюй .env.example у .env і встав токен від @BotFather."
            )


config = Config()
