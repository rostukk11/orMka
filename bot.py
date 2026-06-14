"""Telegram-бот для моніторингу спредів між біржами (CEX + DEX).

Команди:
  /start            — підписатися на авто-алерти
  /stop             — відписатися
  /spread [TOKEN]   — спред конкретного токена (або топ зараз)
  /top              — топ спредів зараз
  /threshold N      — змінити поріг алерта (%)
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
from formatting import format_alert, format_list, format_spread
from scanner import Scanner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("spread-bot")

dp = Dispatcher()
scanner = Scanner()

# Анти-спам: token -> час останнього алерта
_last_alert: dict[str, float] = {}


def _threshold() -> float:
    return float(storage.get_setting("min_spread", config.min_spread))


HELP = (
    "🤖 <b>Spread Scanner Bot</b>\n\n"
    "Слідкую за спредами одного токена між біржами (CEX + DEX) і шлю сигнал, "
    "коли різниця перевищує поріг.\n\n"
    "<b>Команди:</b>\n"
    "/start — підписатися на авто-алерти\n"
    "/stop — відписатися\n"
    "/top — топ спредів зараз\n"
    "/spread BTC — спред по конкретному токену\n"
    "/threshold 2 — поріг алерта = 2%\n"
    "/status — налаштування й список бірж\n"
    "/help — ця довідка\n\n"
    "У сигналі: де купити (min ask) і де продати (max bid), %, "
    "та чи можливий вивід з біржі купівлі (✅/⛔/❔) і ввід на біржу продажу."
)


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    is_new = storage.add_subscriber(message.chat.id)
    note = "Підписку оформлено ✅" if is_new else "Ти вже підписаний ✅"
    await message.answer(f"{note}\nПоріг алерта: <b>{_threshold():.2f}%</b>\n\n{HELP}")


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
        f"Поріг алерта: <b>{_threshold():.2f}%</b>\n"
        f"Інтервал сканування: {config.scan_interval} с\n"
        f"Котирувальна валюта: {config.quote}\n"
        f"Підписників: {len(storage.get_subscribers())}\n\n"
        f"<b>Біржі ({len(venues)}):</b> {html.quote(', '.join(venues))}\n"
        f"<b>Токенів у моніторингу:</b> {len(toks)}"
    )
    await message.answer(text)


@dp.message(Command("threshold"))
async def cmd_threshold(message: Message, command: CommandObject) -> None:
    if not command.args:
        await message.answer(f"Поточний поріг: <b>{_threshold():.2f}%</b>\nЗмінити: /threshold 2")
        return
    try:
        value = float(command.args.replace(",", ".").strip())
    except ValueError:
        await message.answer("Не зрозумів число. Приклад: /threshold 1.5")
        return
    if value <= 0:
        await message.answer("Поріг має бути більше 0.")
        return
    storage.set_setting("min_spread", value)
    await message.answer(f"Готово. Новий поріг алерта: <b>{value:.2f}%</b>")


@dp.message(Command("top"))
async def cmd_top(message: Message) -> None:
    await message.answer("Сканую біржі… ⏳")
    results = await scanner.scan()
    results = [r for r in results if r.spread_pct >= _threshold()]
    await message.answer(format_list(results))


@dp.message(Command("spread"))
async def cmd_spread(message: Message, command: CommandObject) -> None:
    if not command.args:
        await cmd_top(message)
        return
    token = command.args.strip().upper().split("/")[0]
    await message.answer(f"Дивлюсь {html.quote(token)}… ⏳")
    results = await scanner.scan([token])
    if not results:
        await message.answer(
            f"Для <b>{html.quote(token)}/{config.quote}</b> не знайшов ціни щонайменше на 2 біржах."
        )
        return
    await message.answer(format_spread(results[0]))


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
    """Фонове сканування + розсилка алертів за порогом (з анти-спамом)."""
    await asyncio.sleep(5)
    while True:
        try:
            threshold = _threshold()
            results = await scanner.scan()
            now = asyncio.get_event_loop().time()
            fresh: list = []
            for r in results:
                if r.spread_pct < threshold:
                    continue
                last = _last_alert.get(r.token, 0)
                if now - last < config.alert_cooldown:
                    continue
                _last_alert[r.token] = now
                fresh.append(r)
            if fresh:
                log.info("Алерт: %d токенів понад %.2f%%", len(fresh), threshold)
                await _broadcast(bot, format_alert(fresh[:15]))
        except Exception as exc:  # noqa: BLE001
            log.exception("Помилка у циклі сканування: %s", exc)
        await asyncio.sleep(config.scan_interval)


async def main() -> None:
    config.validate()
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
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
