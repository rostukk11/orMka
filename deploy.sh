#!/usr/bin/env bash
# Однокомандний запуск бота.
# Працює на Linux/macOS з docker; якщо docker немає — fallback на venv+python.
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  echo "❌ .env не знайдено."
  echo "   cp .env.example .env  і встав туди TELEGRAM_BOT_TOKEN."
  exit 1
fi

if grep -q "TELEGRAM_BOT_TOKEN=123456:ABC" .env; then
  echo "❌ У .env досі placeholder-токен. Встав справжній токен від @BotFather."
  exit 1
fi

if command -v docker >/dev/null 2>&1; then
  echo "▶ Запускаю через Docker…"
  docker compose up -d --build
  echo "✅ Бот запущено. Логи: docker compose logs -f bot"
  exit 0
fi

echo "ℹ docker не знайдено — піду через python venv"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt
echo "✅ Залежності встановлено. Запускаю python bot.py …"
exec python -u bot.py
