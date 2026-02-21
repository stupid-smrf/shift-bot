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

def motivational_quote():
    quotes = [
        "Дисциплина делает деньги",
        "Система > мотивация",
        "Каждая смена — шаг к свободе",
        "Контроль = рост",
        "Маленькие шаги → большие суммы",
        "Ты управляешь деньгами, а не наоборот",
        "Регулярность делает богатым",
        "Цифры — это сила",
        "PRO начинается с порядка",
        "Система решает всё"
    ]
    return random.choice(quotes)

def inline_main_menu():
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
        InlineKeyboardButton("🔥 Лучший месяц", callback_data="best_month"),
    )

    return kb

def build_main_screen(user_id):
    today = datetime.now()
    today_str = today.strftime("%d.%m.%Y")
    today_db = today.strftime("%Y-%m-%d")
    month_name = today.strftime("%B")

    cursor.execute("SELECT rate, consum, tips FROM shifts WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()

    shifts = len(rows)
    total = sum(r[0] + r[1] + r[2] for r in rows) if rows else 0
    avg = total / shifts if shifts else 0

    cursor.execute(
        "SELECT 1 FROM shifts WHERE user_id = ? AND date = ?",
        (user_id, today_db)
    )
    today_exists = cursor.fetchone()

    status = "✅ Внесена" if today_exists else "❌ Не внесена"

    return (
        "💎 <b>Твой менеджер дохода</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"📅 <b>{today_str}</b> | {month_name}\n\n"
        f"📊 Смен: <b>{shifts}</b>\n"
        f"💰 Доход: <b>{format_money(total)}</b>\n"
        f"📈 Средний: <b>{format_money(avg)}</b>\n\n"
        f"🗓 Сегодня: {status}\n\n"
        f"💬 <i>{motivational_quote()}</i>\n\n"
        "👇 Выбери действие:"
    )

async def update_main(user_id):
    if user_id not in main_messages:
        return

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

# ================= START =================

@dp.message_handler(commands=["start"], state="*")
async def start(message: types.Message, state: FSMContext):

    await state.finish()  # сброс FSM

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
        "Введи:\n"
        "ГГГГ-ММ-ДД СТАВКА КОНСУМ ЧАЙ\n\n"
        "Пример:\n"
        "2026-02-01 3000 2000 2500",
        parse_mode="HTML"
    )

@dp.message_handler(state=ShiftState.waiting_for_shift)
async def process_shift(message: types.Message, state: FSMContext):
    try:
        date, rate, consum, tips = message.text.split()
        datetime.strptime(date, "%Y-%m-%d")

        cursor.execute(
            "INSERT INTO shifts VALUES (NULL, ?, ?, ?, ?, ?)",
            (message.from_user.id, date, float(rate), float(consum), float(tips))
        )
        conn.commit()

        await state.finish()
        await update_main(message.from_user.id)

    except:
        await message.answer("❌ Формат: ГГГГ-ММ-ДД СТАВКА КОНСУМ ЧАЙ")

# ================= СЕГОДНЯ =================

@dp.callback_query_handler(lambda c: c.data == "today")
async def today_shift(callback: types.CallbackQuery):
    await callback.answer()
    await ShiftState.waiting_for_today.set()

    await callback.message.edit_text(
        "📅 <b>Сегодняшняя смена</b>\n\n"
        "Введи:\n"
        "СТАВКА КОНСУМ ЧАЙ\n\n"
        "Пример:\n"
        "3000 2000 2500",
        parse_mode="HTML"
    )

@dp.message_handler(state=ShiftState.waiting_for_today)
async def process_today(message: types.Message, state: FSMContext):
    try:
        rate, consum, tips = message.text.split()
        today = datetime.now().strftime("%Y-%m-%d")

        cursor.execute(
            "INSERT INTO shifts VALUES (NULL, ?, ?, ?, ?, ?)",
            (message.from_user.id, today, float(rate), float(consum), float(tips))
        )
        conn.commit()

        await state.finish()
        await update_main(message.from_user.id)

    except:
        await message.answer("❌ Формат: СТАВКА КОНСУМ ЧАЙ")

# ================= НАПОМИНАНИЕ =================

async def check_shifts():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    for user in users:
        user_id = user[0]

        cursor.execute(
            "SELECT 1 FROM shifts WHERE user_id = ? AND date = ?",
            (user_id, yesterday)
        )

        if not cursor.fetchone():
            await bot.send_message(
                user_id,
                f"🌙 Смена за {yesterday} не внесена.\nНе забудь добавить 👇",
                reply_markup=inline_main_menu()
            )

# ================= МЕСЯЧНЫЙ ОТЧЁТ =================

async def monthly_report():
    first_day = datetime.now().replace(day=1)
    last_month = first_day - timedelta(days=1)
    month = last_month.strftime("%Y-%m")

    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    for user in users:
        user_id = user[0]

        cursor.execute(
            "SELECT rate, consum, tips FROM shifts WHERE user_id = ? AND date LIKE ?",
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
            f"📈 Средний: {format_money(avg)}\n\n"
            "🔥 Отличная работа!"
        )

# ================= ЗАПУСК =================

async def on_startup(dp):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_shifts, "cron", hour=7, minute=30)
    scheduler.add_job(monthly_report, "cron", day=1, hour=9)
    scheduler.start()

if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup)