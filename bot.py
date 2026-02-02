import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
import aiosqlite

# ------------------ KONFIG ------------------
BOT_TOKEN = "8300507896:AAHNXdac48K66Qs8MYNZNypbfuRuQC35JLk"  # Token z BotFather
ADMIN_ID = 7941453829           # Twój ID z @userinfobot
DB = "shop.db"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ------------------ BAZA DANYCH ------------------
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            price INTEGER,
            stock INTEGER
        )""")
        await db.execute("""
        CREATE TABLE IF NOT EXISTS cart(
            user_id INTEGER,
            product_id INTEGER,
            qty INTEGER
        )""")
        await db.execute("""
        CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            product_list TEXT,
            total INTEGER,
            payment_method TEXT,
            status TEXT
        )""")
        await db.commit()

# ------------------ START ------------------
@dp.message(Command("start"))
async def start(msg: Message):
    await msg.answer(
        "👕 Witaj w sklepie!\n\n"
        "Wybierz opcję:\n"
        "🛍 Produkty\n"
        "🛒 Koszyk"
    )

# ------------------ POKAŻ PRODUKTY ------------------
@dp.message(F.text == "🛍 Produkty")
async def show_products(msg: Message):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT id,name,price,stock FROM products")
        products = await cur.fetchall()

    if not products:
        await msg.answer("Brak produktów w sklepie.")
        return

    text = ""
    for p in products:
        text += f"{p[0]}. {p[1]} – {p[2]} zł (dostępne: {p[3]})\n"

    await msg.answer(
        text + "\n✍️ Napisz numer produktu aby dodać do koszyka"
    )

# ------------------ DODAJ DO KOSZYKA ------------------
@dp.message(F.text.regexp(r"^\d+$"))
async def add_cart(msg: Message):
    pid = int(msg.text)
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT stock FROM products WHERE id=?", (pid,))
        product = await cur.fetchone()
        if not product:
            await msg.answer("❌ Nie ma takiego produktu")
            return
        if product[0] <= 0:
            await msg.answer("❌ Produkt wyprzedany")
            return
        await db.execute("INSERT INTO cart VALUES (?,?,1)", (msg.from_user.id, pid))
        await db.commit()
    await msg.answer("✅ Dodano do koszyka")

# ------------------ KOSZYK ------------------
@dp.message(F.text == "🛒 Koszyk")
async def cart(msg: Message):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("""
        SELECT p.name, p.price, c.qty
        FROM cart c JOIN products p ON c.product_id=p.id
        WHERE c.user_id=?
        """, (msg.from_user.id,))
        items = await cur.fetchall()

    if not items:
        await msg.answer("Koszyk pusty")
        return

    total = 0
    text = "🛒 Twój koszyk:\n"
    product_list = []
    for i in items:
        total += i[1] * i[2]
        product_list.append(f"{i[0]} x{i[2]}")
        text += f"{i[0]} x{i[2]} – {i[1]} zł\n"
    text += f"\n💰 Razem: {total} zł"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💳 BLIK", callback_data=f"pay_blik_{total}"),
            InlineKeyboardButton(text="🏦 Przelew", callback_data=f"pay_bank_{total}")
        ]
    ])
    await msg.answer(text, reply_markup=keyboard)

# ------------------ CALLBACK PŁATNOŚCI ------------------
@dp.callback_query(F.data.startswith("pay_"))
async def pay_callback(call):
    data = call.data.split("_")
    method = data[1]
    total = data[2]
    user_id = call.from_user.id
    if method == "blik":
        text = f"📱 Płatność BLIK\nNumer telefonu: 600123456\nKwota: {total} zł\nPo dokonaniu płatności kliknij 'Zapłacone'."
        payment_method = "BLIK"
    else:
        text = f"🏦 Przelew bankowy\nIBAN: PLxx xxxx xxxx xxxx\nKwota: {total} zł\nPo dokonaniu przelewu kliknij 'Zapłacone'."
        payment_method = "Przelew"

    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("""
        SELECT p.name, c.qty FROM cart c JOIN products p ON c.product_id=p.id
        WHERE c.user_id=?
        """, (user_id,))
        items = await cur.fetchall()
        product_list = ", ".join([f"{i[0]} x{i[1]}" for i in items])
        await db.execute("""
        INSERT INTO orders(user_id, product_list, total, payment_method, status)
        VALUES (?,?,?,?,?)
        """, (user_id, product_list, int(total), payment_method, "oczekuje"))
        await db.execute("DELETE FROM cart WHERE user_id=?", (user_id,))
        await db.commit()

    await call.message.answer(text)
    await bot.send_message(
        ADMIN_ID,
        f"🛒 NOWE ZAMÓWIENIE\nUżytkownik: @{call.from_user.username}\nID: {user_id}\nProdukty: {product_list}\nKwota: {total} zł\nMetoda płatności: {payment_method}\nStatus: oczekuje"
    )

# ------------------ ADMIN PANEL ------------------
@dp.message(Command("admin"))
async def admin(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Potwierdź płatność", callback_data="admin_paid")],
        [InlineKeyboardButton(text="📦 Wysłane", callback_data="admin_sent")],
        [InlineKeyboardButton(text="❌ Anuluj", callback_data="admin_cancel")]
    ])
    await msg.answer("🔐 PANEL ADMINA", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("admin_"))
async def admin_buttons(call):
    if call.from_user.id != ADMIN_ID:
        return
    action = call.data.split("_")[1]
    await call.message.answer(f"Akcja admina: {action}")

# ------------------ URUCHOMIENIE ------------------
async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
