import logging
import sqlite3
import random
from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler
from datetime import datetime, timedelta, timezone
import asyncio

# Set up basic logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Connect to SQLite Database
conn = sqlite3.connect('user_balances.db')
c = conn.cursor()

# Create tables if they do not exist
c.execute('''
    CREATE TABLE IF NOT EXISTS balances (
        user_id INTEGER PRIMARY KEY,
        balance INTEGER NOT NULL DEFAULT 0
    )
''')

c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        role TEXT NOT NULL DEFAULT 'user'
    )
''')

c.execute('''
    CREATE TABLE IF NOT EXISTS last_reading (
        user_id INTEGER PRIMARY KEY,
        last_request TIMESTAMP
    )
''')

c.execute('''
    CREATE TABLE IF NOT EXISTS checkin_streak (
        user_id INTEGER PRIMARY KEY,
        streak INTEGER NOT NULL DEFAULT 0,
        last_checkin TIMESTAMP
    )
''')

c.execute('''
    CREATE TABLE IF NOT EXISTS last_game (
        user_id INTEGER PRIMARY KEY,
        last_play TIMESTAMP
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

# Function to reduce balance
def reduce_balance(user_id, amount):
    current_balance = get_balance(user_id)
    if current_balance < amount:
        return None  # Not enough balance
    new_balance = current_balance - amount
    c.execute('REPLACE INTO balances (user_id, balance) VALUES (?, ?)', (user_id, new_balance))
    conn.commit()
    return new_balance

# Function to set balance
def set_balance(user_id, amount):
    c.execute('REPLACE INTO balances (user_id, balance) VALUES (?, ?)', (user_id, amount))
    conn.commit()
    return amount

# Function to get user role
def get_user_role(user_id):
    c.execute('SELECT role FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    return result[0] if result else 'user'

# Function to set user role
def set_user_role(user_id, role):
    c.execute('REPLACE INTO users (user_id, role) VALUES (?, ?)', (user_id, role))
    conn.commit()

# Function to handle messages
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text
    target_group_id = -1002142915618  # Adjust this ID to your target group

    logger.info(f"Received message in group {update.message.chat_id}: {message_text[:50]}")
    if len(message_text) >= 500 and update.message.chat_id == target_group_id:
        user_id = update.message.from_user.id
        user_mention = update.message.from_user.username or update.message.from_user.first_name
        mention_text = f"@{user_mention}" if update.message.from_user.username else user_mention

        new_balance = update_balance(user_id, 5)
        await update.message.reply_text(f"💎 {mention_text}, ваш пост зачтён. Вам начислено +5 к камням душ. Текущий баланс: {new_balance}💎.")

# Function to handle /balance command
async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_mention = update.message.from_user.username or update.message.from_user.first_name
    mention_text = f"@{user_mention}" if update.message.from_user.username else user_mention
    balance = get_balance(user_id)
    await update.message.reply_text(f"💎 {mention_text}, ваш текущий баланс: {balance}💎.")

# Image paths
image_paths = {
    1: './check1.png',
    2: './check2.png',
    3: './check3.png',
    4: './check4.png',
    5: './check5.png',
    6: './check6.png',
    7: './check7.png',
    'loss': './lossStreak.png'
}

# Function to handle the /check-in command
async def checkin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    today = datetime.now()
    c.execute('SELECT streak, last_checkin FROM checkin_streak WHERE user_id = ?', (user_id,))
    result = c.fetchone()

    if result:
        streak, last_checkin = result
        last_checkin_date = datetime.strptime(last_checkin, '%Y-%m-%d %H:%M:%S')

        # Check if the user has already checked in today
        if today.date() == last_checkin_date.date():
            await update.message.reply_text("Вы уже получали награду за вход сегодня. Повторите попытку завтра.")
            return

        # Check if the streak is broken
        if today - last_checkin_date > timedelta(days=1):
            streak = 1
            reward = 25
            image_path = image_paths['loss']
            await update.message.reply_photo(photo=open(image_path, 'rb'), caption="К сожалению, вы прервали череду ежедневных входов и получили 25 Камней душ.")
        else:
            streak += 1
            if streak > 7:
                streak = 7  # Cap streak at 7
            reward = 25 * streak
            image_path = image_paths.get(streak, image_paths[7])  # Default to day 7 image if streak > 7
            await update.message.reply_photo(photo=open(image_path, 'rb'), caption=f"Вы выполнили ежедневный вход {streak} дней подряд и получили {reward} Камней душ!")
    else:
        streak = 1
        reward = 25
        image_path = image_paths[1]
        await update.message.reply_photo(photo=open(image_path, 'rb'), caption=f"Вы выполнили ежедневный вход 1 день подряд и получили 25 Камней душ!")

    # Update the last check-in date and streak
    c.execute('REPLACE INTO checkin_streak (user_id, streak, last_checkin) VALUES (?, ?, ?)', (user_id, streak, today.strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()

    new_balance = update_balance(user_id, reward)

    user_mention = update.message.from_user.username or update.message.from_user.first_name
    mention_text = f"@{user_mention}" if update.message.from_user.username else user_mention

    await update.message.reply_text(f"💎 {mention_text}, ваш текущий баланс: {new_balance}💎.")

# Readings list
readings = [
    "Сегодня ангельская сила будет направлять тебя.",
    "Новая руна откроет тебе свою истинную цель.",
    "Остерегайся демонов, прячущихся в неожиданных местах.",
    "Союзник из Нижнего мира окажет важную помощь.",
    "Твой серфимский клинок будет сегодня сиять ярче в твоих руках.",
    "Институт хранит секрет, который изменит твой путь.",
    "Связь парабатай укрепит твою решимость.",
    "Сообщение из Идриса принесет важные новости.",
    "Мудрость Безмолвных братьев поможет в твоем приключении.",
    "Новое задание проверит твои способности Сумеречного охотника.",
    "Решение Конклава повлияет на твое будущее.",
    "Маг откроет тебе портал в значимое место.",
    "Твой стеле создаст руну огромной силы.",
    "Древняя книга заклинаний откроет забытое временем проклятие.",
    "Загадка фейри приведет тебя к скрытой истине.",
    "Твоя связь с ангельским миром станет сильнее.",
    "Лояльность вампира окажется неоценимой.",
    "Заклинание колдуна принесет ясность в запутанную ситуацию.",
    "Демонические миры необычайно активны; будь на чеку.",
    "Сон даст тебе представление о будущем.",
    "Скрытая руна откроет новую способность.",
    "Ищи ответы в Кодексе. Он знает что тебе подсказать",
    "Смертный удивит тебя своей храбростью.",
    "Потерянная семейная реликвия обретет новое значение.",
    "Теневой рынок содержит предмет, важный для твоего задания.",
    "Столкновение с мятежным Сумеречным охотником неизбежно.",
    "Церемония рун приблизит тебя к твоему истинному потенциалу.",
    "Посещение Зала Согласия очень необходимо.",
    "Неожиданный союз сформируется с обитателем Нижнего мира.",
    "Твой серфимский клинок поможет уничтожить скрытого демона.",
    "Запретное заклинание будет искушать тебя великой силой.",
    "Сообщение из Благого Двора прибудет с настоятельностью.",
    "Призрак прошлого Сумеречного охотника предложит мудрость.",
    "Зачарованный артефакт усилит твои способности.",
    "Твоя лояльность Конклаву будет испытана.",
    "Пророчество из Молчаливого Города выйдет на свет.",
    "Редкий демон потребует твоего немедленного внимания.",
    "Старый друг вернется с удивительными новостями.",
    "Видение от ангела Разиэля направит твой путь.",
    "Сила Смертной Чаши будет ощущаться особенно сильно сегодня.",
    "Путешествие в Город Костей раскроет скрытые знания.",
    "Звук рога Сумеречных охотников сигнализирует важное событие.",
    "Таинственная руна появится в твоих снах.",
    "Встреча с Двором Сумерек изменит твою судьбу.",
    "Тайна Инквизитора будет раскрыта.",
    "Скрытый вход в Институт приведет к новому открытию.",
    "Неожиданный подарок от мага удивит тебя.",
    "Тайное послание от фейри будет обнаружено.",
    "Орудие смерти раскроет свою истинную силу.",
    "Восстание Сумеречных охотников на горизонте.",
    "Мудрость Безмолвных братьев защитит тебя.",
    "Старый дневник Сумеречного охотника содержат ключ к разгадке.",
    "Ожерелье Ангела исполнит свою магию.",
    "Ожидай неожиданного гостя из Нижнего мира.",
    "Древнее проклятие будет снято.",
    "Посещение библиотеки Института обнаружит важную подсказку.",
    "Твоя связь с парабатай обеспечит силу и ясность."
]

# Function to handle the /reading command
async def reading_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not can_request_reading(user_id):
        await update.message.reply_text("Вы уже запросили гадание сегодня. Повторите попытку завтра.")
        return

    if reduce_balance(user_id, 50) is None:
        await update.message.reply_text("Недостаточно Камней Душ для запроса гадания.")
        return

    await update.message.reply_text("Камни душ с лёгким треском осыпались на стол. Магнус вскинул на них свой взор, улыбнулся и положил руку на хрустальный шар...")
    await asyncio.sleep(2)

    reading = random.choice(readings)
    await update.message.reply_photo(photo=open('./reading.png', 'rb'), caption=f"Ваше гадание на сегодня:\n\n{reading}")

# Function to check and update last reading request time
def can_request_reading(user_id):
    c.execute('SELECT last_request FROM last_reading WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    if result:
        last_request_time = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S')
        if datetime.now() - last_request_time < timedelta(days=1):
            return False
    c.execute('REPLACE INTO last_reading (user_id, last_request) VALUES (?, ?)', (user_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    return True

# Define a function to handle the /rockpaperscissors command
async def rockpaperscissors_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    c.execute('SELECT last_play FROM last_game WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    now = datetime.now()

    if result:
        last_play = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S')
        if now - last_play < timedelta(minutes=10):
            await update.message.reply_text("Вы можете играть только раз в 10 минут. Попробуйте позже.")
            return

    buttons = [
        InlineKeyboardButton("25", callback_data="bet_25"),
        InlineKeyboardButton("50", callback_data="bet_50"),
        InlineKeyboardButton("100", callback_data="bet_100"),
        InlineKeyboardButton("200", callback_data="bet_200"),
        InlineKeyboardButton("500", callback_data="bet_500")
    ]
    keyboard = InlineKeyboardMarkup.from_column(buttons)
    await update.message.reply_text("Выберите количество Камней душ, которые вы хотите поставить:", reply_markup=keyboard)

async def bet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    bet = int(query.data.split('_')[1])
    balance = get_balance(user_id)

    if balance < bet:
        await query.edit_message_text("У вас недостаточно Камней душ для этой ставки.")
        return

    buttons = [
        InlineKeyboardButton("🪨", callback_data=f"play_{bet}_rock"),
        InlineKeyboardButton("📄", callback_data=f"play_{bet}_paper"),
        InlineKeyboardButton("✂️", callback_data=f"play_{bet}_scissors")
    ]
    keyboard = InlineKeyboardMarkup.from_row(buttons)
    await query.edit_message_text("Выберите, что вы хотите выбросить:", reply_markup=keyboard)

async def play_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    bet, user_choice = query.data.split('_')[1:]
    bet = int(bet)
    choices = ['rock', 'paper', 'scissors']
    bot_choice = random.choice(choices)

    outcomes = {
        ('rock', 'scissors'): "win",
        ('rock', 'paper'): "lose",
        ('paper', 'rock'): "win",
        ('paper', 'scissors'): "lose",
        ('scissors', 'paper'): "win",
        ('scissors', 'rock'): "lose"
    }

    if user_choice == bot_choice:
        result = "draw"
    else:
        result = outcomes.get((user_choice, bot_choice))

    if result == "win":
        new_balance = update_balance(user_id, bet)
        await query.edit_message_text(f"Поздравляем! Вы выиграли {bet} Камней душ. Ваш текущий баланс: {new_balance}💎.")
    elif result == "lose":
        new_balance = update_balance(user_id, -bet)
        await query.edit_message_text(f"Вы проиграли {bet} Камней душ. Ваш текущий баланс: {new_balance}💎.")
    else:
        await query.edit_message_text(f"Ничья! Ваш баланс остался прежним: {get_balance(user_id)}💎.")

    # Update the last play time
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute('REPLACE INTO last_game (user_id, last_play) VALUES (?, ?)', (user_id, now))
    conn.commit()

# Function to handle /addbalance command (admin only)
async def add_balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if get_user_role(user_id) != 'admin':
        await update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Использование: /addbalance <user_id> <amount>")
        return

    target_user_id, amount = context.args
    try:
        amount = int(amount)
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректное число.")
        return

    new_balance = update_balance(int(target_user_id), amount)
    await update.message.reply_text(f"Баланс пользователя {target_user_id} увеличен на {amount} Камней душ. Новый баланс: {new_balance}💎.")

# Function to handle /subbalance command (admin only)
async def sub_balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if get_user_role(user_id) != 'admin':
        await update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Использование: /subbalance <user_id> <amount>")
        return

    target_user_id, amount = context.args
    try:
        amount = int(amount)
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректное число.")
        return

    new_balance = reduce_balance(int(target_user_id), amount)
    if new_balance is None:
        await update.message.reply_text("Недостаточно Камней душ для выполнения операции.")
        return

    await update.message.reply_text(f"Баланс пользователя {target_user_id} уменьшен на {amount} Камней душ. Новый баланс: {new_balance}💎.")

# Function to handle /setbalance command (admin only)
async def set_balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if get_user_role(user_id) != 'admin':
        await update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Использование: /setbalance <user_id> <amount>")
        return

    target_user_id, amount = context.args
    try:
        amount = int(amount)
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректное число.")
        return

    new_balance = set_balance(int(target_user_id), amount)
    await update.message.reply_text(f"Баланс пользователя {target_user_id} установлен на {amount} Камней душ. Новый баланс: {new_balance}💎.")

# Conversation states
PROMOTE_USER_ID = range(1)

# Function to handle /promote command (super admin only)
async def promote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    super_admin_id = 6505061807  # Replace with your actual super admin ID
    user_id = update.message.from_user.id

    if user_id != super_admin_id:
        await update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return ConversationHandler.END

    await update.message.reply_text("Пожалуйста, введите user_id аккаунта, который вы хотите повысить до администратора.")
    return PROMOTE_USER_ID

# Function to receive the user ID to promote
async def receive_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target_user_id = int(update.message.text)
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректное число.")
        return PROMOTE_USER_ID

    set_user_role(target_user_id, 'admin')
    await update.message.reply_text(f"Пользователь {target_user_id} повышен до администратора.")
    return ConversationHandler.END

# Function to cancel the conversation
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END

# Initialize the bot and add handlers
app = ApplicationBuilder().token("7175746196:AAHckVjmat7IBpqvzWfTxvUzvQR1_1FgLiw").build()

# Conversation handler for promoting a user to admin
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('promote', promote_command)],
    states={
        PROMOTE_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_user_id)],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
app.add_handler(CommandHandler("balance", balance_command))
app.add_handler(CommandHandler("checkin", checkin_command))
app.add_handler(CommandHandler("reading", reading_command))
app.add_handler(CommandHandler("rockpaperscissors", rockpaperscissors_command))
app.add_handler(CommandHandler("addbalance", add_balance_command))
app.add_handler(CommandHandler("subbalance", sub_balance_command))
app.add_handler(CommandHandler("setbalance", set_balance_command))
app.add_handler(conv_handler)
app.add_handler(CallbackQueryHandler(bet_callback, pattern='^bet_'))
app.add_handler(CallbackQueryHandler(play_callback, pattern='^play_'))

app.run_polling()
    