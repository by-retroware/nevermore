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
DB_CHANNEL_ID = int(os.environ.get('DB_CHANNEL_ID', '-1003883431431'))
ADMIN_IDS = [int(id) for id in os.environ.get('ADMIN_IDS', '5695593671').split(',')]
CHAT_ID = int(os.environ.get('CHAT_ID', '-1002501760414'))

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

# Настройки модерации
WARNS_TO_BAN = 3
BAN_DAYS = 5
MUTE_DAYS = 1
REP_LIMIT_PER_DAY = 2

# Смайлики
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
                'rep_usage': {}  # {user_id: {'last_reset': date, 'count': int}}
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
        """Проверяет, может ли пользователь использовать репутацию"""
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

# --- Инициализация БД ---
db = None

async def init_db():
    global db
    db = TelegramDB(BOT_TOKEN, DB_CHANNEL_ID)
    await db.load()

# --- Функции-помощники ---
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
    """Приветственное сообщение"""
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
    """Улучшенный /help со всеми командами для всех"""
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

async def who_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /who - показывает информацию о пользователе"""
    if not context.args:
        await update.message.reply_text(f"{EMOJI['error']} Укажи ник или имя. Пример: /who Diego_Retroware")
        return
    
    query = " ".join(context.args).lower()
    
    found_user = None
    for user in db.get_all_users():
        nickname = user.get('nickname', '').lower() if user.get('nickname') else ''
        username = user.get('username', '').lower() if user.get('username') else ''
        first_name = user.get('first_name', '').lower() if user.get('first_name') else ''
        
        if query in nickname or query in username or query in first_name:
            found_user = user
            break

    if not found_user:
        await update.message.reply_text(f"{EMOJI['error']} Пользователь не найден в базе.")
        return

    rank_name = RANKS.get(found_user.get('rank', 2), {}).get('name', 'Неизвестно')
    text = (
        f"{EMOJI['profile']} <b>Информация о пользователе</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"👤 Имя: {found_user.get('first_name', 'Нет')}\n"
        f"📛 Ник: {found_user.get('nickname', 'Нет')}\n"
        f"🆔 ID: <code>{found_user['user_id']}</code>\n"
        f"📊 Ранг: {rank_name} ({found_user.get('rank', 2)})\n"
        f"{EMOJI['rep']} Репутация: {found_user.get('reputation', 0)}\n"
        f"{EMOJI['warn']} Варны: {found_user.get('warns', 0)}\n"
        f"📅 В семье с: {found_user.get('joined_date', '')[:10]}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def gay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Гей дня - выбирает случайного участника чата"""
    try:
        # Получаем участников чата
        chat = update.effective_chat
        if not chat:
            await update.message.reply_text(f"{EMOJI['error']} Эта команда работает только в группах.")
            return
        
        # Пробуем получить участников через API
        admins = await context.bot.get_chat_administrators(chat.id)
        members = admins  # пока только админы, но для демо сойдёт
        
        if not members:
            # Если не получилось, берём из базы
            users = db.get_all_users()
            if users:
                gay_of_day = random.choice(users)
                name = gay_of_day.get('nickname') or gay_of_day.get('username') or gay_of_day.get('first_name') or f"id{gay_of_day['user_id']}"
                mention = f"@{gay_of_day.get('username')}" if gay_of_day.get('username') else name
            else:
                await update.message.reply_text(f"{EMOJI['error']} Нет участников в базе.")
                return
        else:
            # Выбираем случайного админа
            gay_member = random.choice(admins)
            name = gay_member.user.full_name
            mention = f"@{gay_member.user.username}" if gay_member.user.username else name
        
        await update.message.reply_text(
            f"{EMOJI['gay']} <b>🏳️‍🌈 ГЕЙ ДНЯ 🏳️‍🌈</b>\n\n"
            f"🎉 Поздравляем, <b>{mention}</b>!\n"
            f"Ты сегодня главный гей в семье Nevermore!\n\n"
            f"{random.choice(['🏆', '👑', '💅', '🌈', '🦄'])} Гордись, это почётно!",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        print(f"Ошибка в /gay: {e}")
        # Запасной вариант
        users = db.get_all_users()
        if users:
            gay_of_day = random.choice(users)
            name = gay_of_day.get('nickname') or gay_of_day.get('username') or gay_of_day.get('first_name') or f"id{gay_of_day['user_id']}"
            await update.message.reply_text(
                f"{EMOJI['gay']} <b>🏳️‍🌈 ГЕЙ ДНЯ 🏳️‍🌈</b>\n\n"
                f"🎉 Поздравляем, <b>{name}</b>!",
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(f"{EMOJI['error']} Нет участников в базе.")

async def clown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Клоун дня - выбирает случайного участника чата"""
    try:
        chat = update.effective_chat
        if not chat:
            await update.message.reply_text(f"{EMOJI['error']} Эта команда работает только в группах.")
            return
        
        admins = await context.bot.get_chat_administrators(chat.id)
        
        if admins:
            clown_member = random.choice(admins)
            name = clown_member.user.full_name
            mention = f"@{clown_member.user.username}" if clown_member.user.username else name
        else:
            users = db.get_all_users()
            if not users:
                await update.message.reply_text(f"{EMOJI['error']} Нет участников в базе.")
                return
            clown_user = random.choice(users)
            name = clown_user.get('nickname') or clown_user.get('username') or clown_user.get('first_name') or f"id{clown_user['user_id']}"
            mention = name
        
        await update.message.reply_text(
            f"{EMOJI['clown']} <b>🤡 КЛОУН ДНЯ 🤡</b>\n\n"
            f"🎪 Сегодня главный клоун — <b>{mention}</b>!\n"
            f"{random.choice(['🤡', '🎭', '🎪', '🃏', '😜'])} Цирк уехал, а клоун остался!",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        print(f"Ошибка в /clown: {e}")
        users = db.get_all_users()
        if users:
            clown_of_day = random.choice(users)
            name = clown_of_day.get('nickname') or clown_of_day.get('username') or clown_of_day.get('first_name') or f"id{clown_of_day['user_id']}"
            await update.message.reply_text(
                f"{EMOJI['clown']} <b>🤡 КЛОУН ДНЯ 🤡</b>\n\n"
                f"🎪 Сегодня главный клоун — <b>{name}</b>!",
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(f"{EMOJI['error']} Нет участников в базе.")

async def rep_plus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Повышение репутации (2 раза в день)"""
    if not update.message.reply_to_message:
        await update.message.reply_text(f"{EMOJI['error']} Ответь на сообщение пользователя, чтобы повысить ему репутацию.")
        return
    
    target = update.message.reply_to_message.from_user
    if target.id == update.effective_user.id:
        await update.message.reply_text(f"{EMOJI['error']} Нельзя менять репутацию самому себе.")
        return
    
    # Проверяем лимит
    if not db.check_rep_limit(update.effective_user.id):
        await update.message.reply_text(
            f"{EMOJI['error']} Ты уже использовал все попытки на сегодня ({REP_LIMIT_PER_DAY}/2).\n"
            f"Лимит сбрасывается в полночь по МСК."
        )
        return
    
    user = get_user(target.id)
    if user:
        user['reputation'] = user.get('reputation', 0) + 1
        db.update_user(target.id, user)
        await update.message.reply_text(
            f"{EMOJI['rep']} <b>Репутация повышена!</b>\n"
            f"👤 Пользователь: {target.full_name}\n"
            f"📈 Текущая репутация: {user['reputation']} ⭐\n"
            f"💡 Осталось попыток сегодня: {REP_LIMIT_PER_DAY - db.cache['rep_usage'].get(str(update.effective_user.id), {}).get('count', 0)}/{REP_LIMIT_PER_DAY}",
            parse_mode=ParseMode.HTML
        )
        await db.save()

async def rep_minus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Понижение репутации (2 раза в день)"""
    if not update.message.reply_to_message:
        await update.message.reply_text(f"{EMOJI['error']} Ответь на сообщение пользователя, чтобы понизить ему репутацию.")
        return
    
    target = update.message.reply_to_message.from_user
    if target.id == update.effective_user.id:
        await update.message.reply_text(f"{EMOJI['error']} Нельзя менять репутацию самому себе.")
        return
    
    # Проверяем лимит
    if not db.check_rep_limit(update.effective_user.id):
        await update.message.reply_text(
            f"{EMOJI['error']} Ты уже использовал все попытки на сегодня ({REP_LIMIT_PER_DAY}/2).\n"
            f"Лимит сбрасывается в полночь по МСК."
        )
        return
    
    user = get_user(target.id)
    if user:
        user['reputation'] = user.get('reputation', 0) - 1
        db.update_user(target.id, user)
        await update.message.reply_text(
            f"{EMOJI['rep']} <b>Репутация понижена!</b>\n"
            f"👤 Пользователь: {target.full_name}\n"
            f"📉 Текущая репутация: {user['reputation']} ⭐\n"
            f"💡 Осталось попыток сегодня: {REP_LIMIT_PER_DAY - db.cache['rep_usage'].get(str(update.effective_user.id), {}).get('count', 0)}/{REP_LIMIT_PER_DAY}",
            parse_mode=ParseMode.HTML
        )
        await db.save()

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Жалоба на сообщение - отправляет админам"""
    if not update.message.reply_to_message:
        await update.message.reply_text(f"{EMOJI['error']} Ответь на сообщение, на которое хочешь пожаловаться.")
        return

    reason = " ".join(context.args) if context.args else "Причина не указана"
    bad_msg = update.message.reply_to_message
    bad_user = bad_msg.from_user
    reporter = update.effective_user

    # Находим всех админов (ранг 9 и 10)
    admins = [u for u in db.get_all_users() if u.get('rank', 0) in [9, 10]]
    
    # Добавляем ADMIN_IDS из переменных окружения
    for admin_id in ADMIN_IDS:
        admin_user = get_user(admin_id)
        if admin_user and admin_user not in admins:
            admins.append(admin_user)
        elif not admin_user:
            # Если админа нет в базе, создаем временную запись
            admins.append({'user_id': admin_id, 'rank': 10})
    
    text = (
        f"🚨 <b>⚠️ ЖАЛОБА ⚠️</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📝 <b>От:</b> {reporter.full_name}"
    )
    if reporter.username:
        text += f" (@{reporter.username})"
    text += f"\n👤 <b>ID:</b> <code>{reporter.id}</code>\n\n"
    text += f"👮 <b>Нарушитель:</b> {bad_user.full_name}"
    if bad_user.username:
        text += f" (@{bad_user.username})"
    text += f"\n🆔 <b>ID:</b> <code>{bad_user.id}</code>\n\n"
    text += f"📌 <b>Причина:</b> {reason}\n\n"
    text += f"💬 <b>Сообщение:</b>\n{bad_msg.text or bad_msg.caption or '[Медиа]'}\n\n"
    text += f"🔗 <a href='{bad_msg.link}'>Перейти к сообщению</a>"
    
    sent_count = 0
    for admin in admins:
        try:
            await context.bot.send_message(
                admin['user_id'], 
                text, 
                parse_mode=ParseMode.HTML, 
                disable_web_page_preview=True
            )
            sent_count += 1
        except Exception as e:
            print(f"Не удалось отправить админу {admin.get('user_id')}: {e}")
    
    if sent_count > 0:
        await update.message.reply_text(
            f"{EMOJI['success']} <b>Жалоба отправлена!</b>\n"
            f"📨 Получателей: {sent_count}\n"
            f"🕐 Администраторы рассмотрят её в ближайшее время.",
            parse_mode=ParseMode.HTML
        )
        log_action(reporter.id, reporter.username, f"report on {bad_user.id}: {reason}")
    else:
        await update.message.reply_text(
            f"{EMOJI['error']} ❌ <b>Ошибка отправки</b>\n"
            f"К сожалению, администраторы сейчас недоступны.\n"
            f"Попробуй позже или обратись к ним напрямую.",
            parse_mode=ParseMode.HTML
        )

# --- Все остальные команды (оставляем как есть, но можно добавить смайликов) ---
# Здесь нужно вставить все остальные функции команд из твоего кода:
# welcome_new_member, mute, unmute, ban, warn, setname, giveaccess, setprefix,
# nlist, grank, gnick, ranks, warns, bans, mutelist, logs, all_command,
# wedding, weddings_list, top, me_action, try_action, kiss, slap, hug,
# profile, info, check_user, online, wish, update_last_online, check_message_rules

# --- ЗАПУСК С ЗАГЛУШКОЙ ДЛЯ RENDER ---
import threading
from flask import Flask
import time

# Создаем простой Flask сервер для Render
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

# Запускаем Flask в отдельном потоке
flask_thread = threading.Thread(target=run_flask)
flask_thread.daemon = True
flask_thread.start()

# Основной запуск бота
async def main():
    print("🚀 Бот запускается...")
    
    # Инициализируем БД
    await init_db()
    print("✅ БД загружена")
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики (все команды)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("who", who_command))
    application.add_handler(CommandHandler("gay", gay))
    application.add_handler(CommandHandler("clown", clown))
    application.add_handler(CommandHandler("repplus", rep_plus))
    application.add_handler(CommandHandler("repminus", rep_minus))
    application.add_handler(CommandHandler("report", report))
    
    # Добавь сюда остальные обработчики из твоего кода
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
    
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, update_last_online), group=1)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_message_rules), group=2)
    
    print("✅ Обработчики зарегистрированы")
    
    # Запускаем polling
    print("🚀 Запускаем polling...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    print("🤖 Бот работает 24/7!")
    
    # Держим бота запущенным
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
