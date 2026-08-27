"""Офлайн-перевірка бота: розбір повідомлень, категорії, база, звіти, команди.

Запуск: python selftest.py   (Telegram і токен не потрібні)
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import time

os.environ.setdefault("EXPENSES_BOT_TOKEN", "test")
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

import bot as bot_module  # noqa: E402
from aiogram.filters import CommandObject  # noqa: E402
from db import DEFAULT_CATEGORIES, KEYWORDS, Storage  # noqa: E402
from parser import parse  # noqa: E402
from reports import money, period_bounds  # noqa: E402

CHAT_ID = 777
failures: list[str] = []
checks = 0


def check(condition: bool, label: str) -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(label)
        print(f"  ❌ {label}")


class FakeChat:
    id = CHAT_ID


class FakeMessage:
    """Мінімальний замінник aiogram.types.Message для офлайн-перевірки."""

    def __init__(self, text: str = "") -> None:
        self.text = text
        self.chat = FakeChat()
        self.replies: list[str] = []
        self.markup = None
        self.documents: list[tuple[str, bytes]] = []

    async def answer(self, text: str, **kwargs) -> None:
        self.replies.append(text)

    async def edit_text(self, text: str, **kwargs) -> None:
        self.replies.append(text)
        self.markup = kwargs.get("reply_markup")

    async def answer_document(self, document, caption: str = "", **kwargs) -> None:
        self.documents.append((document.filename, document.data))
        self.replies.append(caption)

    @property
    def last(self) -> str:
        return self.replies[-1] if self.replies else ""


async def run_command(handler, text: str = "", command: str = "", args: str | None = None):
    message = FakeMessage(text)
    if args is None and not command:
        await handler(message)
    else:
        await handler(message, CommandObject(prefix="/", command=command, args=args))
    return message


async def main() -> None:
    storage: Storage = bot_module.storage
    storage.ensure_user(CHAT_ID)
    categories = storage.categories(CHAT_ID)

    print("\n1. Кожна категорія записується явно")
    for name, _emoji in DEFAULT_CATEGORIES:
        parsed = parse(f"100 {name}", categories)
        check(parsed is not None and parsed.category == name, f"'100 {name}' → {name}")
        parsed = parse(f"{name} 100", categories)
        check(parsed is not None and parsed.category == name, f"'{name} 100' → {name}")
        parsed = parse(f"100 {name.upper()} нотатка", categories)
        check(
            parsed is not None and parsed.category == name and parsed.note == "нотатка",
            f"'100 {name.upper()} нотатка' → {name} + нотатка",
        )

    print("2. Автовизначення категорії за ключовим словом")
    for category, words in KEYWORDS.items():
        for word in words:
            parsed = parse(f"100 {word}", categories)
            check(
                parsed is not None and parsed.category == category,
                f"'100 {word}' → {category} (отримано {parsed.category if parsed else None})",
            )

    print("3. Скорочення категорій і запасний варіант")
    check(parse("100 прод", categories).category == "продукти", "'прод' → продукти")
    check(parse("100 трансп", categories).category == "транспорт", "'трансп' → транспорт")
    check(parse("100 йогомамацетоне", categories).category == "інше", "невідоме слово → інше")
    check(parse("100 йогомамацетоне", categories).note == "йогомамацетоне", "слово лишається в нотатці")

    print("3b. Відмінки і фрази")
    inflected = [
        ("120 кави з собою", "їжа"),
        ("300 таксі до дому", "транспорт"),
        ("50 обіду", "їжа"),
        ("450 в аптеці ліки", "здоровя"),
        ("700 бензину на трасі", "транспорт"),
        ("250 футболку купив", "одяг"),
    ]
    for text, category in inflected:
        parsed = parse(text, categories)
        check(
            parsed is not None and parsed.category == category,
            f"'{text}' → {category} (отримано {parsed.category if parsed else None})",
        )

    tricky = [("100 водафон", "звязок"), ("100 газета", "інше"), ("100 форма", "одяг")]
    for text, _expected in tricky:
        parsed = parse(text, categories)
        check(parsed is not None, f"'{text}' розібрано")
    check(parse("100 водафон", categories).category == "звязок", "'водафон' не плутається з 'вода'")
    check(parse("100 газета", categories).category == "інше", "'газета' не плутається з 'газ'")

    print("4. Формати суми")
    cases = [
        ("250 їжа обід з друзями", 250, "expense", "їжа", "обід з друзями"),
        ("250,50 кава", 250.5, "expense", "їжа", "кава"),
        ("250.50 кава", 250.5, "expense", "їжа", "кава"),
        ("1.5к продукти", 1500, "expense", "продукти", ""),
        ("2k продукти", 2000, "expense", "продукти", ""),
        ("-300 таксі", 300, "expense", "транспорт", "таксі"),
        ("+5000 зарплата", 5000, "income", "дохід", "зарплата"),
        ("їжа 250", 250, "expense", "їжа", ""),
    ]
    for text, amount, kind, category, note in cases:
        parsed = parse(text, categories)
        check(parsed is not None, f"'{text}' розібрано")
        if parsed:
            check(abs(parsed.amount - amount) < 1e-9, f"'{text}' сума = {amount}")
            check(parsed.kind == kind, f"'{text}' тип = {kind}")
            check(parsed.category == category, f"'{text}' категорія = {category}")
            check(parsed.note == note, f"'{text}' нотатка = '{note}' (отримано '{parsed.note}')")

    for text in ("привіт", "", "їжа", "0 їжа", "просто текст без цифр"):
        check(parse(text, categories) is None, f"'{text}' → без запису")

    print("5. Команди")
    await run_command(bot_module.cmd_start)
    await run_command(bot_module.cmd_help)

    added = await run_command(bot_module.on_text, "250 їжа обід")
    check("Записав" in added.last and "250" in added.last, "запис через текст")
    await run_command(bot_module.on_text, "1200 житло оренда")
    await run_command(bot_module.on_text, "80 кава")
    await run_command(bot_module.on_text, "+9000 зарплата")

    bad = await run_command(bot_module.on_text, "привіт")
    check("Не побачив суми" in bad.last, "повідомлення без суми")

    day = await run_command(bot_module.cmd_day)
    check("їжа" in day.last and "житло" in day.last, "у /day є категорії")
    check("Разом витрат" in day.last, "у /day є підсумок")
    check("Доходи" in day.last and "Баланс" in day.last, "у /day є дохід і баланс")

    week = await run_command(bot_module.cmd_week)
    check("Разом витрат" in week.last, "/week працює")
    month = await run_command(bot_module.cmd_month)
    check("Разом витрат" in month.last, "/month працює")
    yesterday = await run_command(bot_module.cmd_yesterday)
    check("Записів немає" in yesterday.last, "/yesterday порожній")

    cats = await run_command(bot_module.cmd_cats)
    for name, _emoji in DEFAULT_CATEGORIES:
        check(name in cats.last, f"/cats показує «{name}»")

    print("6. Свої категорії")
    await run_command(bot_module.cmd_addcat, command="addcat", args="кафе 🍰")
    check("кафе" in storage.categories(CHAT_ID), "/addcat додав категорію")
    parsed = parse("199 кафе десерт", storage.categories(CHAT_ID))
    check(parsed.category == "кафе" and parsed.note == "десерт", "нова категорія працює в записі")
    await run_command(bot_module.on_text, "199 кафе десерт")

    await run_command(bot_module.cmd_addcat, command="addcat", args="Спорт")
    check("спорт" in storage.categories(CHAT_ID), "/addcat без емодзі")
    removed = await run_command(bot_module.cmd_delcat, command="delcat", args="спорт")
    check("спорт" not in storage.categories(CHAT_ID) and "прибрано" in removed.last, "/delcat")
    missing = await run_command(bot_module.cmd_delcat, command="delcat", args="нічого")
    check("немає" in missing.last, "/delcat неіснуючої категорії")

    print("7. Ліміт")
    await run_command(bot_module.cmd_limit, command="limit", args="15000")
    check(storage.get_limit(CHAT_ID) == 15000, "/limit встановлено")
    limited = await run_command(bot_module.cmd_month)
    check("Місячний ліміт" in limited.last, "ліміт видно у звіті")
    over = await run_command(bot_module.on_text, "20000 інше техніка")
    check("Ліміт перевищено" in over.last, "попередження про перевищення")
    await run_command(bot_module.cmd_undo)
    bad_limit = await run_command(bot_module.cmd_limit, command="limit", args="абв")
    check("Потрібне число" in bad_limit.last, "/limit з текстом")
    await run_command(bot_module.cmd_limit, command="limit", args="0")
    check(storage.get_limit(CHAT_ID) == 0, "/limit 0 вимикає")
    await run_command(bot_module.cmd_limit, command="limit", args="15000")

    print("8. Правки і експорт")
    entry = storage.last_entry(CHAT_ID)
    undone = await run_command(bot_module.cmd_undo)
    check("Скасовано" in undone.last, "/undo")
    check(storage.last_entry(CHAT_ID).id != entry.id, "/undo прибрав останній запис")

    target = storage.last_entry(CHAT_ID)
    deleted = await run_command(bot_module.cmd_del, command="del", args=str(target.id))
    check("видалено" in deleted.last, "/del існуючого запису")
    ghost = await run_command(bot_module.cmd_del, command="del", args="999999")
    check("не знайшов" in ghost.last, "/del неіснуючого запису")

    export = await run_command(bot_module.cmd_export)
    check(bool(export.documents), "/export віддав файл")
    content = export.documents[0][1].decode("utf-8-sig")
    check("категорія" in content.splitlines()[0], "у CSV є заголовок")
    check(len(content.strip().splitlines()) == len(storage.all_entries(CHAT_ID)) + 1, "у CSV усі записи")

    print("9. Дрібниці")
    check(money(1234.5) == "1 234,50", f"формат грошей (отримано {money(1234.5)})")
    check(money(250.0) == "250", f"ціле без копійок (отримано {money(250.0)})")
    start, end, label = period_bounds("month", "Europe/Kyiv")
    check(start < int(time.time()) < end, "межі місяця охоплюють зараз")
    check(bool(label), "назва періоду не порожня")

    fresh = FakeMessage()
    fresh.chat = type("C", (), {"id": 999})()
    await bot_module.cmd_day(fresh)
    check("Записів немає" in fresh.last, "новий користувач: порожній звіт")

    print("10. Inline-кнопки")

    class FakeQuery:
        def __init__(self, data: str, chat_id: int = CHAT_ID) -> None:
            self.data = data
            self.message = FakeMessage()
            self.message.chat = type("C", (), {"id": chat_id})()
            self.answers: list[str] = []

        async def answer(self, text: str = "", **kwargs) -> None:
            self.answers.append(text)

    def buttons(markup) -> list[str]:
        return [button.callback_data for row in markup.inline_keyboard for button in row]

    added = await run_command(bot_module.on_text, "340 продукти сільпо")
    entry_id = storage.last_entry(CHAT_ID).id

    for period in ("day", "week", "month"):
        query = FakeQuery(f"rep:{period}")
        await bot_module.on_period(query)
        check("📊" in query.message.last, f"кнопка періоду {period} малює звіт")
        check(query.answers == [""] or query.answers, f"кнопка періоду {period} відповідає")
        check(
            f"rep:{period}" in buttons(query.message.markup),
            f"після {period} кнопки лишаються",
        )

    query = FakeQuery("cats")
    await bot_module.on_cats(query)
    check("Категорії" in query.message.last, "кнопка «Категорії» працює")
    for name, _emoji in DEFAULT_CATEGORIES:
        check(f"info:{name}" in buttons(query.message.markup), f"є кнопка категорії «{name}»")

    for name, _emoji in DEFAULT_CATEGORIES:
        query = FakeQuery(f"info:{name}")
        await bot_module.on_category_info(query)
        check(name in query.message.last, f"кнопка «{name}» відкриває деталі")

    query = FakeQuery(f"cat:{entry_id}:транспорт")
    await bot_module.on_set_category(query)
    check(storage.get_entry(CHAT_ID, entry_id).category == "транспорт", "кнопка змінює категорію")
    check("транспорт" in query.message.last, "текст оновився після зміни категорії")
    check(
        any(item == f"cat:{entry_id}:їжа" for item in buttons(query.message.markup)),
        "кнопки категорій лишаються після зміни",
    )

    query = FakeQuery(f"del:{entry_id}")
    await bot_module.on_delete(query)
    check(storage.get_entry(CHAT_ID, entry_id) is None, "кнопка 🗑 видаляє запис")
    check("Видалено" in query.message.last, "повідомлення про видалення")

    query = FakeQuery(f"del:{entry_id}")
    await bot_module.on_delete(query)
    check("уже видалено" in query.answers[-1], "повторне натискання 🗑 не падає")

    query = FakeQuery(f"cat:{entry_id}:їжа")
    await bot_module.on_set_category(query)
    check("уже видалено" in query.answers[-1], "зміна категорії видаленого запису не падає")

    foreign = storage.last_entry(CHAT_ID)
    query = FakeQuery(f"del:{foreign.id}", chat_id=555)
    await bot_module.on_delete(query)
    check(storage.get_entry(CHAT_ID, foreign.id) is not None, "чужу кнопку не виконати")

    print("11. Ізоляція між користувачами")
    other = FakeMessage("500 їжа чужа вечеря")
    other.chat = type("C", (), {"id": 1234})()
    await bot_module.on_text(other)
    other_entry = storage.last_entry(1234)
    check(other_entry is not None, "інший чат має свій запис")
    check(storage.delete_entry(CHAT_ID, other_entry.id) is False, "чужий запис не видаляється")
    check(storage.get_limit(1234) == 0, "ліміт не тече між чатами")
    storage.add_category(1234, "кава", "☕")
    check("кава" not in storage.categories(CHAT_ID), "категорії не течуть між чатами")

    print(f"\n{'✅ Усі перевірки пройдено' if not failures else '❌ Є помилки'}: "
          f"{checks - len(failures)}/{checks}")
    for item in failures:
        print(f"   - {item}")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    asyncio.run(main())
