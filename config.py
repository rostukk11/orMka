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

    # Тип ринку на CEX: "swap" (ф'ючерси/безстрокові) або "spot"
    market_type: str = field(default_factory=lambda: os.getenv("MARKET_TYPE", "swap").lower())

    # Мінімальна ліквідність/обсяг DEX-пари, щоб не ловити сміття (USD), 0 = вимкнено
    min_dex_liquidity: float = field(default_factory=lambda: float(os.getenv("MIN_DEX_LIQUIDITY", "10000")))

    # Оцінка успішності сигналу: за скільки секунд закривати сигнал
    signal_ttl: int = field(default_factory=lambda: int(os.getenv("SIGNAL_TTL", "1800")))
    # Сигнал = успішний, якщо різниця стиснулась нижче цієї частки від стартової
    success_convergence: float = field(default_factory=lambda: float(os.getenv("SUCCESS_CONVERGENCE", "0.5")))

    cex_exchanges: list[str] = field(
        default_factory=lambda: _split(os.getenv("CEX_EXCHANGES", "binance,bybit,okx,kucoin,gate,mexc"))
    )

    tokens: list[str] = field(default_factory=lambda: _split(os.getenv("TOKENS", "")))

    def validate(self) -> None:
        if not self.bot_token:
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN не заданий. Скопіюй .env.example у .env і встав токен від @BotFather."
            )


config = Config()
