import logging
import psycopg2
import random
from psycopg2.extras import DictCursor
from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler, JobQueue
from datetime import datetime, timedelta, timezone
import asyncio
import os

# Set up basic logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Connect to PostgreSQL Database
conn = psycopg2.connect(
    dbname="koyebdb",
    user="koyeb-adm",
    password="WCAFr1R0muaZ",
    host="ep-shy-pine-a2e1ouuw.eu-central-1.pg.koyeb.app",
    port=5432
)
conn.autocommit = True
cur = conn.cursor(cursor_factory=DictCursor)

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

# Populate the missions table with 25 different missions
missions = [
    ('Патрулировать нижний Бруклин', '★☆☆☆☆', 50, 2, 150),
    ('Охранять мага во время ритуала', '★★☆☆☆', 25, 3, 225),
    ('Зачистить нелегальное логово вампиров', '★★★☆☆', 15, 4, 300),
    ('Уничтожить улей демонов-шерстней', '★★★★☆', 7, 6, 450),
    ('Уничтожить высшего демона', '★★★★★', 3, 8, 600),
    ('Исследовать заброшенный замок', '★☆☆☆☆', 50, 2, 150),
    ('Спасение заложника', '★★☆☆☆', 25, 3, 225),
    ('Защитить мирный город', '★★★☆☆', 15, 4, 300),
    ('Сразиться с бандой разбойников', '★★★★☆', 7, 6, 450),
    ('Истребить чумных крыс', '★★★★★', 3, 8, 600),
    ('Поиск древнего артефакта', '★☆☆☆☆', 50, 2, 150),
    ('Наблюдение за ведьмами', '★★☆☆☆', 25, 3, 225),
    ('Разведка границ', '★★★☆☆', 15, 4, 300),
    ('Задержание контрабандистов', '★★★★☆', 7, 6, 450),
    ('Ликвидация вампирского клана', '★★★★★', 3, 8, 600),
    ('Защита каравана', '★☆☆☆☆', 50, 2, 150),
    ('Охота на магических существ', '★★☆☆☆', 25, 3, 225),
    ('Сбор информации', '★★★☆☆', 15, 4, 300),
    ('Уничтожение темного артефакта', '★★★★☆', 7, 6, 450),
    ('Сражение с драконом', '★★★★★', 3, 8, 600),
    ('Оборона замка', '★☆☆☆☆', 50, 2, 150),
    ('Поиск пропавшего мага', '★★☆☆☆', 25, 3, 225),
    ('Защита от фейри', '★★★☆☆', 15, 4, 300),
    ('Разведка подземелий', '★★★★☆', 7, 6, 450),
    ('Победа над темным магом', '★★★★★', 3, 8, 600)
]

cur.executemany('INSERT INTO missions (name, rarity, appearing_rate, length, reward) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING', missions)
conn.commit()

# Function to retrieve balance
def get_balance(user_id):
    cur.execute('SELECT balance FROM balances WHERE user_id = %s', (user_id,))
    result = cur.fetchone()
    return result['balance'] if result else 0

# Function to update balance
def update_balance(user_id, amount):
    current_balance = get_balance(user_id)
    new_balance = current_balance + amount
    cur.execute('INSERT INTO balances (user_id, balance) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET balance = %s', (user_id, new_balance, new_balance))
    conn.commit()
    return new_balance

# Function to reduce balance
def reduce_balance(user_id, amount):
    current_balance = get_balance(user_id)
    if current_balance < amount:
        return None  # Not enough balance
    new_balance = current_balance - amount
    cur.execute('INSERT INTO balances (user_id, balance) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET balance = %s', (user_id, new_balance, new_balance))
    conn.commit()
    return new_balance

# Function to set balance
def set_balance(user_id, amount):
    cur.execute('INSERT INTO balances (user_id, balance) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET balance = %s', (user_id, amount, amount))
    conn.commit()
    return amount

# Function to get user role
def get_user_role(user_id):
    cur.execute('SELECT role FROM users WHERE user_id = %s', (user_id,))
    result = cur.fetchone()
    return result['role'] if result else 'user'

# Function to set user role
def set_user_role(user_id, role):
    cur.execute('INSERT INTO users (user_id, role) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET role = %s', (user_id, role, role))
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
    cur.execute('SELECT streak, last_checkin FROM checkin_streak WHERE user_id = %s', (user_id,))
    result = cur.fetchone()

    if result:
        streak, last_checkin = result['streak'], result['last_checkin']
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
    cur.execute('INSERT INTO checkin_streak (user_id, streak, last_checkin) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET streak = %s, last_checkin = %s', (user_id, streak, today.strftime('%Y-%m-%d %H:%M:%S'), streak, today.strftime('%Y-%m-%d %H:%M:%S')))
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
async def rockpaperscissors_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    cur.execute('SELECT last_play FROM last_game WHERE user_id = %s', (user_id,))
    result = cur.fetchone()
    now = datetime.now()

    if result:
        last_play = result['last_play']
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
    cur.execute('INSERT INTO last_game (user_id, last_play) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET last_play = %s', (user_id, now, now))
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

# Function to generate random missions
def generate_missions():
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
async def missions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    today = datetime.now().date()

    # Check if user has already attempted 3 missions today
    cur.execute('SELECT attempts FROM mission_attempts WHERE user_id = %s AND date = %s', (user_id, today))
    result = cur.fetchone()
    attempts = result['attempts'] if result else 0

    if attempts >= 3:
        await update.message.reply_text("Вы уже отправили 3 отряда на миссии сегодня. Повторите попытку завтра.")
        return

    # Generate 5 random missions based on appearance rates
    missions = generate_missions()

    # Create buttons for each mission
    buttons = [
        InlineKeyboardButton(f"{mission['name']} ({mission['reward']} камней душ)", callback_data=f"mission_{mission['reward']}_{mission['length']}_{mission['name']}")
        for mission in missions
    ]
    keyboard = InlineKeyboardMarkup.from_column(buttons)
    await update.message.reply_text("Выберите миссию для отправки отряда:", reply_markup=keyboard)

# Callback function for mission buttons
async def mission_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data.split('_')
    reward = int(data[1])
    length = int(data[2])
    mission_name = data[3]

    # Check if user has already attempted 3 missions today
    today = datetime.now().date()
    cur.execute('SELECT attempts FROM mission_attempts WHERE user_id = %s AND date = %s', (user_id, today))
    result = cur.fetchone()
    attempts = result['attempts'] if result else 0

    if attempts >= 3:
        await query.edit_message_text("Вы уже отправили 3 отряда на миссии сегодня. Повторите попытку завтра.")
        return

    # Increment the number of attempts for today
    if result:
        cur.execute('UPDATE mission_attempts SET attempts = attempts + 1 WHERE user_id = %s AND date = %s', (user_id, today))
    else:
        cur.execute('INSERT INTO mission_attempts (user_id, date, attempts) VALUES (%s, %s, 1)', (user_id, today))
    conn.commit()

    # Calculate mission end time
    start_time = datetime.now()
    end_time = start_time + timedelta(hours=length)

    # Insert mission into user_missions table
    cur.execute('INSERT INTO user_missions (user_id, mission_id, start_time, end_time) VALUES (%s, %s, %s, %s)', (user_id, reward, start_time, end_time))
    conn.commit()

    await query.edit_message_text(f"Вы отправили отряд на миссию: {mission_name}. Время завершения: {end_time.strftime('%Y-%m-%d %H:%M:%S')}.")

# Function to check for completed missions
async def check_missions(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    cur.execute('SELECT user_id, mission_id FROM user_missions WHERE completed = FALSE AND end_time <= %s', (now,))
    completed_missions = cur.fetchall()

    for mission in completed_missions:
        user_id, mission_id = mission['user_id'], mission['mission_id']
        reward = mission_id  # In this case, mission_id is used as the reward
        update_balance(user_id, reward)
        cur.execute('UPDATE user_missions SET completed = TRUE WHERE user_id = %s AND mission_id = %s', (user_id, mission_id))
        await context.bot.send_message(chat_id=user_id, text=f"Ваша миссия завершена! Вы получили {reward} Камней душ.")
    conn.commit()

# Initialize the bot and add handlers
app = ApplicationBuilder().token("7374196189:AAH5nebr7bg8fVHCSm5uSGhT646sNZJ6nfE").build()

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
app.add_handler(conv_handler)
app.add_handler(CallbackQueryHandler(bet_callback, pattern='^bet_'))
app.add_handler(CallbackQueryHandler(play_callback, pattern='^play_'))
app.add_handler(CallbackQueryHandler(mission_callback, pattern='^mission_'))

job_queue = app.job_queue
job_queue.run_repeating(check_missions, interval=60, first=10)

app.run_polling()