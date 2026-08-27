"""@rozhodnikibot — облік особистих витрат у Telegram."""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import sys
import time

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from config import config
from db import Storage
from keyboards import categories_keyboard, category_keyboard, period_keyboard
from parser import normalize, parse
from reports import format_added, format_report, money, month_bounds, period_bounds

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("rozhodniki")

storage = Storage(config.db_path)
dp = Dispatcher()

KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="/day"), KeyboardButton(text="/week"), KeyboardButton(text="/month")],
        [KeyboardButton(text="/cats"), KeyboardButton(text="/undo"), KeyboardButton(text="/help")],
    ],
    resize_keyboard=True,
)

HELP = """💸 <b>Розхідники</b> — записую твої витрати.

<b>Як записати</b> (просто напиши повідомлення):
<code>250 їжа обід з друзями</code>
<code>їжа 250</code>
<code>120 кава</code> — категорія вгадається сама
<code>1.5к продукти</code> — «к» = тисяча
<code>+5000 зарплата</code> — це дохід

<b>Звіти</b>
/day — сьогодні
/yesterday — вчора
/week — поточний тиждень
/month — поточний місяць

<b>Категорії</b>
/cats — список категорій
/addcat кафе 🍰 — додати (емодзі не обов'язкове)
/delcat кафе — прибрати

<b>Ліміт і правки</b>
/limit 15000 — місячний бюджет (0 = вимкнути)
/undo — скасувати останній запис
/del 42 — видалити запис за номером
/export — вивантажити все у CSV"""


def emojis(chat_id: int) -> dict[str, str]:
    return storage.categories(chat_id)


def month_spent(chat_id: int) -> float:
    start, end = month_bounds(config.timezone)
    return sum(
        entry.amount
        for entry in storage.entries_between(chat_id, start, end)
        if entry.kind == "expense"
    )


def report_text(chat_id: int, period: str) -> str:
    storage.ensure_user(chat_id)
    start, end, label = period_bounds(period, config.timezone)
    entries = storage.entries_between(chat_id, start, end)
    limit = storage.get_limit(chat_id)
    spent = month_spent(chat_id) if period != "month" else None
    return format_report(entries, label, config.currency, emojis(chat_id), limit, spent)


def categories_text(chat_id: int) -> str:
    start, end = month_bounds(config.timezone)
    totals: dict[str, float] = {}
    for entry in storage.entries_between(chat_id, start, end):
        if entry.kind == "expense":
            totals[entry.category] = totals.get(entry.category, 0) + entry.amount

    lines = ["🗂 <b>Категорії</b> <i>(витрати за місяць)</i>", ""]
    for name, emoji in emojis(chat_id).items():
        spent = totals.get(name, 0)
        suffix = f" — {money(spent)} {config.currency}" if spent else " — 0"
        lines.append(f"{emoji} {name}{suffix}")
    lines.append("")
    lines.append("Тисни категорію, щоб побачити записи за місяць.")
    lines.append("Додати: <code>/addcat кафе 🍰</code>   Прибрати: <code>/delcat кафе</code>")
    return "\n".join(lines)


def category_details(chat_id: int, category: str) -> str:
    start, end = month_bounds(config.timezone)
    entries = [
        entry
        for entry in storage.entries_between(chat_id, start, end)
        if entry.category == category and entry.kind == "expense"
    ]
    emoji = emojis(chat_id).get(category, "📦")
    if not entries:
        return f"{emoji} <b>{category}</b>\n\nЗа цей місяць витрат немає."

    total = sum(entry.amount for entry in entries)
    lines = [f"{emoji} <b>{category}</b> — {money(total)} {config.currency} за місяць", ""]
    for entry in entries[-15:]:
        when = time.strftime("%d.%m", time.localtime(entry.ts))
        note = f" — {entry.note}" if entry.note else ""
        lines.append(f"<code>#{entry.id}</code> {when} · {money(entry.amount)}{note}")
    if len(entries) > 15:
        lines.append(f"\n<i>…показано останні 15 із {len(entries)}</i>")
    return "\n".join(lines)


def added_text(chat_id: int, entry_id: int) -> str:
    entry = storage.get_entry(chat_id, entry_id)
    if entry is None:
        return "Запис видалено."
    return format_added(
        entry.id,
        entry.amount,
        entry.kind,
        entry.category,
        entry.note,
        emojis(chat_id).get(entry.category, "💰" if entry.kind == "income" else "📦"),
        config.currency,
        month_spent(chat_id),
        storage.get_limit(chat_id),
    )


async def send_report(message: Message, period: str) -> None:
    await message.answer(
        report_text(message.chat.id, period),
        reply_markup=period_keyboard(period),
    )


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    storage.ensure_user(message.chat.id)
    await message.answer(
        "Привіт! Я рахую твої розхідники 💸\n\n"
        "Просто напиши <code>250 їжа обід</code> — і я запишу.\n"
        "Категорію можна не вказувати: <code>120 кава</code> сам віднесу до «їжа».\n\n"
        "Тисни /help, щоб побачити всі команди.",
        reply_markup=KEYBOARD,
    )


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP, reply_markup=KEYBOARD)


@dp.message(Command("day", "today"))
async def cmd_day(message: Message) -> None:
    await send_report(message, "day")


@dp.message(Command("yesterday"))
async def cmd_yesterday(message: Message) -> None:
    await send_report(message, "yesterday")


@dp.message(Command("week"))
async def cmd_week(message: Message) -> None:
    await send_report(message, "week")


@dp.message(Command("month", "stats"))
async def cmd_month(message: Message) -> None:
    await send_report(message, "month")


@dp.message(Command("cats", "categories"))
async def cmd_cats(message: Message) -> None:
    chat_id = message.chat.id
    storage.ensure_user(chat_id)
    await message.answer(
        categories_text(chat_id), reply_markup=categories_keyboard(emojis(chat_id))
    )


@dp.message(Command("addcat"))
async def cmd_addcat(message: Message, command: CommandObject) -> None:
    chat_id = message.chat.id
    storage.ensure_user(chat_id)
    args = (command.args or "").split()
    if not args:
        await message.answer("Вкажи назву: <code>/addcat кафе 🍰</code>")
        return

    emoji = "📦"
    if len(args) > 1 and not args[-1].isalnum():
        emoji = args[-1]
        args = args[:-1]

    name = normalize(" ".join(args))
    if not name:
        await message.answer("Вкажи назву: <code>/addcat кафе 🍰</code>")
        return

    storage.add_category(chat_id, name, emoji)
    await message.answer(f"✅ Категорія {emoji} <b>{name}</b> додана.")


@dp.message(Command("delcat"))
async def cmd_delcat(message: Message, command: CommandObject) -> None:
    chat_id = message.chat.id
    storage.ensure_user(chat_id)
    name = normalize(command.args or "")
    if not name:
        await message.answer("Вкажи назву: <code>/delcat кафе</code>")
        return
    if storage.remove_category(chat_id, name):
        await message.answer(
            f"🗑 Категорію <b>{name}</b> прибрано. Старі записи лишились у звітах."
        )
    else:
        await message.answer(f"Категорії <b>{name}</b> немає. Список: /cats")


@dp.message(Command("limit"))
async def cmd_limit(message: Message, command: CommandObject) -> None:
    chat_id = message.chat.id
    storage.ensure_user(chat_id)
    raw = (command.args or "").replace(",", ".").strip()
    if not raw:
        limit = storage.get_limit(chat_id)
        text = (
            f"Місячний ліміт: <b>{money(limit)} {config.currency}</b>"
            if limit > 0
            else "Ліміт не заданий."
        )
        await message.answer(f"{text}\nЗмінити: <code>/limit 15000</code>")
        return
    try:
        value = float(raw)
    except ValueError:
        await message.answer("Потрібне число: <code>/limit 15000</code>")
        return
    if value < 0:
        await message.answer("Ліміт не може бути відʼємним.")
        return

    storage.set_limit(chat_id, value)
    if value == 0:
        await message.answer("🔕 Ліміт вимкнено.")
    else:
        spent = month_spent(chat_id)
        await message.answer(
            f"🎯 Місячний ліміт: <b>{money(value)} {config.currency}</b>\n"
            f"Уже витрачено: {money(spent)} {config.currency}"
        )


@dp.message(Command("undo"))
async def cmd_undo(message: Message) -> None:
    chat_id = message.chat.id
    storage.ensure_user(chat_id)
    entry = storage.last_entry(chat_id)
    if not entry:
        await message.answer("Немає чого скасовувати.")
        return
    storage.delete_entry(chat_id, entry.id)
    await message.answer(
        f"↩️ Скасовано: {money(entry.amount)} {config.currency} · {entry.category}"
    )


@dp.message(Command("del", "delete"))
async def cmd_del(message: Message, command: CommandObject) -> None:
    chat_id = message.chat.id
    storage.ensure_user(chat_id)
    raw = (command.args or "").strip()
    if not raw.isdigit():
        await message.answer("Вкажи номер запису: <code>/del 42</code>")
        return
    if storage.delete_entry(chat_id, int(raw)):
        await message.answer(f"🗑 Запис #{raw} видалено.")
    else:
        await message.answer(f"Запису #{raw} не знайшов.")


@dp.message(Command("export"))
async def cmd_export(message: Message) -> None:
    chat_id = message.chat.id
    storage.ensure_user(chat_id)
    entries = storage.all_entries(chat_id)
    if not entries:
        await message.answer("Поки нічого експортувати.")
        return

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "дата", "тип", "сума", "категорія", "коментар"])
    for entry in entries:
        writer.writerow(
            [
                entry.id,
                time.strftime("%Y-%m-%d %H:%M", time.localtime(entry.ts)),
                "дохід" if entry.kind == "income" else "витрата",
                f"{entry.amount:.2f}",
                entry.category,
                entry.note,
            ]
        )
    await message.answer_document(
        BufferedInputFile(buffer.getvalue().encode("utf-8-sig"), filename="rozhodniki.csv"),
        caption=f"📄 {len(entries)} записів",
    )


@dp.message(F.text & ~F.text.startswith("/"))
async def on_text(message: Message) -> None:
    chat_id = message.chat.id
    storage.ensure_user(chat_id)
    categories = emojis(chat_id)
    parsed = parse(message.text, categories)
    if not parsed:
        await message.answer(
            "Не побачив суми 🤔\nСпробуй так: <code>250 їжа обід</code> або <code>120 кава</code>"
        )
        return

    entry_id = storage.add_entry(
        chat_id, parsed.amount, parsed.category, parsed.note, parsed.kind, int(time.time())
    )
    await message.answer(
        added_text(chat_id, entry_id),
        reply_markup=category_keyboard(entry_id, categories, parsed.category)
        if parsed.kind == "expense"
        else None,
    )


@dp.callback_query(F.data.startswith("rep:"))
async def on_period(query: CallbackQuery) -> None:
    period = query.data.split(":", 1)[1]
    chat_id = query.message.chat.id
    await query.message.edit_text(
        report_text(chat_id, period), reply_markup=period_keyboard(period)
    )
    await query.answer()


@dp.callback_query(F.data == "cats")
async def on_cats(query: CallbackQuery) -> None:
    chat_id = query.message.chat.id
    storage.ensure_user(chat_id)
    await query.message.edit_text(
        categories_text(chat_id), reply_markup=categories_keyboard(emojis(chat_id))
    )
    await query.answer()


@dp.callback_query(F.data.startswith("info:"))
async def on_category_info(query: CallbackQuery) -> None:
    category = query.data.split(":", 1)[1]
    chat_id = query.message.chat.id
    await query.message.edit_text(
        category_details(chat_id, category), reply_markup=categories_keyboard(emojis(chat_id))
    )
    await query.answer()


@dp.callback_query(F.data.startswith("cat:"))
async def on_set_category(query: CallbackQuery) -> None:
    _, raw_id, category = query.data.split(":", 2)
    chat_id = query.message.chat.id
    entry_id = int(raw_id)
    if not storage.update_entry_category(chat_id, entry_id, category):
        await query.answer("Запис уже видалено", show_alert=True)
        return
    await query.message.edit_text(
        added_text(chat_id, entry_id),
        reply_markup=category_keyboard(entry_id, emojis(chat_id), category),
    )
    await query.answer(f"Категорія: {category}")


@dp.callback_query(F.data.startswith("del:"))
async def on_delete(query: CallbackQuery) -> None:
    entry_id = int(query.data.split(":", 1)[1])
    chat_id = query.message.chat.id
    entry = storage.get_entry(chat_id, entry_id)
    if entry is None or not storage.delete_entry(chat_id, entry_id):
        await query.answer("Запис уже видалено", show_alert=True)
        return
    await query.message.edit_text(
        f"🗑 Видалено: {money(entry.amount)} {config.currency} · {entry.category}"
    )
    await query.answer("Видалено")


async def main() -> None:
    bot = Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    me = await bot.get_me()
    log.info("Запускаю @%s", me.username)
    await dp.start_polling(bot)


if __name__ == "__main__":
    # Windows-консоль інколи не вміє UTF-8 — не даємо їй впасти на кирилиці
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    try:
        config.validate()
    except RuntimeError as error:
        raise SystemExit(f"ПОМИЛКА: {error}")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Зупинено")
