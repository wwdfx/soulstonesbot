import logging
import psycopg2
import random
from psycopg2.extras import DictCursor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler, JobQueue
from datetime import datetime, timedelta
import asyncio

# Set up basic logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection details
DB_DETAILS = {
    "dbname": "koyebdb",
    "user": "koyeb-adm",
    "password": "WCAFr1R0muaZ",
    "host": "ep-shy-pine-a2e1ouuw.eu-central-1.pg.koyeb.app",
    "port": 5432
}

# Connect to PostgreSQL Database
def connect_db():
    conn = psycopg2.connect(**DB_DETAILS)
    conn.autocommit = True
    return conn

conn = connect_db()
cur = conn.cursor(cursor_factory=DictCursor)

# Function to handle reconnection
def reconnect_db(func):
    async def wrapper(*args, **kwargs):
        global conn, cur
        try:
            return await func(*args, **kwargs)
        except psycopg2.OperationalError:
            conn.close()
            conn = connect_db()
            cur = conn.cursor(cursor_factory=DictCursor)
            return await func(*args, **kwargs)
    return wrapper

# Create tables if they do not exist
cur.execute('''
    CREATE TABLE IF NOT EXISTS balances (
        user_id BIGINT PRIMARY KEY,
        balance INTEGER NOT NULL DEFAULT 0
    )
''')

cur.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        role TEXT NOT NULL DEFAULT 'user'
    )
''')

cur.execute('''
    CREATE TABLE IF NOT EXISTS last_reading (
        user_id BIGINT PRIMARY KEY,
        last_request TIMESTAMP
    )
''')

cur.execute('''
    CREATE TABLE IF NOT EXISTS checkin_streak (
        user_id BIGINT PRIMARY KEY,
        streak INTEGER NOT NULL DEFAULT 0,
        last_checkin TIMESTAMP
    )
''')

cur.execute('''
    CREATE TABLE IF NOT EXISTS last_game (
        user_id BIGINT PRIMARY KEY,
        last_play TIMESTAMP
    )
''')

cur.execute('''
    CREATE TABLE IF NOT EXISTS missions (
        id SERIAL PRIMARY KEY,
        name TEXT,
        rarity TEXT,
        appearing_rate INTEGER,
        length INTEGER,
        reward INTEGER
    )
''')

cur.execute('''
    CREATE TABLE IF NOT EXISTS user_missions (
        user_id BIGINT,
        mission_id INTEGER,
        start_time TIMESTAMP,
        end_time TIMESTAMP,
        completed BOOLEAN DEFAULT FALSE,
        PRIMARY KEY (user_id, mission_id, start_time)
    )
''')

cur.execute('''
    CREATE TABLE IF NOT EXISTS mission_attempts (
        user_id BIGINT,
        date DATE,
        attempts INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, date)
    )
''')

cur.execute('''
    CREATE TABLE IF NOT EXISTS user_symbols (
        user_id BIGINT PRIMARY KEY,
        symbols_count BIGINT DEFAULT 0
    )
''')

# Populate the missions table with 25 different missions
missions = [
    ('Патрулировать нижний Бруклин', 'Сложность: 1', 50, 2, 150),
    ('Охранять мага во время ритуала', 'Сложность: 2', 25, 3, 225),
    ('Зачистить нелегальное логово вампиров', 'Сложность: 3', 15, 4, 300),
    ('Уничтожить улей демонов-шерстней', 'Сложность: 4', 7, 6, 450),
    ('Уничтожить высшего демона', 'Сложность: 5', 3, 8, 600),
]

cur.executemany('INSERT INTO missions (name, rarity, appearing_rate, length, reward) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING', missions)
conn.commit()

# Function to retrieve balance
@reconnect_db
async def get_balance(user_id):
    cur.execute('SELECT balance FROM balances WHERE user_id = %s', (user_id,))
    result = cur.fetchone()
    return result['balance'] if result else 0

# Function to update balance
@reconnect_db
async def update_balance(user_id, amount):
    current_balance = await get_balance(user_id)
    new_balance = current_balance + amount
    cur.execute('INSERT INTO balances (user_id, balance) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET balance = %s', (user_id, new_balance, new_balance))
    conn.commit()
    return new_balance

# Function to reduce balance
@reconnect_db
async def reduce_balance(user_id, amount):
    current_balance = await get_balance(user_id)
    if current_balance < amount:
        return None  # Not enough balance
    new_balance = current_balance - amount
    cur.execute('INSERT INTO balances (user_id, balance) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET balance = %s', (user_id, new_balance, new_balance))
    conn.commit()
    return new_balance

# Function to set balance
@reconnect_db
async def set_balance(user_id, amount):
    cur.execute('INSERT INTO balances (user_id, balance) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET balance = %s', (user_id, amount, amount))
    conn.commit()
    return amount

# Function to get user role
@reconnect_db
async def get_user_role(user_id):
    cur.execute('SELECT role FROM users WHERE user_id = %s', (user_id,))
    result = cur.fetchone()
    return result['role'] if result else 'user'

# Function to set user role
@reconnect_db
async def set_user_role(user_id, role):
    cur.execute('INSERT INTO users (user_id, role) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET role = %s', (user_id, role, role))
    conn.commit()

# Function to get user symbols
@reconnect_db
async def get_user_symbols(user_id):
    cur.execute('SELECT symbols_count FROM user_symbols WHERE user_id = %s', (user_id,))
    result = cur.fetchone()
    return result['symbols_count'] if result else 0

# Function to get user rank
@reconnect_db
async def get_user_rank(user_id):
    symbols_count = await get_user_symbols(user_id)
    
    if symbols_count < 5000:
        return "Смертный"
    elif symbols_count < 20000:
        return "Новичок"
    elif symbols_count < 50000:
        return "Новоприбывший Охотник"
    elif symbols_count < 100000:
        return "Опытный охотник"
    elif symbols_count < 250000:
        return "Лидер миссий Института"
    elif symbols_count < 400000:
        return "Лидер Института"
    elif symbols_count < 250000:
        return "Кандидат в Инквизиторы"
    else:
        return "Лидер Института"

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

# Function to handle messages
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        message_text = update.message.text
        target_group_id = -1002142915618  # Adjust this ID to your target group

        logger.info(f"Received message in group {update.message.chat_id}: {message_text[:50]}")
        if len(message_text) >= 500 and update.message.chat_id == target_group_id:
            user_id = update.message.from_user.id
            user_mention = update.message.from_user.username or update.message.from_user.first_name
            mention_text = f"@{user_mention}" if update.message.from_user.username else user_mention

            # Update symbols count
            cur.execute('INSERT INTO user_symbols (user_id, symbols_count) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET symbols_count = user_symbols.symbols_count + %s', (user_id, len(message_text), len(message_text)))
            conn.commit()

            user_rank, soulstones = await get_user_rank(user_id)
            new_balance = await update_balance(user_id, soulstones)
            await update.message.reply_text(f"💎 {mention_text}, ваш пост зачтён. Вам начислено +{soulstones} к камням душ. Текущий баланс: {new_balance}💎.")

# Function to handle /profile command
async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_mention = update.message.from_user.username or update.message.from_user.first_name
    mention_text = f"@{user_mention}" if update.message.from_user.username else user_mention
    user_rank, _ = await get_user_rank(user_id)
    user_balance = await get_balance(user_id)
    
    total_symbols = await get_user_symbols(user_id)

    profile_text = (f"Профиль {mention_text}:\n"
                    f"Ранк: {user_rank}.\n"
                    f"Баланс Камней душ: {user_balance}.\n"
                    f"Символов в рп-чате: {total_symbols}.")

    buttons = [
        [InlineKeyboardButton("Баланс", callback_data="balance")],
        [InlineKeyboardButton("Предсказание от Магнуса", callback_data="reading")],
        [InlineKeyboardButton("Ежедневная награда", callback_data="checkin")],
        [InlineKeyboardButton("Камень-ножницы-бумага", callback_data="rockpaperscissors")],
        [InlineKeyboardButton("Миссии", callback_data="missions")]
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(profile_text, reply_markup=keyboard)

# Function to handle /balance command
async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_mention = query.from_user.username or query.from_user.first_name
    mention_text = f"@{user_mention}" if query.from_user.username else user_mention
    balance = await get_balance(user_id)
    await query.edit_message_text(f"💎 {mention_text}, ваш текущий баланс: {balance}💎.")

# Function to handle the /checkin command
@reconnect_db
async def checkin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    today = datetime.now()
    cur.execute('SELECT streak, last_checkin FROM checkin_streak WHERE user_id = %s', (user_id,))
    result = cur.fetchone()

    if result:
        streak, last_checkin = result['streak'], result['last_checkin']

        # Check if the user has already checked in today
        if today.date() == last_checkin.date():
            await query.edit_message_text("Вы уже получали награду за вход сегодня. Повторите попытку завтра.")
            return

        # Check if the streak is broken
        if today - last_checkin > timedelta(days=1):
            streak = 1
            reward = 25
            image_path = image_paths['loss']
            await query.message.reply_photo(photo=open(image_path, 'rb'), caption="К сожалению, вы прервали череду ежедневных входов и получили 25 Камней душ.")
        else:
            streak += 1
            if streak > 7:
                streak = 7  # Cap streak at 7
            reward = 25 * streak
            image_path = image_paths.get(streak, image_paths[7])  # Default to day 7 image if streak > 7
            await query.message.reply_photo(photo=open(image_path, 'rb'), caption=f"Вы выполнили ежедневный вход {streak} дней подряд и получили {reward} Камней душ!")
    else:
        streak = 1
        reward = 25
        image_path = image_paths[1]
        await query.message.reply_photo(photo=open(image_path, 'rb'), caption=f"Вы выполнили ежедневный вход 1 день подряд и получили 25 Камней душ!")

    # Update the last check-in date and streak
    cur.execute('INSERT INTO checkin_streak (user_id, streak, last_checkin) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET streak = %s, last_checkin = %s', (user_id, streak, today, streak, today))
    conn.commit()

    new_balance = await update_balance(user_id, reward)

    user_mention = query.from_user.username or query.from_user.first_name
    mention_text = f"@{user_mention}" if query.from_user.username else user_mention

    await query.edit_message_text(f"💎 {mention_text}, ваш текущий баланс: {new_balance}💎.")

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
@reconnect_db
async def reading_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    if not await can_request_reading(user_id):
        await update.callback_query.edit_message_text("Вы уже запросили гадание сегодня. Повторите попытку завтра.")
        return

    if await reduce_balance(user_id, 50) is None:
        await update.callback_query.edit_message_text("Недостаточно Камней Душ для запроса гадания.")
        return

    await update.callback_query.message.reply_text("Камни душ с лёгким треском осыпались на стол. Магнус вскинул на них свой взор, улыбнулся и положил руку на хрустальный шар...")
    await asyncio.sleep(2)

    reading = random.choice(readings)
    await update.callback_query.message.reply_photo(photo=open('./reading.png', 'rb'), caption=f"Ваше гадание на сегодня:\n\n{reading}")

# Function to check and update last reading request time
@reconnect_db
async def can_request_reading(user_id):
    cur.execute('SELECT last_request FROM last_reading WHERE user_id = %s', (user_id,))
    result = cur.fetchone()
    if result:
        last_request_time = result['last_request']
        if datetime.now() - last_request_time < timedelta(days=1):
            return False
    cur.execute('INSERT INTO last_reading (user_id, last_request) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET last_request = %s', (user_id, datetime.now(), datetime.now()))
    conn.commit()
    return True

# Function to handle the /rockpaperscissors command
@reconnect_db
async def rockpaperscissors_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    cur.execute('SELECT last_play FROM last_game WHERE user_id = %s', (user_id,))
    result = cur.fetchone()
    now = datetime.now()

    if result:
        last_play = result['last_play']
        if now - last_play < timedelta(minutes=10):
            await query.edit_message_text("Вы можете играть только раз в 10 минут. Попробуйте позже.")
            return

    buttons = [
        InlineKeyboardButton("25", callback_data="bet_25"),
        InlineKeyboardButton("50", callback_data="bet_50"),
        InlineKeyboardButton("100", callback_data="bet_100"),
        InlineKeyboardButton("200", callback_data="bet_200"),
        InlineKeyboardButton("500", callback_data="bet_500")
    ]
    keyboard = InlineKeyboardMarkup.from_column(buttons)
    await query.edit_message_text("Выберите количество Камней душ, которые вы хотите поставить:", reply_markup=keyboard)

@reconnect_db
async def bet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    bet = int(query.data.split('_')[1])
    balance = await get_balance(user_id)

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

@reconnect_db
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
        new_balance = await update_balance(user_id, bet)
        await query.edit_message_text(f"Поздравляем! Вы выиграли {bet} Камней душ. Ваш текущий баланс: {new_balance}💎.")
    elif result == "lose":
        new_balance = await update_balance(user_id, -bet)
        await query.edit_message_text(f"Вы проиграли {bet} Камней душ. Ваш текущий баланс: {new_balance}💎.")
    else:
        await query.edit_message_text(f"Ничья! Ваш баланс остался прежним: {await get_balance(user_id)}💎.")

    # Update the last play time
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cur.execute('INSERT INTO last_game (user_id, last_play) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET last_play = %s', (user_id, now, now))
    conn.commit()

# Function to handle /addbalance command (admin only)
@reconnect_db
async def add_balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if await get_user_role(user_id) != 'admin':
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

    new_balance = await update_balance(int(target_user_id), amount)
    await update.message.reply_text(f"Баланс пользователя {target_user_id} увеличен на {amount} Камней душ. Новый баланс: {new_balance}💎.")

# Function to handle /subbalance command (admin only)
@reconnect_db
async def sub_balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if await get_user_role(user_id) != 'admin':
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

    new_balance = await reduce_balance(int(target_user_id), amount)
    if new_balance is None:
        await update.message.reply_text("Недостаточно Камней душ для выполнения операции.")
        return

    await update.message.reply_text(f"Баланс пользователя {target_user_id} уменьшен на {amount} Камней душ. Новый баланс: {new_balance}💎.")

# Function to handle /setbalance command (admin only)
@reconnect_db
async def set_balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if await get_user_role(user_id) != 'admin':
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

    new_balance = await set_balance(int(target_user_id), amount)
    await update.message.reply_text(f"Баланс пользователя {target_user_id} установлен на {amount} Камней душ. Новый баланс: {new_balance}💎.")

# Conversation states
PROMOTE_USER_ID = range(1)

# Function to handle /promote command (super admin only)
@reconnect_db
async def promote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    super_admin_id = 6505061807  # Replace with your actual super admin ID
    user_id = update.message.from_user.id

    if user_id != super_admin_id:
        await update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return ConversationHandler.END

    await update.message.reply_text("Пожалуйста, введите user_id аккаунта, который вы хотите повысить до администратора.")
    return PROMOTE_USER_ID

# Function to receive the user ID to promote
@reconnect_db
async def receive_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target_user_id = int(update.message.text)
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректное число.")
        return PROMOTE_USER_ID

    await set_user_role(target_user_id, 'admin')
    await update.message.reply_text(f"Пользователь {target_user_id} повышен до администратора.")
    return ConversationHandler.END

# Function to cancel the conversation
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END

# Function to generate random missions
@reconnect_db
async def generate_missions():
    missions = []
    cur.execute('SELECT * FROM missions')
    mission_data = cur.fetchall()
    for mission in mission_data:
        if random.randint(1, 100) <= mission['appearing_rate']:
            missions.append(mission)
        if len(missions) >= 5:
            break
    return missions

# Function to handle the /missions command
@reconnect_db
async def missions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    today = datetime.now().date()

    # Check if user has already attempted 3 missions today
    cur.execute('SELECT attempts FROM mission_attempts WHERE user_id = %s AND date = %s', (user_id, today))
    result = cur.fetchone()
    attempts = result['attempts'] if result else 0

    if attempts >= 3:
        await update.callback_query.edit_message_text("✨ Вы уже отправили 3 отряда на миссии сегодня. ⌛️ Повторите попытку завтра. ")
        return

    # Generate 5 random missions based on appearance rates
    missions = await generate_missions()

    # Create buttons for each mission
    buttons = [
        InlineKeyboardButton(
            f"{mission['name']} ({mission['reward']} 💎 камней душ)",
            callback_data=f"mission_{mission['id']}"
        )
        for mission in missions
    ]
    keyboard = InlineKeyboardMarkup.from_column(buttons)
    await update.callback_query.edit_message_text("⚔️ Выберите миссию для отправки отряда:", reply_markup=keyboard)

# Callback function for mission buttons
@reconnect_db
async def mission_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    mission_id = int(query.data.split('_')[1])

    # Fetch mission details using mission_id
    cur.execute('SELECT * FROM missions WHERE id = %s', (mission_id,))
    mission = cur.fetchone()

    if not mission:
        await query.edit_message_text("Ошибка: миссия не найдена.")
        return

    # Check if user has already attempted 3 missions today
    today = datetime.now().date()
    cur.execute('SELECT attempts FROM mission_attempts WHERE user_id = %s AND date = %s', (user_id, today))
    result = cur.fetchone()
    attempts = result['attempts'] if result else 0

    if attempts >= 3:
        await query.edit_message_text("✨ Вы уже отправили 3 отряда на миссии сегодня. ⌛️ Повторите попытку завтра. ")
        return

    # Increment the number of attempts for today
    if result:
        cur.execute('UPDATE mission_attempts SET attempts = attempts + 1 WHERE user_id = %s AND date = %s', (user_id, today))
    else:
        cur.execute('INSERT INTO mission_attempts (user_id, date, attempts) VALUES (%s, %s, 1)', (user_id, today))
    conn.commit()

    # Calculate mission end time
    start_time = datetime.now()
    end_time = start_time + timedelta(hours=mission['length'])

    # Insert mission into user_missions table
    cur.execute('INSERT INTO user_missions (user_id, mission_id, start_time, end_time) VALUES (%s, %s, %s, %s)', (user_id, mission_id, start_time, end_time))
    conn.commit()

    await query.edit_message_text(f"💼 Вы отправили отряд на миссию: ✨{mission['name']}✨.  🌒 Время завершения: ⌛️ {end_time.strftime('%Y-%m-%d %H:%M:%S')} ⌛️.")

# Function to check for completed missions
@reconnect_db
async def check_missions(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    cur.execute('SELECT user_id, mission_id FROM user_missions WHERE completed = FALSE AND end_time <= %s', (now,))
    completed_missions = cur.fetchall()

    for mission in completed_missions:
        user_id, mission_id = mission['user_id'], mission['mission_id']
        cur.execute('SELECT reward FROM missions WHERE id = %s', (mission_id,))
        reward = cur.fetchone()['reward']
        await update_balance(user_id, reward)
        cur.execute('UPDATE user_missions SET completed = TRUE WHERE user_id = %s AND mission_id = %s', (user_id, mission_id))
        await context.bot.send_message(chat_id=user_id, text=f"✅ Ваша миссия завершена! ✅ Вы получили {reward} 💎 Камней душ.")
    conn.commit()

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
app.add_handler(CommandHandler("missions", missions_command))
app.add_handler(CommandHandler("profile", profile_command))
app.add_handler(conv_handler)
app.add_handler(CallbackQueryHandler(bet_callback, pattern='^bet_'))
app.add_handler(CallbackQueryHandler(play_callback, pattern='^play_'))
app.add_handler(CallbackQueryHandler(mission_callback, pattern='^mission_'))
app.add_handler(CallbackQueryHandler(balance_command, pattern='^balance$'))
app.add_handler(CallbackQueryHandler(reading_command, pattern='^reading$'))
app.add_handler(CallbackQueryHandler(checkin_command, pattern='^checkin$'))
app.add_handler(CallbackQueryHandler(rockpaperscissors_command, pattern='^rockpaperscissors$'))
app.add_handler(CallbackQueryHandler(missions_command, pattern='^missions$'))

job_queue = app.job_queue
job_queue.run_repeating(check_missions, interval=6000, first=6000)

app.run_polling()