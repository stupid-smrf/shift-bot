import sqlite3
import os
import random
import asyncio
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
user_locks = {}
user_modes = {}

# ================= РЕЖИМЫ =================

class Mode:
    MAIN = "main"
    ADD = "add"
    TODAY = "today"
    EDIT = "edit"

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
    
    return kb


def build_main_screen(user_id):
    today = datetime.now()
    today_str = today.strftime("%d.%m.%Y")
    today_db = today.strftime("%Y-%m-%d")

    cursor.execute("SELECT rate, consum, tips FROM shifts WHERE user_id=?", (user_id,))
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


async def update_main(user_id, animated=True):
    if user_id not in main_messages:
        return

    if animated:
        try:
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=main_messages[user_id],
                text="⏳ Обновление..."
            )
            await asyncio.sleep(0.2)
        except:
            pass

    try:
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=main_messages[user_id],
            text=build_main_screen(user_id),
            parse_mode="HTML",
            reply_markup=inline_main_menu()
        )
        user_modes[user_id] = Mode.MAIN
    except:
        pass


async def render_screen(user_id, text):
    if user_id not in main_messages:
        return

    await bot.edit_message_text(
        chat_id=user_id,
        message_id=main_messages[user_id],
        text=text,
        parse_mode="HTML"
    )


async def is_locked(user_id):
    if user_locks.get(user_id):
        return True
    user_locks[user_id] = True
    return False


def unlock(user_id):
    user_locks[user_id] = False


# ================= FSM =================

class ShiftState(StatesGroup):
    waiting_for_shift = State()
    waiting_for_today = State()
    waiting_for_edit = State()
    confirm_delete = State()


# ================= GLOBAL GUARD =================

@dp.message_handler(state="*", content_types=types.ContentTypes.TEXT)
async def global_guard(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    mode = user_modes.get(message.from_user.id)

    if not current_state and mode == Mode.MAIN:
        try:
            await message.delete()
        except:
            pass


# ================= START =================

@dp.message_handler(commands=["start"], state="*")
async def start(message: types.Message, state: FSMContext):
    await state.finish()

    register_user(message.from_user)

    
    if message.from_user.id in main_messages:
        await update_main(message.from_user.id, animated=False)
        await message.delete()
        return

    
    sent = await message.answer(
        build_main_screen(message.from_user.id),
        parse_mode="HTML",
        reply_markup=inline_main_menu()
    )

    main_messages[message.from_user.id] = sent.message_id
    user_modes[message.from_user.id] = Mode.MAIN
    await message.delete()


# ================= ADD =================

@dp.callback_query_handler(lambda c: c.data == "add")
async def add_shift(callback: types.CallbackQuery):

    if await is_locked(callback.from_user.id):
        await callback.answer("Подожди…")
        return

    await callback.answer()
    await ShiftState.waiting_for_shift.set()
    user_modes[callback.from_user.id] = Mode.ADD

    await render_screen(
        callback.from_user.id,
        "📅 <b>Добавление смены</b>\n\n"
        "Введите:\n"
        "<b>ГГГГ-ММ-ДД СТАВКА КОНСУМ ЧАЙ</b>"
    )

    unlock(callback.from_user.id)


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
            await message.delete()

            kb = InlineKeyboardMarkup()
            kb.add(
                InlineKeyboardButton("✅ Заменить", callback_data="confirm_replace"),
                InlineKeyboardButton("❌ Отмена", callback_data="cancel_replace")
            )

            msg = await bot.send_message(
                message.from_user.id,
                f"⚠️ Смена за {date} уже существует.\nЗаменить её?",
                reply_markup=kb
            )

            await state.update_data(
                duplicate_date=date,
                duplicate_rate=rate,
                duplicate_consum=consum,
                duplicate_tips=tips
            )


    except:
       
        await message.delete()


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


    await callback.message.delete()

    await update_main(callback.from_user.id)


@dp.callback_query_handler(lambda c: c.data == "cancel_replace", state=ShiftState.waiting_for_shift)
async def cancel_replace(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("Отмена ❌")
    await state.finish()

    await callback.message.delete()
    await update_main(callback.from_user.id)


# ================= TODAY =================

@dp.callback_query_handler(lambda c: c.data == "today")
async def today_shift(callback: types.CallbackQuery):

    if await is_locked(callback.from_user.id):
        await callback.answer("Подожди…")
        return

    await callback.answer()
    await ShiftState.waiting_for_today.set()
    user_modes[callback.from_user.id] = Mode.TODAY

    await render_screen(
        callback.from_user.id,
        "📅 <b>Сегодняшняя смена</b>\n\n"
        "Введите:\n"
        "<b>СТАВКА КОНСУМ ЧАЙ</b>"
    )

    unlock(callback.from_user.id)


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

        await message.delete()


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
    executor.start_polling(
        dp,
        on_startup=on_startup,
        skip_updates=True
    )
    import asyncio

async def reset_telegram():
    await bot.delete_webhook(drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(reset_telegram())

    executor.start_polling(
        dp,
        on_startup=on_startup,
        skip_updates=True
    )