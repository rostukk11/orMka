"""Telegram-бот для моніторингу спредів DEX ↔ CEX.

Команди:
  /start            — підписатися на авто-сигнали
  /stop             — відписатися
  /signal [TOKEN]   — сигнал по токену (або топ зараз)
  /top              — топ сигналів зараз
  /threshold N      — змінити поріг різниці (%)
  /status           — поточні налаштування й біржі
  /help             — довідка
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

import storage
from config import config
from formatting import format_list, format_signal
from scanner import Scanner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("spread-bot")

dp = Dispatcher()
scanner = Scanner()

_last_alert: dict[str, float] = {}


def _threshold() -> float:
    return float(storage.get_setting("min_spread", config.min_spread))


HELP = (
    "🤖 <b>Spread Scanner Bot</b>\n\n"
    "Слідкую за різницею ціни токена між <b>DEX</b> і <b>CEX</b> ({market}) "
    "і шлю сигнал LONG/SHORT, коли різниця перевищує поріг.\n\n"
    "<b>Команди:</b>\n"
    "/start — підписатися на авто-сигнали\n"
    "/stop — відписатися\n"
    "/top — топ сигналів зараз\n"
    "/signal LAB — сигнал по конкретному токену\n"
    "/threshold 5 — поріг різниці = 5%\n"
    "/status — налаштування й список бірж\n"
    "/help — ця довідка"
).format(market="Futures" if config.market_type == "swap" else "Spot")


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    is_new = storage.add_subscriber(message.chat.id)
    note = "Підписку оформлено ✅" if is_new else "Ти вже підписаний ✅"
    await message.answer(f"{note}\nПоріг різниці: <b>{_threshold():.2f}%</b>\n\n{HELP}")


@dp.message(Command("stop"))
async def cmd_stop(message: Message) -> None:
    removed = storage.remove_subscriber(message.chat.id)
    await message.answer("Відписано 🔕" if removed else "Ти й так не підписаний.")


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP)


@dp.message(Command("status"))
async def cmd_status(message: Message) -> None:
    toks = await scanner.tokens()
    venues = scanner.venues
    text = (
        f"⚙️ <b>Налаштування</b>\n"
        f"Поріг різниці: <b>{_threshold():.2f}%</b>\n"
        f"Інтервал сканування: {config.scan_interval} с\n"
        f"Ринок CEX: {scanner.cex.market_label}\n"
        f"Котирувальна валюта: {config.quote}\n"
        f"Підписників: {len(storage.get_subscribers())}\n\n"
        f"<b>Біржі ({len(venues)}):</b> {html.quote(', '.join(venues))}\n"
        f"<b>Токенів у моніторингу:</b> {len(toks)}"
    )
    await message.answer(text)


@dp.message(Command("threshold"))
async def cmd_threshold(message: Message, command: CommandObject) -> None:
    if not command.args:
        await message.answer(f"Поточний поріг: <b>{_threshold():.2f}%</b>\nЗмінити: /threshold 5")
        return
    try:
        value = float(command.args.replace(",", ".").strip())
    except ValueError:
        await message.answer("Не зрозумів число. Приклад: /threshold 5")
        return
    if value <= 0:
        await message.answer("Поріг має бути більше 0.")
        return
    storage.set_setting("min_spread", value)
    await message.answer(f"Готово. Новий поріг різниці: <b>{value:.2f}%</b>")


@dp.message(Command("top"))
async def cmd_top(message: Message) -> None:
    await message.answer("Сканую біржі… ⏳")
    signals = await scanner.scan()
    signals = [s for s in signals if s.diff_pct >= _threshold()]
    await message.answer(format_list(signals))


@dp.message(Command(commands=["signal", "spread"]))
async def cmd_signal(message: Message, command: CommandObject) -> None:
    if not command.args:
        await cmd_top(message)
        return
    token = command.args.strip().upper().split("/")[0]
    await message.answer(f"Дивлюсь {html.quote(token)}… ⏳")
    signals = await scanner.scan([token])
    if not signals:
        await message.answer(
            f"Для <b>{html.quote(token)}</b> не знайшов пару DEX+{config.quote} разом із CEX."
        )
        return
    await message.answer(format_signal(signals[0]))


async def _broadcast(bot: Bot, text: str) -> None:
    targets = set(storage.get_subscribers())
    if config.default_chat_id:
        try:
            targets.add(int(config.default_chat_id))
        except ValueError:
            pass
    for chat_id in targets:
        try:
            await bot.send_message(chat_id, text, disable_web_page_preview=True)
        except Exception as exc:  # noqa: BLE001
            log.warning("Не зміг надіслати %s: %s", chat_id, exc)


async def alert_loop(bot: Bot) -> None:
    """Фонове сканування + розсилка сигналів за порогом (з анти-спамом)."""
    await asyncio.sleep(5)
    while True:
        try:
            threshold = _threshold()
            signals = await scanner.scan()
            now = asyncio.get_event_loop().time()
            fresh = []
            for s in signals:
                if s.diff_pct < threshold:
                    continue
                last = _last_alert.get(s.token, 0)
                if now - last < config.alert_cooldown:
                    continue
                _last_alert[s.token] = now
                storage.record_signal(s.token)
                scanner.open_signal(s)
                fresh.append(s)
            if fresh:
                log.info("Сигнали: %d токенів понад %.2f%%", len(fresh), threshold)
                for s in fresh[:15]:
                    await _broadcast(bot, format_signal(s))
        except Exception as exc:  # noqa: BLE001
            log.exception("Помилка у циклі сканування: %s", exc)
        await asyncio.sleep(config.scan_interval)


async def main() -> None:
    config.validate()
    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    log.info("Біржі: %s", ", ".join(scanner.venues))
    task = asyncio.create_task(alert_loop(bot))
    try:
        await dp.start_polling(bot)
    finally:
        task.cancel()
        await scanner.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Зупинено.")
