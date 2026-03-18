import logging
import json
import asyncio
import random
import re
import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict

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
DB_CHANNEL_ID = int(os.environ.get('DB_CHANNEL_ID', '-1003883431431'))
ADMIN_IDS = [int(id) for id in os.environ.get('ADMIN_IDS', '1784442476,1389740970,5695593671').split(',')]
CHAT_ID = int(os.environ.get('CHAT_ID', '-1002501760414'))
PORT = int(os.environ.get('PORT', 8080))  # Render даст порт сам

# Ранги (ключ: уровень, значение: название и описание)
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

# Настройки модерации
WARNS_TO_BAN = 3
BAN_DAYS = 5
MUTE_DAYS = 1

# Смайлики для красоты
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
                'next_id': 1
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
                'next_id': 1
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
            
            updates = await self.bot.get_updates(limit=20)
            backups = []
            for update in updates:
                if update.message and update.message.text and update.message.text.startswith('DB_BACKUP'):
                    backups.append((update.message.message_id, update.message.date))
            backups.sort(key=lambda x: x[1], reverse=True)
            for msg_id, _ in backups[3:]:
                try:
                    await self.bot.delete_message(chat_id=self.channel_id, message_id=msg_id)
                except:
                    pass
            print(f"✅ База данных сохранена в Telegram. Сообщение ID: {message.message_id}")
            
        except Exception as e:
            print(f"❌ Ошибка сохранения БД: {e}")
    
    # --- Методы для работы с данными ---
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

# --- Инициализация БД ---
db = None

async def init_db():
    global db
    db = TelegramDB(BOT_TOKEN, DB_CHANNEL_ID)
    await db.load()

# --- Функции-помощники (без изменений) ---
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

# --- Все твои команды (welcome_new_member, mute, unmute, ban, warn, setname, giveaccess, setprefix, nlist, grank, gnick, ranks, warns, bans, mutelist, logs, all_command, wedding, weddings_list, top, me_action, try_action, kiss, slap, hug, rep_plus, rep_minus, profile, info, report, check_user, online, gay, clown, wish, help_command, check_message_rules, update_last_online, start) ---
# Вставь сюда все функции команд из твоего кода (welcome_new_member, mute, unmute, ban, warn, setname, giveaccess, setprefix, nlist, grank, gnick, ranks, warns, bans, mutelist, logs, all_command, wedding, weddings_list, top, me_action, try_action, kiss, slap, hug, rep_plus, rep_minus, profile, info, report, check_user, online, gay, clown, wish, help_command, check_message_rules, update_last_online, start)
# Они идут с 95-й строки и до конца, прямо перед "# --- Точка входа ---"

# --- Точка входа ---
if __name__ == '__main__':
    application = Application.builder().token(BOT_TOKEN).build()

    # Регистрация обработчиков команд (скопируй этот блок из своего кода)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("mute", mute))
    application.add_handler(CommandHandler("unmute", unmute))
    application.add_handler(CommandHandler("ban", ban))
    application.add_handler(CommandHandler("warn", warn))
    application.add_handler(CommandHandler("setname", setname))
    application.add_handler(CommandHandler("giveaccess", giveaccess))
    application.add_handler(CommandHandler("setprefix", setprefix))
    application.add_handler(CommandHandler("nlist", nlist))
    application.add_handler(CommandHandler("grank", grank))
    application.add_handler(CommandHandler("gnick", gnick))
    application.add_handler(CommandHandler("ranks", ranks))
    application.add_handler(CommandHandler("warns", warns))
    application.add_handler(CommandHandler("bans", bans))
    application.add_handler(CommandHandler("mutelist", mutelist))
    application.add_handler(CommandHandler("logs", logs))
    application.add_handler(CommandHandler("all", all_command))
    application.add_handler(CommandHandler("wedding", wedding))
    application.add_handler(CommandHandler("weddings", weddings_list))
    application.add_handler(CommandHandler("top", top))
    application.add_handler(CommandHandler("me", me_action))
    application.add_handler(CommandHandler("try", try_action))
    application.add_handler(CommandHandler("kiss", kiss))
    application.add_handler(CommandHandler("slap", slap))
    application.add_handler(CommandHandler("hug", hug))
    application.add_handler(CommandHandler("repplus", rep_plus))
    application.add_handler(CommandHandler("repminus", rep_minus))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("info", info))
    application.add_handler(CommandHandler("report", report))
    application.add_handler(CommandHandler("check", check_user))
    application.add_handler(CommandHandler("online", online))
    application.add_handler(CommandHandler("gay", gay))
    application.add_handler(CommandHandler("clown", clown))
    application.add_handler(CommandHandler("wish", wish))

    # Обработчики сообщений
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, update_last_online), group=1)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_message_rules), group=2)

    # Запуск через вебхуки для Render
    async def run_webhook():
        """Инициализация и запуск вебхуков"""
        global db
        print("🚀 Бот запускается на Render...")
        await init_db()
        print("✅ БД загружена, запускаем вебхуки...")
        
        # Настройка вебхука
        await application.initialize()
        await application.start()
        
        # Render даст свой URL
        webhook_url = os.environ.get('RENDER_EXTERNAL_URL')
        if not webhook_url:
            raise ValueError("❌ RENDER_EXTERNAL_URL не задан!")
        
        # Устанавливаем вебхук
        await application.bot.set_webhook(
            url=f"{webhook_url}/webhook",
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
        print(f"✅ Вебхук установлен на {webhook_url}/webhook")
        print("🤖 Бот готов к работе 24/7!")

        # Бесконечное ожидание (бот работает постоянно)
        try:
            while True:
                await asyncio.sleep(3600)  # Спим час, проверяем
                # Сохраняем БД каждый час
                print("💾 Автосохранение БД...")
                await db.save()
        except KeyboardInterrupt:
            print("🛑 Останавливаем бота...")
            await application.bot.delete_webhook()
            await application.stop()
            await application.shutdown()
            print("👋 Бот завершил работу.")

    # Запускаем
    asyncio.run(run_webhook())