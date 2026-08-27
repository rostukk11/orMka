"""Конфіг бота витрат (з .env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    bot_token: str = field(default_factory=lambda: os.getenv("EXPENSES_BOT_TOKEN", ""))
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", "data/expenses.db"))
    currency: str = field(default_factory=lambda: os.getenv("CURRENCY", "грн"))
    timezone: str = field(default_factory=lambda: os.getenv("TZ", "Europe/Kyiv"))

    def validate(self) -> None:
        if not self.bot_token:
            raise RuntimeError(
                "EXPENSES_BOT_TOKEN не заданий. Скопіюй .env.example у .env "
                "і встав токен @rozhodnikibot від @BotFather."
            )


config = Config()
