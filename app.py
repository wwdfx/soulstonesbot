# app.py

import logging
import psycopg2
import random
from psycopg2.extras import DictCursor
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

# Set up basic logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Connect to PostgreSQL Database
def get_db_connection():
    conn = psycopg2.connect(
        dbname="koyebdb",
        user="koyeb-adm",
        password="WCAFr1R0muaZ",
        host="ep-shy-pine-a2e1ouuw.eu-central-1.pg.koyeb.app",
        port=5432
    )
    conn.autocommit = True
    return conn

conn = get_db_connection()
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

# Check-in system
@app.route('/checkin', methods=['POST'])
def checkin():
    data = request.json
    user_id = data.get('user_id')
    today = datetime.now()
    cur.execute('SELECT streak, last_checkin FROM checkin_streak WHERE user_id = %s', (user_id,))
    result = cur.fetchone()

    if result:
        streak, last_checkin = result['streak'], result['last_checkin']

        if today.date() == last_checkin.date():
            return jsonify({"message": "You have already checked in today. Try again tomorrow."})

        if today - last_checkin > timedelta(days=1):
            streak = 1
            reward = 25
        else:
            streak += 1
            if streak > 7:
                streak = 7
            reward = 25 * streak
    else:
        streak = 1
        reward = 25

    cur.execute('INSERT INTO checkin_streak (user_id, streak, last_checkin) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET streak = %s, last_checkin = %s', (user_id, streak, today, streak, today))
    conn.commit()

    new_balance = update_balance(user_id, reward)
    return jsonify({"message": f"Checked in for {streak} consecutive days. You have earned {reward} soulstones.", "new_balance": new_balance})

# Function to handle /balance command
@app.route('/balance', methods=['GET'])
def balance():
    user_id = request.args.get('user_id')
    balance = get_balance(user_id)
    return jsonify({"balance": balance})

# Function to handle /reading command
readings = [
    "Today's angelic power will guide you.",
    "A new rune will reveal its true purpose to you.",
    "Beware of demons lurking in unexpected places.",
    # Add more readings here...
]

@app.route('/reading', methods=['POST'])
def reading():
    data = request.json
    user_id = data.get('user_id')
    if not can_request_reading(user_id):
        return jsonify({"message": "You have already requested a reading today. Try again tomorrow."})

    if reduce_balance(user_id, 50) is None:
        return jsonify({"message": "Insufficient soulstones for a reading."})

    reading = random.choice(readings)
    return jsonify({"message": f"Your reading for today: {reading}"})

# Function to handle /addbalance command (admin only)
@app.route('/addbalance', methods=['POST'])
def add_balance():
    data = request.json
    user_id = data.get('user_id')
    target_user_id = data.get('target_user_id')
    amount = data.get('amount')

    if get_user_role(user_id) != 'admin':
        return jsonify({"message": "You do not have permission to perform this command."})

    try:
        amount = int(amount)
    except ValueError:
        return jsonify({"message": "Please enter a valid number."})

    new_balance = update_balance(target_user_id, amount)
    return jsonify({"message": f"User {target_user_id}'s balance increased by {amount} soulstones. New balance: {new_balance}"})

# Function to handle /subbalance command (admin only)
@app.route('/subbalance', methods=['POST'])
def sub_balance():
    data = request.json
    user_id = data.get('user_id')
    target_user_id = data.get('target_user_id')
    amount = data.get('amount')

    if get_user_role(user_id) != 'admin':
        return jsonify({"message": "You do not have permission to perform this command."})

    try:
        amount = int(amount)
    except ValueError:
        return jsonify({"message": "Please enter a valid number."})

    new_balance = reduce_balance(target_user_id, amount)
    if new_balance is None:
        return jsonify({"message": "Insufficient soulstones to perform this operation."})

    return jsonify({"message": f"User {target_user_id}'s balance decreased by {amount} soulstones. New balance: {new_balance}"})

# Function to handle /setbalance command (admin only)
@app.route('/setbalance', methods=['POST'])
def set_balance_command():
    data = request.json
    user_id = data.get('user_id')
    target_user_id = data.get('target_user_id')
    amount = data.get('amount')

    if get_user_role(user_id) != 'admin':
        return jsonify({"message": "You do not have permission to perform this command."})

    try:
        amount = int(amount)
    except ValueError:
        return jsonify({"message": "Please enter a valid number."})

    new_balance = set_balance(target_user_id, amount)
    return jsonify({"message": f"User {target_user_id}'s balance set to {amount} soulstones. New balance: {new_balance}"})

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
@app.route('/missions', methods=['GET'])
def missions():
    user_id = request.args.get('user_id')
    today = datetime.now().date()

    cur.execute('SELECT attempts FROM mission_attempts WHERE user_id = %s AND date = %s', (user_id, today))
    result = cur.fetchone()
    attempts = result['attempts'] if result else 0

    if attempts >= 3:
        return jsonify({"message": "You have already sent 3 teams on missions today. Try again tomorrow."})

    missions = generate_missions()
    return jsonify({"missions": missions})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
