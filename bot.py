import asyncio
import logging
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Вставьте сюда токен от @BotFather
BOT_TOKEN = "9017355018:AAGwa1Jy2-bo3J65wY_v_YS1VZfajTyGisE"

# Опционально: укажите Telegram ID членов семьи для защиты от посторонних.
# Узнать свой ID можно через бота @userinfobot. Если список пуст — доступ открыт всем.
ALLOWED_USERS = []  # Например: [123456789, 987654321]

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- РАБОТА С БАЗОЙ ДАННЫХ (SQLite) ---
def init_db():
    conn = sqlite3.connect("family_budget.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT,
            type TEXT,          -- 'expense' (расход) или 'income' (доход)
            amount REAL,
            category TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_transaction(user_name: str, t_type: str, amount: float, category: str):
    conn = sqlite3.connect("family_budget.db")
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO transactions (user_name, type, amount, category, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_name, t_type, amount, category.lower(), now)
    )
    conn.commit()
    conn.close()

def get_month_stats():
    conn = sqlite3.connect("family_budget.db")
    cursor = conn.cursor()
    current_month = datetime.now().strftime("%Y-%m")
    
    # Общие доходы и расходы за месяц
    cursor.execute("""
        SELECT type, SUM(amount) FROM transactions 
        WHERE created_at LIKE ? GROUP BY type
    """, (f"{current_month}%",))
    totals = dict(cursor.fetchall())
    
    # Расходы по категориям
    cursor.execute("""
        SELECT category, SUM(amount) FROM transactions 
        WHERE type = 'expense' AND created_at LIKE ? 
        GROUP BY category ORDER BY SUM(amount) DESC
    """, (f"{current_month}%",))
    categories = cursor.fetchall()
    
    # Вклад каждого члена семьи (траты)
    cursor.execute("""
        SELECT user_name, SUM(amount) FROM transactions 
        WHERE type = 'expense' AND created_at LIKE ? 
        GROUP BY user_name ORDER BY SUM(amount) DESC
    """, (f"{current_month}%",))
    users = cursor.fetchall()
    
    conn.close()
    return totals, categories, users

def delete_last_transaction():
    conn = sqlite3.connect("family_budget.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, amount, category, type FROM transactions ORDER BY id DESC LIMIT 1")
    last = cursor.fetchone()
    if last:
        cursor.execute("DELETE FROM transactions WHERE id = ?", (last[0],))
        conn.commit()
    conn.close()
    return last

# --- КЛАВИАТУРА ---
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Отчет за месяц"), KeyboardButton(text="↩️ Отменить последнюю")],
        [KeyboardButton(text="ℹ️ Инструкция")]
    ],
    resize_keyboard=True
)

# --- ПРОВЕРКА ДОСТУПА ---
def is_allowed(user_id: int) -> bool:
    if not ALLOWED_USERS:
        return True
    return user_id in ALLOWED_USERS

# --- ОБРАБОТЧИКИ КОМАНД ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if not is_allowed(message.from_user.id):
        return await message.answer("⛔ У вас нет доступа к этому семейному бюджету.")
    
    await message.answer(
        "👋 Привет! Я бот для учета семейного бюджета.\n\n"
        "Просто напишите мне сумму и категорию:\n"
        "• `500 продукты` — запишет расход\n"
        "• `+50000 зарплата` — запишет доход\n\n"
        "Все участники семьи видят общую статистику.",
        parse_mode="Markdown",
        reply_markup=main_kb
    )

@dp.message(F.text == "ℹ️ Инструкция")
async def cmd_help(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    await message.answer(
        "📌 **Как пользоваться:**\n\n"
        "1. **Записать расход:** отправьте число и название категории.\n"
        "Пример: `1250 супермаркет` или `300 такси`\n\n"
        "2. **Записать доход:** поставьте `+` перед суммой.\n"
        "Пример: `+85000 аванс` или `+5000 кэшбэк`\n\n"
        "3. **Групповой чат:** вы можете добавить меня в общий чат семьи, чтобы все видели траты друг друга в реальном времени.",
        parse_mode="Markdown"
    )

@dp.message(F.text == "📊 Отчет за месяц")
async def cmd_stats(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    
    totals, categories, users = get_month_stats()
    income = totals.get("income", 0)
    expense = totals.get("expense", 0)
    balance = income - expense

    text = f"📅 **Отчет за текущий месяц:**\n\n"
    text += f"💰 Доходы: **{income:,.0f} ₽**\n"
    text += f"💸 Расходы: **{expense:,.0f} ₽**\n"
    text += f"⚖️ Остаток: **{balance:,.0f} ₽**\n\n"

    if categories:
        text += "📂 **Расходы по категориям:**\n"
        for cat, amount in categories:
            text += f"• {cat.capitalize()}: {amount:,.0f} ₽\n"
        text += "\n"

    if users:
        text += "👨‍👩‍👧‍👦 **Кто сколько потратил:**\n"
        for user, amount in users:
            text += f"• {user}: {amount:,.0f} ₽\n"

    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "↩️ Отменить последнюю")
async def cmd_undo(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    
    deleted = delete_last_transaction()
    if deleted:
        _, amount, category, t_type = deleted
        sign = "+" if t_type == "income" else "-"
        await message.answer(f"🗑 Удалена запись: **{sign}{amount:,.0f} ₽ ({category})**", parse_mode="Markdown")
    else:
        await message.answer("База данных пуста, удалять нечего.")

# --- ОБРАБОТКА ВВОДА ТРАТ И ДОХОДОВ ---
@dp.message(F.text)
async def handle_transaction(message: types.Message):
    if not is_allowed(message.from_user.id):
        return

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return  # Игнорируем обычные сообщения в групповом чате

    raw_amount, category = parts[0], parts[1]
    
    # Определяем тип операции (доход или расход)
    if raw_amount.startswith("+"):
        t_type = "income"
        raw_amount = raw_amount[1:]
    else:
        t_type = "expense"

    # Поддержка дробных чисел через точку или запятую
    try:
        amount = float(raw_amount.replace(",", "."))
        if amount <= 0:
            raise ValueError
    except ValueError:
        return  # Если первое слово не число — игнорируем

    user_name = message.from_user.first_name or "Участник"
    add_transaction(user_name, t_type, amount, category)

    if t_type == "income":
        await message.answer(f"✅ Доход записан: **+{amount:,.0f} ₽** ({category})\n👤 Добавил(а): {user_name}", parse_mode="Markdown")
    else:
        await message.answer(f"💸 Расход записан: **-{amount:,.0f} ₽** ({category})\n👤 Добавил(а): {user_name}", parse_mode="Markdown")

# --- ЗАПУСК ---
async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
