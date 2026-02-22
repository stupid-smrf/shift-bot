import sqlite3
import os
import random
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from apscheduler.schedulers.asyncio import AsyncIOScheduler


# ================= НАСТРОЙКИ =================

TOKEN = os.getenv("TOKEN")

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

main_messages = {}

# ================= БАЗА =================

conn = sqlite3.connect("shifts.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    date TEXT,
    rate REAL,
    consum REAL,
    tips REAL,
    UNIQUE(user_id, date)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    first_name TEXT,
    username TEXT,
    registered_at TEXT
)
""")

conn.commit()

# ================= ВСПОМОГАТЕЛЬНЫЕ =================

def format_money(value):
    return f"{int(value):,}".replace(",", " ") + " ₽"

def register_user(user: types.User):
    cursor.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?)",
            (
                user.id,
                user.first_name,
                user.username,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        )
        conn.commit()

def motivational_quote():
    quotes = [
        "Дисциплина делает деньги",
        "Система > мотивация",
        "Каждая смена — шаг к свободе",
        "Контроль = рост",
        "Регулярность делает богатым",
        "Цифры — это сила",
        "PRO начинается с порядка"
    ]
    return random.choice(quotes)

def inline_main_menu():
    kb = InlineKeyboardMarkup(row_width=2)

    kb.add(
        InlineKeyboardButton("➕ Добавить", callback_data="add"),
        InlineKeyboardButton("📅 Сегодня", callback_data="today"),
    )

    kb.add(
        InlineKeyboardButton("✏ Редактировать", callback_data="edit"),
        InlineKeyboardButton("🗑 Удалить", callback_data="delete"),
    )

    kb.add(
        InlineKeyboardButton("📅 Месяц", callback_data="month"),
        InlineKeyboardButton("🔥 Лучший месяц", callback_data="best_month"),
    )

    return kb

def build_main_screen(user_id):
    today = datetime.now()
    today_str = today.strftime("%d.%m.%Y")
    today_db = today.strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT rate, consum, tips
        FROM shifts
        WHERE user_id=?
    """, (user_id,))

    rows = cursor.fetchall()

    shifts = len(rows)

    total_rate = sum(r[0] for r in rows) if rows else 0
    total_consum = sum(r[1] for r in rows) if rows else 0
    total_tips = sum(r[2] for r in rows) if rows else 0

    total = total_rate + total_consum + total_tips
    avg = total / shifts if shifts else 0

    cursor.execute(
        "SELECT 1 FROM shifts WHERE user_id=? AND date=?",
        (user_id, today_db)
    )
    today_exists = cursor.fetchone()

    status = "✅ Внесена" if today_exists else "❌ Не внесена"

    return (
        "💎 <b>Твой менеджер дохода</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"📅 <b>{today_str}</b>\n\n"
        f"📊 Смен: <b>{shifts}</b>\n\n"
        f"💰 Ставка: <b>{format_money(total_rate)}</b>\n"
        f"🍾 Консум: <b>{format_money(total_consum)}</b>\n"
        f"☕ Чай: <b>{format_money(total_tips)}</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💎 Итого: <b>{format_money(total)}</b>\n"
        f"📈 Средний: <b>{format_money(avg)}</b>\n\n"
        f"🗓 Сегодня: {status}\n\n"
        f"💬 <i>{motivational_quote()}</i>\n\n"
        "👇 Выбери действие:"
    )

async def update_main(user_id):
    if user_id not in main_messages:
        return

    # маленький визуальный эффект обновления
    await bot.edit_message_text(
        chat_id=user_id,
        message_id=main_messages[user_id],
        text="🔄 Обновление...",
    )

    await bot.edit_message_text(
        chat_id=user_id,
        message_id=main_messages[user_id],
        text=build_main_screen(user_id),
        parse_mode="HTML",
        reply_markup=inline_main_menu()
    )

# ================= FSM =================

class ShiftState(StatesGroup):
    waiting_for_shift = State()
    waiting_for_today = State()
    waiting_for_edit = State()
    confirm_delete = State()

# ================= START =================

@dp.message_handler(commands=["start"], state="*")
async def start(message: types.Message, state: FSMContext):
    await state.finish()
    
    register_user(message.from_user)

    # если панель уже существует — просто обновляем её
    if message.from_user.id in main_messages:
        await update_main(message.from_user.id)
        await message.delete()
        return

    # если панели нет — создаём новую
    sent = await message.answer(
        build_main_screen(message.from_user.id),
        parse_mode="HTML",
        reply_markup=inline_main_menu()
    )

    main_messages[message.from_user.id] = sent.message_id
    await message.delete()
# ================= ДОБАВИТЬ =================

@dp.callback_query_handler(lambda c: c.data == "add")
async def add_shift(callback: types.CallbackQuery):
    await callback.answer()
    await ShiftState.waiting_for_shift.set()

    await callback.message.edit_text(
        "📅 <b>Добавление смены</b>\n\n"
        "Формат:\n"
        "ГГГГ-ММ-ДД СТАВКА КОНСУМ ЧАЙ\n\n"
        "Пример:\n"
        "2026-02-01 3500 2000 2500",
        parse_mode="HTML"
    )

@dp.message_handler(state=ShiftState.waiting_for_shift)
async def process_shift(message: types.Message, state: FSMContext):
    try:
        date, rate, consum, tips = message.text.split()
        datetime.strptime(date, "%Y-%m-%d")

        try:
            cursor.execute(
                "INSERT INTO shifts VALUES (NULL, ?, ?, ?, ?, ?)",
                (message.from_user.id, date, float(rate), float(consum), float(tips))
            )
            conn.commit()
            await state.finish()
            await message.delete()
            await update_main(message.from_user.id)

        except sqlite3.IntegrityError:
            await state.update_data(
                duplicate_date=date,
                duplicate_rate=rate,
                duplicate_consum=consum,
                duplicate_tips=tips
            )
            kb = InlineKeyboardMarkup()
            kb.add(
            InlineKeyboardButton("✅ Заменить", callback_data="confirm_replace"),
            InlineKeyboardButton("❌ Отмена", callback_data="cancel_replace")
)

            await message.answer(
            f"⚠️ Смена за {date} уже существует.\n"
            "Заменить её новыми данными?",
            reply_markup=kb
)

    except:
        await message.answer("❌ Формат: ГГГГ-ММ-ДД СТАВКА КОНСУМ ЧАЙ")

@dp.message_handler(lambda m: m.text.lower() == "заменить", state=ShiftState.waiting_for_shift)
async def replace_shift(message: types.Message, state: FSMContext):
    data = await state.get_data()

    cursor.execute(
        "UPDATE shifts SET rate=?, consum=?, tips=? WHERE user_id=? AND date=?",
        (
            float(data["duplicate_rate"]),
            float(data["duplicate_consum"]),
            float(data["duplicate_tips"]),
            message.from_user.id,
            data["duplicate_date"]
        )
    )
    conn.commit()

    await state.finish()
    await update_main(message.from_user.id)

# ================= СЕГОДНЯ =================

@dp.callback_query_handler(lambda c: c.data == "today")
async def today_shift(callback: types.CallbackQuery):
    await callback.answer()
    await ShiftState.waiting_for_today.set()

    await callback.message.edit_text(
        "📅 <b>Сегодняшняя смена</b>\n\n"
        "Формат:\n"
        "СТАВКА КОНСУМ ЧАЙ\n\n"
        "Пример:\n"
        "3500 2000 2500",
        parse_mode="HTML"
    )

@dp.message_handler(state=ShiftState.waiting_for_today)
async def process_today(message: types.Message, state: FSMContext):
    try:
        rate, consum, tips = message.text.split()
        today = datetime.now().strftime("%Y-%m-%d")

        cursor.execute(
            "INSERT OR REPLACE INTO shifts VALUES (NULL, ?, ?, ?, ?, ?)",
            (message.from_user.id, today, float(rate), float(consum), float(tips))
        )
        conn.commit()

        await state.finish()
        await message.delete()
        await update_main(message.from_user.id)

    except:
        await message.answer("❌ Формат: СТАВКА КОНСУМ ЧАЙ")

# ================= РЕДАКТИРОВАНИЕ =================

@dp.callback_query_handler(lambda c: c.data == "edit")
async def edit_menu(callback: types.CallbackQuery):
    await callback.answer()

    cursor.execute("""
        SELECT id, date
        FROM shifts
        WHERE user_id=?
        ORDER BY date DESC
        LIMIT 10
    """, (callback.from_user.id,))

    rows = cursor.fetchall()

    if not rows:
        await callback.message.edit_text("Нет смен.", reply_markup=inline_main_menu())
        return

    kb = InlineKeyboardMarkup()
    for r in rows:
        kb.add(InlineKeyboardButton(f"✏ {r[1]}", callback_data=f"edit_{r[0]}"))
    kb.add(InlineKeyboardButton("⬅ Назад", callback_data="back"))

    await callback.message.edit_text("Выбери смену:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("edit_"))
async def edit_shift(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    shift_id = int(callback.data.split("_")[1])
    await state.update_data(edit_id=shift_id)
    await ShiftState.waiting_for_edit.set()

    await callback.message.answer("Введи: СТАВКА КОНСУМ ЧАЙ")

@dp.message_handler(state=ShiftState.waiting_for_edit)
async def process_edit(message: types.Message, state: FSMContext):
    try:
        rate, consum, tips = message.text.split()
        data = await state.get_data()

        cursor.execute("""
            UPDATE shifts
            SET rate=?, consum=?, tips=?
            WHERE id=? AND user_id=?
        """, (
            float(rate),
            float(consum),
            float(tips),
            data["edit_id"],
            message.from_user.id
        ))
        conn.commit()

        await state.finish()
        await message.delete()
        await update_main(message.from_user.id)

    except:
        await message.answer("❌ Формат: СТАВКА КОНСУМ ЧАЙ")

# ================= УДАЛЕНИЕ =================

@dp.callback_query_handler(lambda c: c.data == "delete")
async def delete_menu(callback: types.CallbackQuery):
    await callback.answer()

    cursor.execute("""
        SELECT id, date
        FROM shifts
        WHERE user_id=?
        ORDER BY date DESC
        LIMIT 10
    """, (callback.from_user.id,))

    rows = cursor.fetchall()

    if not rows:
        await callback.message.edit_text("Нет смен.", reply_markup=inline_main_menu())
        return

    kb = InlineKeyboardMarkup()
    for r in rows:
        kb.add(InlineKeyboardButton(f"🗑 {r[1]}", callback_data=f"del_{r[0]}"))
    kb.add(InlineKeyboardButton("⬅ Назад", callback_data="back"))

    await callback.message.edit_text("Выбери смену:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("del_"))
async def confirm_delete(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    shift_id = int(callback.data.split("_")[1])
    await state.update_data(delete_id=shift_id)
    await ShiftState.confirm_delete.set()

    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Да", callback_data="confirm_yes"),
        InlineKeyboardButton("❌ Нет", callback_data="confirm_no")
    )

    await callback.message.edit_text("Удалить смену?", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "confirm_yes", state=ShiftState.confirm_delete)
async def delete_yes(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("Удалено 🗑")

    data = await state.get_data()

    cursor.execute(
        "DELETE FROM shifts WHERE id=? AND user_id=?",
        (data["delete_id"], callback.from_user.id)
    )
    conn.commit()

    await state.finish()

    await callback.message.delete()
    await update_main(callback.from_user.id)

@dp.callback_query_handler(lambda c: c.data == "confirm_no", state=ShiftState.confirm_delete)
async def delete_no(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.finish()
    await update_main(callback.from_user.id)

@dp.callback_query_handler(lambda c: c.data == "back")
async def go_back(callback: types.CallbackQuery):
    await callback.answer()
    await update_main(callback.from_user.id)
@dp.callback_query_handler(lambda c: c.data == "confirm_replace", state=ShiftState.waiting_for_shift)
async def confirm_replace(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("Смена заменена ✅")

    data = await state.get_data()

    cursor.execute(
        "UPDATE shifts SET rate=?, consum=?, tips=? WHERE user_id=? AND date=?",
        (
            float(data["duplicate_rate"]),
            float(data["duplicate_consum"]),
            float(data["duplicate_tips"]),
            callback.from_user.id,
            data["duplicate_date"]
        )
    )
    conn.commit()

    await state.finish()

    # удаляем сообщение с кнопками
    await callback.message.delete()

    await update_main(callback.from_user.id)


@dp.callback_query_handler(lambda c: c.data == "cancel_replace", state=ShiftState.waiting_for_shift)
async def cancel_replace(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("Отмена ❌")
    await state.finish()

    await callback.message.delete()
    await update_main(callback.from_user.id)


@dp.callback_query_handler(lambda c: c.data == "cancel_replace", state=ShiftState.waiting_for_shift)
async def cancel_replace(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("Отмена ❌")
    await state.finish()
    await update_main(callback.from_user.id)

# ================= НАПОМИНАНИЕ =================

async def check_shifts():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    for user in users:
        user_id = user[0]

        cursor.execute(
            "SELECT 1 FROM shifts WHERE user_id=? AND date=?",
            (user_id, yesterday)
        )

        if not cursor.fetchone():
            await bot.send_message(
                user_id,
                f"🌙 Смена за {yesterday} не внесена.",
                reply_markup=inline_main_menu()
            )

# ================= ЗАПУСК =================

async def on_startup(dp):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_shifts, "cron", hour=7)
    scheduler.start()

if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup)
import sqlite3
import os
import random
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from apscheduler.schedulers.asyncio import AsyncIOScheduler


# ================= НАСТРОЙКИ =================

TOKEN = os.getenv("TOKEN")

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

main_messages = {}

# ================= БАЗА =================

conn = sqlite3.connect("shifts.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    date TEXT,
    rate REAL,
    consum REAL,
    tips REAL,
    UNIQUE(user_id, date)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    first_name TEXT,
    username TEXT,
    registered_at TEXT
)
""")

conn.commit()

# ================= ВСПОМОГАТЕЛЬНЫЕ =================

def format_money(value):
    return f"{int(value):,}".replace(",", " ") + " ₽"

def register_user(user: types.User):
    cursor.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?)",
            (
                user.id,
                user.first_name,
                user.username,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        )
        conn.commit()

def motivational_quote():
    quotes = [
        "Дисциплина делает деньги",
        "Система > мотивация",
        "Каждая смена — шаг к свободе",
        "Контроль = рост",
        "Регулярность делает богатым",
        "Цифры — это сила",
        "PRO начинается с порядка"
    ]
    return random.choice(quotes)

def inline_main_menu():
    kb = InlineKeyboardMarkup(row_width=2)

    kb.add(
        InlineKeyboardButton("➕ Добавить", callback_data="add"),
        InlineKeyboardButton("📅 Сегодня", callback_data="today"),
    )

    kb.add(
        InlineKeyboardButton("✏ Редактировать", callback_data="edit"),
        InlineKeyboardButton("🗑 Удалить", callback_data="delete"),
    )

    kb.add(
        InlineKeyboardButton("📅 Месяц", callback_data="month"),
        InlineKeyboardButton("🔥 Лучший месяц", callback_data="best_month"),
    )

    return kb

def build_main_screen(user_id):
    today = datetime.now()
    today_str = today.strftime("%d.%m.%Y")
    today_db = today.strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT rate, consum, tips
        FROM shifts
        WHERE user_id=?
    """, (user_id,))

    rows = cursor.fetchall()

    shifts = len(rows)

    total_rate = sum(r[0] for r in rows) if rows else 0
    total_consum = sum(r[1] for r in rows) if rows else 0
    total_tips = sum(r[2] for r in rows) if rows else 0

    total = total_rate + total_consum + total_tips
    avg = total / shifts if shifts else 0

    cursor.execute(
        "SELECT 1 FROM shifts WHERE user_id=? AND date=?",
        (user_id, today_db)
    )
    today_exists = cursor.fetchone()

    status = "✅ Внесена" if today_exists else "❌ Не внесена"

    return (
        "💎 <b>Твой менеджер дохода</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"📅 <b>{today_str}</b>\n\n"
        f"📊 Смен: <b>{shifts}</b>\n\n"
        f"💰 Ставка: <b>{format_money(total_rate)}</b>\n"
        f"🍾 Консум: <b>{format_money(total_consum)}</b>\n"
        f"☕ Чай: <b>{format_money(total_tips)}</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💎 Итого: <b>{format_money(total)}</b>\n"
        f"📈 Средний: <b>{format_money(avg)}</b>\n\n"
        f"🗓 Сегодня: {status}\n\n"
        f"💬 <i>{motivational_quote()}</i>\n\n"
        "👇 Выбери действие:"
    )

async def update_main(user_id):
    if user_id not in main_messages:
        return

    # маленький визуальный эффект обновления
    await bot.edit_message_text(
        chat_id=user_id,
        message_id=main_messages[user_id],
        text="🔄 Обновление...",
    )

    await bot.edit_message_text(
        chat_id=user_id,
        message_id=main_messages[user_id],
        text=build_main_screen(user_id),
        parse_mode="HTML",
        reply_markup=inline_main_menu()
    )

# ================= FSM =================

class ShiftState(StatesGroup):
    waiting_for_shift = State()
    waiting_for_today = State()
    waiting_for_edit = State()
    confirm_delete = State()

# ================= START =================

@dp.message_handler(commands=["start"], state="*")
async def start(message: types.Message, state: FSMContext):
    await state.finish()

    register_user(message.from_user)

    sent = await message.answer(
        build_main_screen(message.from_user.id),
        parse_mode="HTML",
        reply_markup=inline_main_menu()
    )

    main_messages[message.from_user.id] = sent.message_id

# ================= ДОБАВИТЬ =================

@dp.callback_query_handler(lambda c: c.data == "add")
async def add_shift(callback: types.CallbackQuery):
    await callback.answer()
    await ShiftState.waiting_for_shift.set()

    await callback.message.edit_text(
        "📅 <b>Добавление смены</b>\n\n"
        "Формат:\n"
        "ГГГГ-ММ-ДД СТАВКА КОНСУМ ЧАЙ\n\n"
        "Пример:\n"
        "2026-02-01 3500 2000 2500",
        parse_mode="HTML"
    )

@dp.message_handler(state=ShiftState.waiting_for_shift)
async def process_shift(message: types.Message, state: FSMContext):
    try:
        date, rate, consum, tips = message.text.split()
        datetime.strptime(date, "%Y-%m-%d")

        try:
            cursor.execute(
                "INSERT INTO shifts VALUES (NULL, ?, ?, ?, ?, ?)",
                (message.from_user.id, date, float(rate), float(consum), float(tips))
            )
            conn.commit()
            await state.finish()
            await message.delete()
            await update_main(message.from_user.id)

        except sqlite3.IntegrityError:
            await state.update_data(
                duplicate_date=date,
                duplicate_rate=rate,
                duplicate_consum=consum,
                duplicate_tips=tips
            )
            kb = InlineKeyboardMarkup()
            kb.add(
            InlineKeyboardButton("✅ Заменить", callback_data="confirm_replace"),
            InlineKeyboardButton("❌ Отмена", callback_data="cancel_replace")
)

            await message.answer(
            f"⚠️ Смена за {date} уже существует.\n"
            "Заменить её новыми данными?",
            reply_markup=kb
)

    except:
        await message.answer("❌ Формат: ГГГГ-ММ-ДД СТАВКА КОНСУМ ЧАЙ")

@dp.message_handler(lambda m: m.text.lower() == "заменить", state=ShiftState.waiting_for_shift)
async def replace_shift(message: types.Message, state: FSMContext):
    data = await state.get_data()

    cursor.execute(
        "UPDATE shifts SET rate=?, consum=?, tips=? WHERE user_id=? AND date=?",
        (
            float(data["duplicate_rate"]),
            float(data["duplicate_consum"]),
            float(data["duplicate_tips"]),
            message.from_user.id,
            data["duplicate_date"]
        )
    )
    conn.commit()

    await state.finish()
    await update_main(message.from_user.id)

# ================= СЕГОДНЯ =================

@dp.callback_query_handler(lambda c: c.data == "today")
async def today_shift(callback: types.CallbackQuery):
    await callback.answer()
    await ShiftState.waiting_for_today.set()

    await callback.message.edit_text(
        "📅 <b>Сегодняшняя смена</b>\n\n"
        "Формат:\n"
        "СТАВКА КОНСУМ ЧАЙ\n\n"
        "Пример:\n"
        "3500 2000 2500",
        parse_mode="HTML"
    )

@dp.message_handler(state=ShiftState.waiting_for_today)
async def process_today(message: types.Message, state: FSMContext):
    try:
        rate, consum, tips = message.text.split()
        today = datetime.now().strftime("%Y-%m-%d")

        cursor.execute(
            "INSERT OR REPLACE INTO shifts VALUES (NULL, ?, ?, ?, ?, ?)",
            (message.from_user.id, today, float(rate), float(consum), float(tips))
        )
        conn.commit()

        await state.finish()
        await message.delete()
        await update_main(message.from_user.id)

    except:
        await message.answer("❌ Формат: СТАВКА КОНСУМ ЧАЙ")

# ================= РЕДАКТИРОВАНИЕ =================

@dp.callback_query_handler(lambda c: c.data == "edit")
async def edit_menu(callback: types.CallbackQuery):
    await callback.answer()

    cursor.execute("""
        SELECT id, date
        FROM shifts
        WHERE user_id=?
        ORDER BY date DESC
        LIMIT 10
    """, (callback.from_user.id,))

    rows = cursor.fetchall()

    if not rows:
        await callback.message.edit_text("Нет смен.", reply_markup=inline_main_menu())
        return

    kb = InlineKeyboardMarkup()
    for r in rows:
        kb.add(InlineKeyboardButton(f"✏ {r[1]}", callback_data=f"edit_{r[0]}"))
    kb.add(InlineKeyboardButton("⬅ Назад", callback_data="back"))

    await callback.message.edit_text("Выбери смену:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("edit_"))
async def edit_shift(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    shift_id = int(callback.data.split("_")[1])
    await state.update_data(edit_id=shift_id)
    await ShiftState.waiting_for_edit.set()

    await callback.message.answer("Введи: СТАВКА КОНСУМ ЧАЙ")

@dp.message_handler(state=ShiftState.waiting_for_edit)
async def process_edit(message: types.Message, state: FSMContext):
    try:
        rate, consum, tips = message.text.split()
        data = await state.get_data()

        cursor.execute("""
            UPDATE shifts
            SET rate=?, consum=?, tips=?
            WHERE id=? AND user_id=?
        """, (
            float(rate),
            float(consum),
            float(tips),
            data["edit_id"],
            message.from_user.id
        ))
        conn.commit()

        await state.finish()
        await message.delete()
        await update_main(message.from_user.id)

    except:
        await message.answer("❌ Формат: СТАВКА КОНСУМ ЧАЙ")

# ================= УДАЛЕНИЕ =================

@dp.callback_query_handler(lambda c: c.data == "delete")
async def delete_menu(callback: types.CallbackQuery):
    await callback.answer()

    cursor.execute("""
        SELECT id, date
        FROM shifts
        WHERE user_id=?
        ORDER BY date DESC
        LIMIT 10
    """, (callback.from_user.id,))

    rows = cursor.fetchall()

    if not rows:
        await callback.message.edit_text("Нет смен.", reply_markup=inline_main_menu())
        return

    kb = InlineKeyboardMarkup()
    for r in rows:
        kb.add(InlineKeyboardButton(f"🗑 {r[1]}", callback_data=f"del_{r[0]}"))
    kb.add(InlineKeyboardButton("⬅ Назад", callback_data="back"))

    await callback.message.edit_text("Выбери смену:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("del_"))
async def confirm_delete(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    shift_id = int(callback.data.split("_")[1])
    await state.update_data(delete_id=shift_id)
    await ShiftState.confirm_delete.set()

    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Да", callback_data="confirm_yes"),
        InlineKeyboardButton("❌ Нет", callback_data="confirm_no")
    )

    await callback.message.edit_text("Удалить смену?", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "confirm_yes", state=ShiftState.confirm_delete)
async def delete_yes(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("Удалено 🗑")

    data = await state.get_data()

    cursor.execute(
        "DELETE FROM shifts WHERE id=? AND user_id=?",
        (data["delete_id"], callback.from_user.id)
    )
    conn.commit()

    await state.finish()

    await callback.message.delete()
    await update_main(callback.from_user.id)

@dp.callback_query_handler(lambda c: c.data == "confirm_no", state=ShiftState.confirm_delete)
async def delete_no(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.finish()
    await update_main(callback.from_user.id)

@dp.callback_query_handler(lambda c: c.data == "back")
async def go_back(callback: types.CallbackQuery):
    await callback.answer()
    await update_main(callback.from_user.id)
@dp.callback_query_handler(lambda c: c.data == "confirm_replace", state=ShiftState.waiting_for_shift)
async def confirm_replace(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("Смена заменена ✅")

    data = await state.get_data()

    cursor.execute(
        "UPDATE shifts SET rate=?, consum=?, tips=? WHERE user_id=? AND date=?",
        (
            float(data["duplicate_rate"]),
            float(data["duplicate_consum"]),
            float(data["duplicate_tips"]),
            callback.from_user.id,
            data["duplicate_date"]
        )
    )
    conn.commit()

    await state.finish()

    # удаляем сообщение с кнопками
    await callback.message.delete()

    await update_main(callback.from_user.id)


@dp.callback_query_handler(lambda c: c.data == "cancel_replace", state=ShiftState.waiting_for_shift)
async def cancel_replace(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("Отмена ❌")
    await state.finish()

    await callback.message.delete()
    await update_main(callback.from_user.id)


@dp.callback_query_handler(lambda c: c.data == "cancel_replace", state=ShiftState.waiting_for_shift)
async def cancel_replace(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("Отмена ❌")
    await state.finish()
    await update_main(callback.from_user.id)

# ================= НАПОМИНАНИЕ =================

async def check_shifts():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    for user in users:
        user_id = user[0]

        cursor.execute(
            "SELECT 1 FROM shifts WHERE user_id=? AND date=?",
            (user_id, yesterday)
        )

        if not cursor.fetchone():
            await bot.send_message(
                user_id,
                f"🌙 Смена за {yesterday} не внесена.",
                reply_markup=inline_main_menu()
            )

# ================= ЗАПУСК =================

async def on_startup(dp):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_shifts, "cron", hour=7)
    scheduler.start()

if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup)