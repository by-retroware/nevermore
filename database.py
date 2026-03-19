import sqlite3
import os
from datetime import datetime

DB_PATH = os.environ.get('DB_PATH', '/opt/render/project/src/data/bot.db')

class Database:
    def __init__(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        self.init_db()
    
    def init_db(self):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            nickname TEXT,
            rank INTEGER DEFAULT 2,
            warns INTEGER DEFAULT 0,
            reputation INTEGER DEFAULT 0,
            joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            spouse_id INTEGER DEFAULT NULL,
            prefix TEXT DEFAULT NULL,
            last_online TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS mutes (
            user_id INTEGER PRIMARY KEY,
            muted_until TIMESTAMP,
            reason TEXT
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS bans (
            user_id INTEGER PRIMARY KEY,
            banned_until TIMESTAMP,
            reason TEXT
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            action TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS weddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user1_id INTEGER,
            user2_id INTEGER,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS rep_usage (
            user_id INTEGER,
            date TEXT,
            count INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, date)
        )''')
        
        conn.commit()
        conn.close()
        print(f"✅ База данных инициализирована")
    
    def get_user(self, user_id):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return {
                'user_id': row[0],
                'username': row[1],
                'first_name': row[2],
                'nickname': row[3],
                'rank': row[4],
                'warns': row[5],
                'reputation': row[6],
                'joined_date': row[7],
                'spouse_id': row[8],
                'prefix': row[9],
                'last_online': row[10]
            }
        return None
    
    def add_user(self, user_id, username, first_name):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        try:
            c.execute('''INSERT OR IGNORE INTO users 
                        (user_id, username, first_name, joined_date) 
                        VALUES (?, ?, ?, ?)''',
                     (user_id, username, first_name, datetime.now().isoformat()))
            conn.commit()
            return True
        except Exception as e:
            print(f"Ошибка добавления пользователя: {e}")
            return False
        finally:
            conn.close()
    
    def update_user(self, user_id, **kwargs):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        try:
            for key, value in kwargs.items():
                c.execute(f"UPDATE users SET {key} = ? WHERE user_id = ?", (value, user_id))
            conn.commit()
        except Exception as e:
            print(f"Ошибка обновления пользователя: {e}")
        finally:
            conn.close()
    
    def add_mute(self, user_id, muted_until, reason):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO mutes (user_id, muted_until, reason) 
                     VALUES (?, ?, ?)''', (user_id, muted_until.isoformat(), reason))
        conn.commit()
        conn.close()
    
    def remove_mute(self, user_id):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM mutes WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
    
    def get_mute(self, user_id):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT muted_until, reason FROM mutes WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return {'muted_until': row[0], 'reason': row[1]}
        return None
    
    def add_ban(self, user_id, banned_until, reason):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO bans (user_id, banned_until, reason) 
                     VALUES (?, ?, ?)''', (user_id, banned_until.isoformat(), reason))
        conn.commit()
        conn.close()
    
    def remove_ban(self, user_id):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM bans WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
    
    def get_ban(self, user_id):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT banned_until, reason FROM bans WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return {'banned_until': row[0], 'reason': row[1]}
        return None
    
    def add_log(self, user_id, username, action):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT INTO logs (user_id, username, action, timestamp) 
                     VALUES (?, ?, ?, ?)''', 
                  (user_id, username, action, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    
    def get_logs(self, limit=20):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''SELECT username, action, timestamp FROM logs 
                     ORDER BY id DESC LIMIT ?''', (limit,))
        rows = c.fetchall()
        conn.close()
        return rows
    
    def add_wedding(self, user1_id, user2_id):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT INTO weddings (user1_id, user2_id, date) 
                     VALUES (?, ?, ?)''', (user1_id, user2_id, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    
    def get_weddings(self):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''SELECT * FROM weddings''')
        rows = c.fetchall()
        conn.close()
        return rows
    
    def check_rep_limit(self, user_id):
        today = datetime.now().date().isoformat()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('''SELECT count FROM rep_usage 
                     WHERE user_id = ? AND date = ?''', (user_id, today))
        row = c.fetchone()
        
        if row and row[0] >= 2:
            conn.close()
            return False
        
        if row:
            c.execute('''UPDATE rep_usage SET count = count + 1 
                         WHERE user_id = ? AND date = ?''', (user_id, today))
        else:
            c.execute('''INSERT INTO rep_usage (user_id, date, count) 
                         VALUES (?, ?, 1)''', (user_id, today))
        
        conn.commit()
        conn.close()
        return True
    
    def get_all_users(self):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT * FROM users")
        rows = c.fetchall()
        conn.close()
        return rows
    
    def get_all_mutes(self):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT * FROM mutes")
        rows = c.fetchall()
        conn.close()
        return rows
    
    def get_all_bans(self):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT * FROM bans")
        rows = c.fetchall()
        conn.close()
        return rows
