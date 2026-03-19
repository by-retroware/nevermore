import logging
import json
import asyncio
import random
import re
import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
)
from telegram.constants import ParseMode
from telegram import Bot
from telegram.error import TelegramError

# --- Настройки ---
BOT_TOKEN = os.environ.get('BOT_TOKEN')
DB_CHANNEL_ID = int(os.environ.get('DB_CHANNEL_ID', '-1002456893352'))
ADMIN_IDS = [int(id) for id in os.environ.get('ADMIN_IDS', '5695593671').split(',')]
CHAT_ID = int(os.environ.get('CHAT_ID', '-1002162455644'))

# Ранги
RANKS = {
    2: {"name": "👶 Новичок", "description": "• У вас есть 6 машин в автопарке\n• фри ранг в дс с гайдами\n• советы для новичков\n• топ работы\n• скрипты\n• как расширить инвентарь"},
    3: {"name": "🏎 Любитель скорости", "description": "• Доступен средний автопарк\n• Можете выбрать себе любой тег\n• Карта с секретными персонажами\n• Получение наёмного фермера\n\nВы так же можете приобрести 3 ранг за смену фамилии на Nevermore, цена 20кк"},
    4: {"name": "🎓 Образованный", "description": "• Куда вложить первые деньги?\n• Что делать при старте игры?\n• Как узнать цену на любой товар?\n\nЦена 30кк"},
    5: {"name": "🌑 Невермор", "description": "• Полезные инвестиции, куда вложить чтобы сделать больше\n• Расскажем как зарабатывать афк\n• Открыт доступ к полезным скриптам\n\nЦена 40кк"},
    6: {"name": "💡 Шарющий", "description": "• Доступен улучшенный автопарк\n• Ответы на клады\n• Как получить тайник VC\n• Как заработать много денег\n• Как заработать азекоины\n\nЦена 60кк"},
    7: {"name": "💰 Барыга", "description": "• Доступ к гайдам:\n  - как ловить лавки на цр\n  - как барыжить на цр\n  - конфиги для скупки на цр\n\nЦена 70кк"},
    8: {"name": "💎 Премиум", "description": "• Доступен абсолютно весь автопарк\n• Доступны все гайды:\n  + мой опыт фарма\n• Любой тег\n• Чат с лидером семьи, отвечу на любые вопросы, в любое время\n• Как выбивать тачки с ларцов\n• Анти-кик с фамы (можете в ней находиться хоть год, вас не кикнут)\n• Как фармить новые клады\n\nЦена 100кк"},
    9: {"name": "👑 Зам. Лидера", "description": "Правая рука лидера."},
    10: {"name": "👑👑 Лидер", "description": "Глава семьи Nevermore."},
}

WARNS_TO_BAN = 3
BAN_DAYS = 5
MUTE_DAYS = 1
REP_LIMIT_PER_DAY = 2

EMOJI = {
    "warn": "⚠️",
    "ban": "🔨",
    "mute": "🔇",
    "unmute": "🔊",
    "info": "ℹ️",
    "success": "✅",
    "error": "❌",
    "heart": "❤️",
    "crown": "👑",
    "game": "🎮",
    "profile": "👤",
    "list": "📜",
    "rules": "📏",
    "rep": "⭐",
    "online": "🟢",
    "offline": "⚫",
    "wedding": "💍",
    "gay": "🏳️‍🌈",
    "clown": "🤡",
    "wish": "✨",
    "mod": "🛡️",
    "fun": "🎉",
    "stats": "📊",
}

# --- Telegram Storage ---
class TelegramDB:
    def __init__(self, token, channel_id):
        self.bot = Bot(token=token)
        self.channel_id = channel_id
        self.cache = None
        self.last_update_id = 0
        
    async def load(self):
        try:
            updates = await self.bot.get_updates(offset=self.last_update_id, limit=10)
            for update in updates:
                if update.message and update.message.text:
                    if update.message.text.startswith('DB_BACKUP'):
                        json_str = update.message.text[9:]
                        self.cache = json.loads(json_str)
                        self.last_update_id = update.update_id + 1
                        print(f"✅ База данных загружена из Telegram. Записей: {len(self.cache.get('users', {}))}")
                        return self.cache
                        
            print("⚠️ База данных не найдена, создаем новую")
            self.cache = {
                'users': {},
                'mutes': {},
                'bans': {},
                'warns': {},
                'weddings': [],
                'logs': [],
                'next_id': 1,
                'rep_usage': {}
            }
            await self.save()
            return self.cache
            
        except Exception as e:
            print(f"❌ Ошибка загрузки БД: {e}")
            self.cache = {
                'users': {},
                'mutes': {},
                'bans': {},
                'warns': {},
                'weddings': [],
                'logs': [],
                'next_id': 1,
                'rep_usage': {}
            }
            return self.cache
    
    async def save(self):
        try:
            if not self.cache:
                return
                
            json_str = json.dumps(self.cache, ensure_ascii=False, indent=2, default=str)
            message = await self.bot.send_message(
                chat_id=self.channel_id,
                text=f"DB_BACKUP{json_str}"
            )
            print(f"✅ База данных сохранена в Telegram. Сообщение ID: {message.message_id}")
            
        except Exception as e:
            print(f"❌ Ошибка сохранения БД: {e}")
    
    def get_user(self, user_id):
        return self.cache['users'].get(str(user_id))
    
    def update_user(self, user_id, data):
        self.cache['users'][str(user_id)] = data
        
    def add_user(self, user_id, username, first_name):
        if str(user_id) not in self.cache['users']:
            self.cache['users'][str(user_id)] = {
                'user_id': user_id,
                'username': username,
                'first_name': first_name,
                'nickname': None,
                'rank': 2,
                'warns': 0,
                'reputation': 0,
                'joined_date': datetime.now().isoformat(),
                'spouse_id': None,
                'prefix': None,
                'last_online': datetime.now().isoformat()
            }
            return True
        return False
    
    def add_log(self, user_id, username, action):
        log_entry = {
            'id': self.cache.get('next_id', 1),
            'user_id': user_id,
            'username': username,
            'action': action,
            'timestamp': datetime.now().isoformat()
        }
        self.cache['logs'].append(log_entry)
        self.cache['next_id'] = self.cache.get('next_id', 1) + 1
        if len(self.cache['logs']) > 1000:
            self.cache['logs'] = self.cache['logs'][-1000:]
    
    def add_mute(self, user_id, muted_until, reason):
        self.cache['mutes'][str(user_id)] = {
            'user_id': user_id,
            'muted_until': muted_until.isoformat() if isinstance(muted_until, datetime) else muted_until,
            'reason': reason
        }
    
    def remove_mute(self, user_id):
        if str(user_id) in self.cache['mutes']:
            del self.cache['mutes'][str(user_id)]
    
    def get_mute(self, user_id):
        return self.cache['mutes'].get(str(user_id))
    
    def add_ban(self, user_id, banned_until, reason):
        self.cache['bans'][str(user_id)] = {
            'user_id': user_id,
            'banned_until': banned_until.isoformat() if isinstance(banned_until, datetime) else banned_until,
            'reason': reason
        }
    
    def remove_ban(self, user_id):
        if str(user_id) in self.cache['bans']:
            del self.cache['bans'][str(user_id)]
    
    def get_ban(self, user_id):
        return self.cache['bans'].get(str(user_id))
    
    def add_wedding(self, user1_id, user2_id):
        wedding = {
            'id': len(self.cache['weddings']) + 1,
            'user1_id': user1_id,
            'user2_id': user2_id,
            'date': datetime.now().isoformat()
        }
        self.cache['weddings'].append(wedding)
        return wedding
    
    def get_all_users(self):
        return list(self.cache['users'].values())
    
    def get_all_mutes(self):
        return list(self.cache['mutes'].values())
    
    def get_all_bans(self):
        return list(self.cache['bans'].values())
    
    def get_all_logs(self, limit=20):
        return self.cache['logs'][-limit:]
    
    def get_all_weddings(self):
        return self.cache['weddings']
    
    def check_rep_limit(self, user_id):
        today = datetime.now().date().isoformat()
        if 'rep_usage' not in self.cache:
            self.cache['rep_usage'] = {}
        
        user_data = self.cache['rep_usage'].get(str(user_id), {'date': today, 'count': 0})
        
        if user_data.get('date') != today:
            user_data = {'date': today, 'count': 0}
        
        if user_data['count'] >= REP_LIMIT_PER_DAY:
            return False
        
        user_data['count'] += 1
        self.cache['rep_usage'][str(user_id)] = user_data
        return True

db = None

async def init_db():
    global db
    db = TelegramDB(BOT_TOKEN, DB_CHANNEL_ID)
    await db.load()

def get_user(user_id):
    return db.get_user(user_id)

def update_user_rank(user_id, new_rank):
    user = db.get_user(user_id)
    if user:
        user['rank'] = new_rank
        db.update_user(user_id, user)

def add_warn(user_id):
    user = db.get_user(user_id)
    if user:
        user['warns'] = user.get('warns', 0) + 1
        db.update_user(user_id, user)
        if user['warns'] >= WARNS_TO_BAN:
            return True
    return False

def log_action(user_id, username, action):
    db.add_log(user_id, username, action)

def get_user_rank(user_id):
    user = db.get_user(user_id)
    return user['rank'] if user else 2

def is_muted(user_id):
    mute = db.get_mute(user_id)
    if mute:
        mute_until = datetime.fromisoformat(mute['muted_until'])
        if mute_until > datetime.now():
            return True
        else:
            db.remove_mute(user_id)
    return False

def is_banned(user_id):
    ban = db.get_ban(user_id)
    if ban:
        ban_until = datetime.fromisoformat(ban['banned_until'])
        if ban_until > datetime.now():
            return True
        else:
            db.remove_ban(user_id)
    return False

def has_permission(user_id, required_rank):
    user_rank = get_user_rank(user_id)
    return user_rank >= required_rank

# --- Команды ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"{EMOJI['heart']} <b>Добро пожаловать в семью Nevermore!</b>\n\n"
        f"👋 Привет, {user.full_name}!\n\n"
        f"Я — бот-помощник нашей семьи. Со мной ты можешь:\n"
        f"• {EMOJI['profile']} Узнать информацию о себе\n"
        f"• {EMOJI['wedding']} Жениться/выйти замуж\n"
        f"• {EMOJI['rep']} Повышать репутацию друзьям\n"
        f"• {EMOJI['fun']} Весело проводить время\n\n"
        f"📌 <b>Важно:</b> Чтобы я мог модерировать чат, выдай мне права администратора!\n\n"
        f"🔍 Введи /help, чтобы увидеть все мои команды.",
        parse_mode=ParseMode.HTML
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = f"""
{EMOJI['info']} <b>📚 ВСЕ КОМАНДЫ БОТА NEVERMORE</b>

{EMOJI['fun']} <b>ОБЩИЕ КОМАНДЫ (ДЛЯ ВСЕХ):</b>
• /profile - твоя карточка игрока
• /info - информация о семье
• /gnick <ник> - установить никнейм
• /top - топ по репутации
• /ranks - список всех рангов
• /nlist - список всех игроков
• /online - кто сейчас онлайн

{EMOJI['wedding']} <b>СВАДЬБЫ И ОТНОШЕНИЯ:</b>
• /wedding [ответ] - предложить брак
• /weddings - список всех семейных пар

{EMOJI['rep']} <b>РЕПУТАЦИЯ (2 раза в день):</b>
• /repplus [ответ] - повысить репутацию
• /repminus [ответ] - понизить репутацию

{EMOJI['fun']} <b>РАЗВЛЕЧЕНИЯ:</b>
• /me <действие> - действие от 3-го лица
• /try <действие> - проверить удачу
• /kiss [ответ] - поцеловать
• /hug [ответ] - обнять
• /slap [ответ] - дать пощечину
• /gay - гей дня
• /clown - клоун дня
• /wish - предсказание на день

{EMOJI['mod']} <b>🛡️ МОДЕРАЦИЯ (ДОСТУПНО ВСЕМ):</b>
• /mutelist - список замученных
• /warns - список предупреждений
• /bans - список забаненных
• /report [ответ] <причина> - пожаловаться админам

{EMOJI['crown']} <b>👑 АДМИН-КОМАНДЫ (РАНГ 8+):</b>
• /mute <причина> - замутить
• /unmute [ответ] - размутить
• /warn <причина> - выдать варн
• /ban <причина> - забанить
• /setname <ник> - сменить ник юзеру
• /setprefix <префикс> - дать префикс
• /grank <ранг> - выдать игровой ранг
• /check <ник> - проверить пользователя
• /logs - логи действий

{EMOJI['crown']} <b>👑 ЛИДЕР-КОМАНДЫ (РАНГ 10):</b>
• /giveaccess <8/9/10> - выдать админку
• /all - обращение ко всем
"""
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        db.add_user(member.id, member.username, member.first_name)
        
        welcome_text = (
            f"👋 {member.full_name}, добро пожаловать в группу Fam Nevermore!\n\n"
            f"📝 Напиши, пожалуйста, свой ник в авторизацию в течение 24 часов, иначе кик.\n"
            f"📖 Просим ознакомиться с правилами чата: https://t.me/famnevermore/26\n"
            f"🔑 Ссылка на авторизацию: https://t.me/famnevermore/19467\n\n"
            f"Приятного общения! {EMOJI['heart']}"
        )
        await update.message.reply_text(welcome_text)
        log_action(member.id, member.username, "joined the chat")
    
    await db.save()

# --- Заглушка для Render ---
import threading
from flask import Flask

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Nevermore Bot is running! 🤖"

@flask_app.route('/health')
def health():
    return "OK", 200

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    flask_app.run(host='0.0.0.0', port=port)

flask_thread = threading.Thread(target=run_flask)
flask_thread.daemon = True
flask_thread.start()

# --- ЗАПУСК ---
async def main():
    print("🚀 Бот запускается...")
    
    await init_db()
    print("✅ БД загружена")
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    
    print("✅ Обработчики зарегистрированы")
    
    print("🚀 Запускаем polling...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    print("🤖 Бот работает 24/7!")
    
    try:
        while True:
            await asyncio.sleep(3600)
            print("💾 Автосохранение БД...")
            await db.save()
    except KeyboardInterrupt:
        print("🛑 Останавливаем бота...")
        await application.updater.stop()
        await application.stop()
        await application.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
