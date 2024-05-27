import logging
import sqlite3
import random
from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
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

# Define a function to handle the /check-in command
async def checkin_command(update: Update, context):
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

# Define a function to handle the /reading command
async def reading_command(update: Update, context):
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

app = ApplicationBuilder().token("7175746196:AAHckVjmat7IBpqvzWfTxvUzvQR1_1FgLiw").build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
app.add_handler(CommandHandler("balance", balance_command))
app.add_handler(CommandHandler("checkin", checkin_command))
app.add_handler(CommandHandler("reading", reading_command))
app.run_polling()
