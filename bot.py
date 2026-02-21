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
    tips REAL
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
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user.id,))
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

def quote():
    quotes = [
        "Система > мотивация",
        "Каждая смена — шаг к свободе",
        "Деньги любят учет",
        "Регулярность делает богатым",
        "Статистика не врёт",
        "Смена за сменой — строится свобода",
        "Контроль = рост"
    ]
    return random.choice(quotes)

def menu():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📊 Статистика", callback_data="stats"),
        InlineKeyboardButton("📋 Последние", callback_data="list"),
    )
    kb.add(
        InlineKeyboardButton("➕ Добавить", callback_data="add"),
        InlineKeyboardButton("📅 Сегодня", callback_data="today"),
    )
    kb.add(
        InlineKeyboardButton("📅 Месяц", callback_data="month"),
        InlineKeyboardButton("🔥 Лучший", callback_data="best"),
    )
    return kb

def build_main(user_id):
    today = datetime.now()
    today_db = today.strftime("%Y-%m-%d")

    cursor.execute("SELECT rate, consum, tips FROM shifts WHERE user_id=?", (user_id,))
    rows = cursor.fetchall()

    shifts = len(rows)
    total = sum(r[0] + r[1] + r[2] for r in rows) if rows else 0
    avg = total / shifts if shifts else 0

    cursor.execute(
        "SELECT 1 FROM shifts WHERE user_id=? AND date=?",
        (user_id, today_db)
    )
    status = "✅ Внесена" if cursor.fetchone() else "❌ Не внесена"

    return (
        "💎 <b>Твой менеджер дохода</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Смен: <b>{shifts}</b>\n"
        f"💰 Доход: <b>{format_money(total)}</b>\n"
        f"📈 Средний: <b>{format_money(avg)}</b>\n\n"
        f"🗓 Сегодня: {status}\n\n"
        f"💬 <i>{quote()}</i>\n\n"
        "👇 Выбери действие:"
    )

async def refresh(user_id):
    if user_id not in main_messages:
        return

    await bot.edit_message_text(
        chat_id=user_id,
        message_id=main_messages[user_id],
        text=build_main(user_id),
        parse_mode="HTML",
        reply_markup=menu()
    )

# ================= FSM =================

class ShiftState(StatesGroup):
    add_shift = State()
    today_shift = State()

@dp.message_handler(state="*")
async def guard(message: types.Message, state: FSMContext):
    if message.text.startswith("/"):
        await state.finish()

# ================= START =================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    register_user(message.from_user)

    sent = await message.answer(
        build_main(message.from_user.id),
        parse_mode="HTML",
        reply_markup=menu()
    )

    main_messages[message.from_user.id] = sent.message_id

# ================= ADD =================

@dp.callback_query_handler(lambda c: c.data == "add")
async def add(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.finish()
    await ShiftState.add_shift.set()

    await bot.edit_message_text(
        "📅 Введи:\nГГГГ-ММ-ДД СТАВКА КОНСУМ ЧАЙ\n\n"
        "Пример:\n2026-02-01 3000 2000 2500",
        callback.from_user.id,
        main_messages[callback.from_user.id]
    )

@dp.message_handler(state=ShiftState.add_shift)
async def process_add(message: types.Message, state: FSMContext):
    try:
        date, rate, consum, tips = message.text.split()
        datetime.strptime(date, "%Y-%m-%d")
        rate, consum, tips = float(rate), float(consum), float(tips)

        cursor.execute(
            "INSERT INTO shifts VALUES (NULL, ?, ?, ?, ?, ?)",
            (message.from_user.id, date, rate, consum, tips)
        )
        conn.commit()

        await state.finish()
        await refresh(message.from_user.id)

    except:
        await message.answer("❌ Ошибка формата")

# ================= TODAY =================

@dp.callback_query_handler(lambda c: c.data == "today")
async def today(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.finish()
    await ShiftState.today_shift.set()

    await bot.edit_message_text(
        "📅 Сегодняшняя смена\n\n"
        "СТАВКА КОНСУМ ЧАЙ\n\n"
        "Пример:\n3000 2000 2500",
        callback.from_user.id,
        main_messages[callback.from_user.id]
    )

@dp.message_handler(state=ShiftState.today_shift)
async def process_today(message: types.Message, state: FSMContext):
    try:
        rate, consum, tips = map(float, message.text.split())
        today = datetime.now().strftime("%Y-%m-%d")

        cursor.execute(
            "INSERT INTO shifts VALUES (NULL, ?, ?, ?, ?, ?)",
            (message.from_user.id, today, rate, consum, tips)
        )
        conn.commit()

        await state.finish()
        await refresh(message.from_user.id)

    except:
        await message.answer("❌ Ошибка формата")

# ================= НАПОМИНАНИЯ =================

async def check_shifts():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    cursor.execute("SELECT user_id FROM users")
    for (user_id,) in cursor.fetchall():

        cursor.execute(
            "SELECT 1 FROM shifts WHERE user_id=? AND date=?",
            (user_id, yesterday)
        )

        if not cursor.fetchone():
            await bot.send_message(
                user_id,
                f"🌙 Смена за {yesterday} не внесена",
                reply_markup=menu()
            )

async def monthly_report():
    first_day = datetime.now().replace(day=1)
    last_month = first_day - timedelta(days=1)
    month = last_month.strftime("%Y-%m")

    cursor.execute("SELECT user_id FROM users")
    for (user_id,) in cursor.fetchall():

        cursor.execute(
            "SELECT rate, consum, tips FROM shifts WHERE user_id=? AND date LIKE ?",
            (user_id, f"{month}%")
        )

        rows = cursor.fetchall()
        if not rows:
            continue

        shifts = len(rows)
        total = sum(r[0] + r[1] + r[2] for r in rows)
        avg = total / shifts

        await bot.send_message(
            user_id,
            f"📅 Отчёт за {month}\n\n"
            f"Смен: {shifts}\n"
            f"💰 Итого: {format_money(total)}\n"
            f"📈 Средний: {format_money(avg)}"
        )

# ================= ЗАПУСК =================

async def on_startup(dp):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_shifts, "cron", hour=7, minute=30)
    scheduler.add_job(monthly_report, "cron", day=1, hour=9)
    scheduler.start()

if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup)