import logging
import sqlite3
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

# Set up basic logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Connect to SQLite Database
conn = sqlite3.connect('user_balances.db')
c = conn.cursor()

# Create table if it does not exist
c.execute('''
    CREATE TABLE IF NOT EXISTS balances (
        user_id INTEGER PRIMARY KEY,
        balance INTEGER NOT NULL DEFAULT 0
    )
''')
conn.commit()

# Function to retrieve balance
def get_balance(user_id):
    c.execute('SELECT balance FROM balances WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    return result[0] if result else 0

# Function to update balance
def update_balance(user_id, amount):
    current_balance = get_balance(user_id)
    new_balance = current_balance + amount
    c.execute('REPLACE INTO balances (user_id, balance) VALUES (?, ?)', (user_id, new_balance))
    conn.commit()
    return new_balance

# Define a function to handle messages
async def message_handler(update: Update, context):
    message_text = update.message.text
    target_group_id = -1002142915618  # Adjust this ID to your target group

    logger.info(f"Received message in group {update.message.chat_id}: {message_text[:50]}")
    if len(message_text) >= 500 and update.message.chat_id == target_group_id:
        user_id = update.message.from_user.id
        user_mention = update.message.from_user.username or update.message.from_user.first_name
        mention_text = f"@{user_mention}" if update.message.from_user.username else user_mention

        new_balance = update_balance(user_id, 5)
        await update.message.reply_text(f"💎 {mention_text}, ваш пост зачтён. Вам начислено +5 к камням душ. Текущий баланс: {new_balance}💎.")

# Define a function to handle the /balance command
async def balance_command(update: Update, context):
    user_id = update.message.from_user.id
    user_mention = update.message.from_user.username or update.message.from_user.first_name
    mention_text = f"@{user_mention}" if update.message.from_user.username else user_mention
    balance = get_balance(user_id)
    await update.message.reply_text(f"💎 {mention_text}, ваш текущий баланс: {balance}💎.")

app = ApplicationBuilder().token("7175746196:AAHckVjmat7IBpqvzWfTxvUzvQR1_1FgLiw").build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
app.add_handler(CommandHandler("balance", balance_command))
app.run_polling()