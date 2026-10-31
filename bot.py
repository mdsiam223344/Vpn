import os
import sqlite3
import logging
import secrets
from datetime import datetime, timezone

from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

# ============================================================
# PREMIUM VPN SHOP - Single file Telegram shop bot
# Python 3.10+ | python-telegram-bot 21.x | Polling
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}
DB_PATH = os.getenv("DB_PATH", "shop.db")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@your_support")
CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/your_channel")
PAYMENT_DETAILS = os.getenv(
    "PAYMENT_DETAILS",
    "bKash: YOUR_NUMBER\nNagad: YOUR_NUMBER\nRocket: YOUR_NUMBER"
)
CURRENCY = os.getenv("CURRENCY", "TK")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required")
if not ADMIN_IDS:
    raise RuntimeError("ADMIN_IDS is required. Example: 123456789")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("premium-vpn-shop")

# -------------------- DATABASE --------------------

def connect():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT DEFAULT '',
            balance REAL DEFAULT 0,
            referred_by INTEGER DEFAULT NULL,
            joined_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            duration TEXT NOT NULL,
            name TEXT NOT NULL,
            price REAL NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            UNIQUE(category, duration, name)
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            duration TEXT NOT NULL,
            price REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS topups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            method TEXT NOT NULL,
            txn_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS referrals (
            user_id INTEGER PRIMARY KEY,
            referrer_id INTEGER NOT NULL,
            rewarded INTEGER NOT NULL DEFAULT 0
        );
        """)
        # Seed screenshot example. Admin can add/change prices with /setprice.
        con.execute("""
            INSERT OR IGNORE INTO products(category,duration,name,price,active)
            VALUES
            ('VPN','3 Days','Express VPN',15,1),
            ('VPN','3 Days','Vyper VPN',15,1),
            ('VPN','3 Days','CyberGhost VPN',15,1),
            ('VPN','3 Days','Panda VPN',15,1)
        """)
        con.commit()

def now():
    return datetime.now(timezone.utc).isoformat()

def register_user(update: Update, referrer_id=None):
    user = update.effective_user
    if not user:
        return
    with connect() as con:
        con.execute(
            "INSERT OR IGNORE INTO users(user_id,username,joined_at) VALUES(?,?,?)",
            (user.id, user.username or "", now())
        )
        con.execute(
            "UPDATE users SET username=? WHERE user_id=?",
            (user.username or "", user.id)
        )
        if referrer_id and referrer_id != user.id:
            exists = con.execute(
                "SELECT 1 FROM referrals WHERE user_id=?", (user.id,)
            ).fetchone()
            if not exists:
                referrer = con.execute(
                    "SELECT 1 FROM users WHERE user_id=?", (referrer_id,)
                ).fetchone()
                if referrer:
                    con.execute(
                        "INSERT INTO referrals(user_id,referrer_id) VALUES(?,?)",
                        (user.id, referrer_id)
                    )
                    con.execute(
                        "UPDATE users SET referred_by=? WHERE user_id=?",
                        (referrer_id, user.id)
                    )
        con.commit()

def get_balance(user_id):
    with connect() as con:
        row = con.execute(
            "SELECT balance FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
    return float(row["balance"]) if row else 0.0

def is_admin(update):
    return bool(update.effective_user and update.effective_user.id in ADMIN_IDS)

# -------------------- KEYBOARDS --------------------

def main_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🛍 Proxy Shop"), KeyboardButton("🌐 VPN Shop")],
        [KeyboardButton("💎 Products"), KeyboardButton("💳 Top-up")],
        [KeyboardButton("👛 Balance"), KeyboardButton("🧙 Refer")],
        [KeyboardButton("📊 Status"), KeyboardButton("💬 Support")]
    ], resize_keyboard=True)

def back_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("⬅️ Back to Menu"), KeyboardButton("❌ Close")]
    ], resize_keyboard=True)

def validity_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🛡 3 Days Validity"), KeyboardButton("🛡 7 Days Validity")],
        [KeyboardButton("🛡 14 Days Validity"), KeyboardButton("🛡 30 Days Validity")],
        [KeyboardButton("❌ Close")]
    ], resize_keyboard=True)

def product_keyboard(rows):
    buttons = [[KeyboardButton(
        f"🛒 {r['name']} ({r['duration']}) — {r['price']:g} {CURRENCY}"
    )] for r in rows]
    buttons.append([KeyboardButton("⬅️ Back to Validity")])
    buttons.append([KeyboardButton("⬅️ Back to Menu")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# -------------------- START / GENERAL --------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    referrer = None
    if context.args and context.args[0].startswith("ref"):
        try:
            referrer = int(context.args[0][3:])
        except ValueError:
            pass
    register_user(update, referrer)
    name = update.effective_user.first_name or "Customer"
    await update.message.reply_text(
        "╔════════════════════════════╗\n"
        "      🔴 VIP PremiumVPNShop 🛍️\n"
        "╚════════════════════════════╝\n\n"
        f"👌 Welcome, {name}!\n\n"
        "💎 Premium products — Fast delivery\n"
        "🚀 Secure • Reliable • 24/7\n\n"
        "━━━━━━━━━━━━━━━━━━━━",
        reply_markup=main_keyboard()
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 SHOP HELP\n\n"
        "🌐 VPN Shop — Select validity and product.\n"
        "💎 Products — Browse digital products.\n"
        "💳 Top-up — Submit payment transaction ID.\n"
        "👛 Balance — Check wallet balance.\n"
        "🧙 Refer — Get your referral link.\n"
        "📊 Status — Check your recent orders.\n"
        "💬 Support — Contact support.",
        reply_markup=main_keyboard()
    )

async def show_products(update, context, category, duration=None):
    with connect() as con:
        if duration:
            rows = con.execute(
                "SELECT * FROM products WHERE category=? AND duration=? AND active=1 ORDER BY id",
                (category, duration)
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM products WHERE category=? AND active=1 ORDER BY duration,id",
                (category,)
            ).fetchall()

    if not rows:
        await update.message.reply_text(
            "এই ক্যাটাগরিতে এখন কোনো পণ্য যোগ করা হয়নি। পরে আবার চেষ্টা করুন অথবা Support-এ যোগাযোগ করুন।",
            reply_markup=back_keyboard()
        )
        return

    if duration:
        title = f"🛡 {duration.upper()} VPN\n━━━━━━━━━━━━━━━━━━━━\n"
    else:
        title = f"💎 {category} PRODUCTS\n━━━━━━━━━━━━━━━━━━━━\n"
    lines = [title]
    for r in rows:
        lines.append(f"💎 {r['name']} ({r['duration']}) — {r['price']:g} {CURRENCY}")
    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=product_keyboard(rows)
    )

# -------------------- SHOP ROUTER --------------------

async def shop_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    user_id = update.effective_user.id

    if text in ("⬅️ Back to Menu", "❌ Close"):
        context.user_data.clear()
        await update.message.reply_text(
            "🏠 Main Menu", reply_markup=main_keyboard()
        )
        return

    if text == "🌐 VPN Shop":
        context.user_data["shop_category"] = "VPN"
        await update.message.reply_text(
            "📂 Select Validity:", reply_markup=validity_keyboard()
        )
        return

    if text == "🛍 Proxy Shop":
        context.user_data["shop_category"] = "PROXY"
        await show_products(update, context, "PROXY")
        return

    if text == "💎 Products":
        await show_products(update, context, "PRODUCT")
        return

    if text in (
        "🛡 3 Days Validity", "🛡 7 Days Validity",
        "🛡 14 Days Validity", "🛡 30 Days Validity"
    ):
        duration = text.replace("🛡 ", "").replace(" Validity", "")
        context.user_data["selected_duration"] = duration
        await show_products(update, context, "VPN", duration)
        return

    if text == "⬅️ Back to Validity":
        await update.message.reply_text(
            "📂 Select Validity:", reply_markup=validity_keyboard()
        )
        return

    if text == "👛 Balance":
        balance = get_balance(user_id)
        await update.message.reply_text(
            f"👛 Your Wallet Balance: {balance:g} {CURRENCY}",
            reply_markup=main_keyboard()
        )
        return

    if text == "🧙 Refer":
        bot = await context.bot.get_me()
        link = f"https://t.me/{bot.username}?start=ref{user_id}"
        with connect() as con:
            count = con.execute(
                "SELECT COUNT(*) AS n FROM referrals WHERE referrer_id=?",
                (user_id,)
            ).fetchone()["n"]
        await update.message.reply_text(
            "🧙 REFER & EARN\n\n"
            f"👥 Total referrals: {count}\n"
            f"🔗 Your referral link:\n{link}\n\n"
            "Referral reward can be configured by the admin.",
            reply_markup=main_keyboard()
        )
        return

    if text == "📊 Status":
        with connect() as con:
            rows = con.execute(
                "SELECT id,product_name,duration,price,status,created_at "
                "FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 5",
                (user_id,)
            ).fetchall()
        if not rows:
            msg = "📊 You have no orders yet."
        else:
            msg = "📊 YOUR RECENT ORDERS\n\n"
            for r in rows:
                msg += (
                    f"Order #{r['id']} — {r['product_name']}\n"
                    f"{r['duration']} | {r['price']:g} {CURRENCY}\n"
                    f"Status: {r['status']}\n\n"
                )
        await update.message.reply_text(msg, reply_markup=main_keyboard())
        return

    if text == "💬 Support":
        await update.message.reply_text(
            f"💬 Support: {SUPPORT_USERNAME}",
            reply_markup=main_keyboard()
        )
        return

    if text == "💳 Top-up":
        context.user_data["awaiting"] = "topup_amount"
        await update.message.reply_text(
            "💳 TOP-UP WALLET\n\n"
            f"Payment details:\n{PAYMENT_DETAILS}\n\n"
            "কত টাকা Add Funds করতে চান? শুধু Amount লিখুন।",
            reply_markup=back_keyboard()
        )
        return

    # User selected a product button. Match against active catalogue.
    if text.startswith("🛒 "):
        label = text[3:]
        with connect() as con:
            rows = con.execute(
                "SELECT * FROM products WHERE active=1 ORDER BY id"
            ).fetchall()
        chosen = None
        for row in rows:
            expected = f"{row['name']} ({row['duration']}) — {row['price']:g} {CURRENCY}"
            if label == expected:
                chosen = row
                break
        if not chosen:
            await update.message.reply_text("পণ্যটি পাওয়া যায়নি। আবার Shop খুলুন।")
            return

        price = float(chosen["price"])
        balance = get_balance(user_id)
        if balance < price:
            await update.message.reply_text(
                f"❌ Insufficient balance.\n"
                f"Price: {price:g} {CURRENCY}\n"
                f"Your balance: {balance:g} {CURRENCY}\n\n"
                "প্রথমে Top-up করুন।",
                reply_markup=main_keyboard()
            )
            return

        with connect() as con:
            con.execute(
                "UPDATE users SET balance=balance-? WHERE user_id=?",
                (price, user_id)
            )
            cur = con.execute("""
                INSERT INTO orders(user_id,product_id,product_name,duration,price,status,created_at)
                VALUES(?,?,?,?,?,'PENDING',?)
            """, (
                user_id, chosen["id"], chosen["name"],
                chosen["duration"], price, now()
            ))
            order_id = cur.lastrowid
            con.commit()

        username = update.effective_user.username or "N/A"
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    "🛒 NEW ORDER\n\n"
                    f"Order ID: #{order_id}\n"
                    f"User ID: {user_id}\n"
                    f"Username: @{username}\n"
                    f"Product: {chosen['name']}\n"
                    f"Validity: {chosen['duration']}\n"
                    f"Price: {price:g} {CURRENCY}\n\n"
                    f"Complete: /complete_order {order_id}\n"
                    f"Refund: /refund_order {order_id}"
                )
            except Exception:
                log.exception("Could not notify admin %s", admin_id)

        await update.message.reply_text(
            f"✅ Order #{order_id} placed successfully!\n"
            "Admin will deliver your product shortly.",
            reply_markup=main_keyboard()
        )
        return

    # Pending top-up flow
    awaiting = context.user_data.get("awaiting")
    if awaiting == "topup_amount":
        try:
            amount = float(text)
            if amount <= 0 or amount > 1000000:
                raise ValueError
        except ValueError:
            await update.message.reply_text("সঠিক Amount লিখুন, যেমন: 100")
            return
        context.user_data["topup_amount"] = amount
        context.user_data["awaiting"] = "topup_method"
        await update.message.reply_text(
            "Payment Method লিখুন: bKash / Nagad / Rocket"
        )
        return

    if awaiting == "topup_method":
        method = text.strip()
        if method.lower() not in ("bkash", "bKash".lower(), "nagad", "rocket"):
            await update.message.reply_text("bKash, Nagad অথবা Rocket লিখুন।")
            return
        context.user_data["topup_method"] = method
        context.user_data["awaiting"] = "topup_txn"
        await update.message.reply_text(
            "আপনার Payment Transaction ID পাঠান:"
        )
        return

    if awaiting == "topup_txn":
        txn_id = text.strip()
        if len(txn_id) < 4 or len(txn_id) > 100:
            await update.message.reply_text("সঠিক Transaction ID পাঠান।")
            return
        amount = context.user_data["topup_amount"]
        method = context.user_data["topup_method"]
        try:
            with connect() as con:
                cur = con.execute(
                    "INSERT INTO topups(user_id,amount,method,txn_id,created_at) "
                    "VALUES(?,?,?,?,?)",
                    (user_id, amount, method, txn_id, now())
                )
                topup_id = cur.lastrowid
                con.commit()
        except sqlite3.IntegrityError:
            await update.message.reply_text(
                "এই Transaction ID আগে জমা দেওয়া হয়েছে।"
            )
            context.user_data.clear()
            return

        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    "💳 NEW TOP-UP REQUEST\n\n"
                    f"Top-up ID: #{topup_id}\n"
                    f"User ID: {user_id}\n"
                    f"Amount: {amount:g} {CURRENCY}\n"
                    f"Method: {method}\n"
                    f"Transaction ID: {txn_id}\n\n"
                    f"Approve: /approve_topup {topup_id}\n"
                    f"Reject: /reject_topup {topup_id}"
                )
            except Exception:
                log.exception("Could not notify admin about top-up")

        context.user_data.clear()
        await update.message.reply_text(
            f"✅ Top-up request #{topup_id} submitted. Admin verification pending.",
            reply_markup=main_keyboard()
        )
        return

    await update.message.reply_text(
        "নিচের Menu থেকে একটি Option নির্বাচন করুন।",
        reply_markup=main_keyboard()
    )

# -------------------- ADMIN COMMANDS --------------------

async def setprice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    # /setprice VPN|3 Days|Express VPN|15
    parts = " ".join(context.args).split("|")
    if len(parts) != 4:
        await update.message.reply_text(
            "Format: /setprice VPN|3 Days|Express VPN|15"
        )
        return
    category, duration, name, price_text = [p.strip() for p in parts]
    try:
        price = float(price_text)
        if price < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Price must be zero or higher.")
        return
    with connect() as con:
        con.execute("""
            INSERT INTO products(category,duration,name,price,active)
            VALUES(?,?,?,?,1)
            ON CONFLICT(category,duration,name)
            DO UPDATE SET price=excluded.price,active=1
        """, (category.upper(), duration, name, price))
        con.commit()
    await update.message.reply_text(
        f"✅ Price saved: {name} / {duration} = {price:g} {CURRENCY}"
    )

async def addproduct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    # /addproduct PROXY|30 Days|Proxy Name|100
    parts = " ".join(context.args).split("|")
    if len(parts) != 4:
        await update.message.reply_text(
            "Format: /addproduct PROXY|30 Days|Proxy Name|100"
        )
        return
    category, duration, name, price_text = [p.strip() for p in parts]
    try:
        price = float(price_text)
        if price < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Invalid price.")
        return
    with connect() as con:
        con.execute(
            "INSERT OR REPLACE INTO products(category,duration,name,price,active) VALUES(?,?,?,?,1)",
            (category.upper(), duration, name, price)
        )
        con.commit()
    await update.message.reply_text("✅ Product added/updated.")

async def approve_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Use: /approve_topup TOPUP_ID")
        return
    topup_id = int(context.args[0])
    with connect() as con:
        row = con.execute(
            "SELECT * FROM topups WHERE id=?", (topup_id,)
        ).fetchone()
        if not row or row["status"] != "PENDING":
            await update.message.reply_text("Top-up not found or already processed.")
            return
        con.execute(
            "UPDATE topups SET status='APPROVED' WHERE id=?", (topup_id,)
        )
        con.execute(
            "UPDATE users SET balance=balance+? WHERE user_id=?",
            (row["amount"], row["user_id"])
        )
        con.commit()
    await context.bot.send_message(
        row["user_id"],
        f"✅ Your top-up #{topup_id} was approved. "
        f"{row['amount']:g} {CURRENCY} added to your balance."
    )
    await update.message.reply_text("✅ Top-up approved.")

async def reject_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Use: /reject_topup TOPUP_ID")
        return
    topup_id = int(context.args[0])
    with connect() as con:
        row = con.execute(
            "SELECT * FROM topups WHERE id=?", (topup_id,)
        ).fetchone()
        if not row or row["status"] != "PENDING":
            await update.message.reply_text("Top-up not found or already processed.")
            return
        con.execute(
            "UPDATE topups SET status='REJECTED' WHERE id=?", (topup_id,)
        )
        con.commit()
    await context.bot.send_message(
        row["user_id"],
        f"❌ Your top-up #{topup_id} was rejected. Contact support if needed."
    )
    await update.message.reply_text("❌ Top-up rejected.")

async def complete_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Use: /complete_order ORDER_ID")
        return
    order_id = int(context.args[0])
    with connect() as con:
        row = con.execute(
            "SELECT * FROM orders WHERE id=?", (order_id,)
        ).fetchone()
        if not row or row["status"] != "PENDING":
            await update.message.reply_text("Order not found or already processed.")
            return
        con.execute(
            "UPDATE orders SET status='COMPLETED' WHERE id=?", (order_id,)
        )
        con.commit()
    await context.bot.send_message(
        row["user_id"],
        f"🎉 Your order #{order_id} ({row['product_name']}) is marked completed. "
        "Please contact support if you need delivery details."
    )
    await update.message.reply_text("✅ Order marked completed.")

async def refund_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Use: /refund_order ORDER_ID")
        return
    order_id = int(context.args[0])
    with connect() as con:
        row = con.execute(
            "SELECT * FROM orders WHERE id=?", (order_id,)
        ).fetchone()
        if not row or row["status"] != "PENDING":
            await update.message.reply_text("Order not found or already processed.")
            return
        con.execute(
            "UPDATE orders SET status='REFUNDED' WHERE id=?", (order_id,)
        )
        con.execute(
            "UPDATE users SET balance=balance+? WHERE user_id=?",
            (row["price"], row["user_id"])
        )
        con.commit()
    await context.bot.send_message(
        row["user_id"],
        f"↩️ Order #{order_id} cancelled. {row['price']:g} {CURRENCY} refunded."
    )
    await update.message.reply_text("✅ Order refunded.")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Admin only.")
        return
    await update.message.reply_text(
        "🛠 ADMIN COMMANDS\n\n"
        "/setprice CATEGORY|DURATION|NAME|PRICE\n"
        "/addproduct CATEGORY|DURATION|NAME|PRICE\n"
        "/approve_topup ID\n"
        "/reject_topup ID\n"
        "/complete_order ID\n"
        "/refund_order ID\n\n"
        "Example:\n"
        "/setprice VPN|7 Days|Express VPN|35"
    )

async def post_init(application: Application):
    # Long polling mode: remove any previous webhook.
    await application.bot.delete_webhook(drop_pending_updates=True)
    log.info("Premium VPN Shop bot is ready (polling).")

def main():
    init_db()
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("setprice", setprice))
    app.add_handler(CommandHandler("addproduct", addproduct))
    app.add_handler(CommandHandler("approve_topup", approve_topup))
    app.add_handler(CommandHandler("reject_topup", reject_topup))
    app.add_handler(CommandHandler("complete_order", complete_order))
    app.add_handler(CommandHandler("refund_order", refund_order))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, shop_router))

    log.info("Starting Premium VPN Shop...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
