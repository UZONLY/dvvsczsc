import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import logging
import random
import string
from datetime import datetime, timedelta
from telebot.apihelper import ApiTelegramException

# Logging sozlash
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Bot token va dastlabki admin ID
BOT_TOKEN = '8317320020:AAH3ezJChgad0nDOc2vuCbNQmZCNKbZ4Cys'
BOT_USERNAME = 'kanekianimeuz_bot'
INITIAL_ADMIN_ID = 6526385624
ADMIN_CONTACTS = ['@Senpay_07', '@prostaShodiyor']

bot = telebot.TeleBot(BOT_TOKEN)

# Upload sessions
upload_sessions = {}
ad_sessions = {}
watching_sessions = {}

# Common genres
common_genres = ['Action', 'Adventure', 'Comedy', 'Drama', 'Fantasy']

# Database ulanish
def get_db_connection():
    conn = sqlite3.connect('anime_bot.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# Database boshlash
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)')
    cursor.execute('CREATE TABLE IF NOT EXISTS animes (code INTEGER PRIMARY KEY, name TEXT DEFAULT "Noma\'lum Anime", episodes TEXT, status TEXT, quality TEXT, genres TEXT, referral_required INTEGER DEFAULT 0, premium_only INTEGER DEFAULT 0, views INTEGER DEFAULT 0, poster TEXT DEFAULT NULL, half_referral_required INTEGER DEFAULT 0)')
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, search_count INTEGER DEFAULT 0, username TEXT, premium_until TEXT DEFAULT NULL, referred_by INTEGER DEFAULT NULL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS anime_referrals (user_id INTEGER, anime_code INTEGER, referral_count INTEGER DEFAULT 0, PRIMARY KEY (user_id, anime_code))')
    cursor.execute('CREATE TABLE IF NOT EXISTS promo_codes (code TEXT PRIMARY KEY, used_by INTEGER DEFAULT NULL, created_at TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    for column, col_type in [('status', 'TEXT'), ('quality', 'TEXT'), ('genres', 'TEXT'), ('referral_required', 'INTEGER DEFAULT 0'), ('premium_only', 'INTEGER DEFAULT 0'), ('views', 'INTEGER DEFAULT 0'), ('poster', 'TEXT DEFAULT NULL'), ('half_referral_required', 'INTEGER DEFAULT 0')]:
        try:
            cursor.execute(f'ALTER TABLE animes ADD COLUMN {column} {col_type}')
        except sqlite3.OperationalError as e:
            if 'duplicate column name' not in str(e):
                logging.error(f"{column} ustunini qo'shishda xatolik: {e}")
    try:
        cursor.execute('ALTER TABLE animes ADD COLUMN name TEXT DEFAULT "Noma\'lum Anime"')
    except sqlite3.OperationalError as e:
        if 'duplicate column name' not in str(e):
            logging.error(f"name ustunini qo'shishda xatolik: {e}")
    for column, col_type in [('username', 'TEXT'), ('premium_until', 'TEXT DEFAULT NULL'), ('referred_by', 'INTEGER DEFAULT NULL')]:
        try:
            cursor.execute(f'ALTER TABLE users ADD COLUMN {column} {col_type}')
        except sqlite3.OperationalError as e:
            if 'duplicate column name' not in str(e):
                logging.error(f"{column} ustunini qo'shishda xatolik: {e}")
    cursor.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (INITIAL_ADMIN_ID,))
    cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('subscription_channels', ''))
    conn.commit()
    conn.close()
    logging.info("Database muvaffaqiyatli boshlandi!")

init_db()

# Majburiy obuna kanallarini olish
def get_subscription_channels():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', ('subscription_channels',))
    result = cursor.fetchone()
    conn.close()
    return result['value'].split(',') if result and result['value'] else []

# Majburiy obuna kanallarini yangilash
def update_subscription_channels(channels):
    value = ','.join(channels)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('subscription_channels', value))
    conn.commit()
    conn.close()

# Majburiy obuna tekshirish
def is_subscribed(user_id):
    channels = get_subscription_channels()
    if not channels:
        return True  # Agar majburiy obuna bo'lmasa, har doim True
    for channel in channels:
        try:
            member = bot.get_chat_member(channel, user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        except Exception as e:
            logging.error(f"Obuna tekshirishda xatolik {channel}: {e}")
            return False
    return True

# Premium tekshirish
def is_premium(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT premium_until FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result and result['premium_until']:
        try:
            premium_until = datetime.fromisoformat(result['premium_until'])
            return premium_until > datetime.now()
        except ValueError:
            return False
    return False

# Yordamchi funksiyalar
def is_admin(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM admins WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def get_main_keyboard(is_admin_user, is_premium_user):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton('🔍 Anime qidirish'), KeyboardButton('📋 Barcha animelar'))
    markup.add(KeyboardButton('📋 Profil'), KeyboardButton('💎 Bot premium'))
    markup.add(KeyboardButton('🏆 Top 10'))
    if is_admin_user:
        markup.add(KeyboardButton('🛠 Admin panel'))
    return markup

def get_main_inline_keyboard(is_admin_user, is_premium_user):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton('🔍 Anime qidirish', callback_data='search_anime'),
        InlineKeyboardButton('📋 Barcha animelar', callback_data='list_animes')
    )
    markup.add(
        InlineKeyboardButton('📋 Profil', callback_data='profile'),
        InlineKeyboardButton('💎 Bot premium', callback_data='premium')
    )
    markup.add(InlineKeyboardButton('🏆 Top 10', callback_data='top10'))
    if is_admin_user:
        markup.add(InlineKeyboardButton('🛠 Admin panel', callback_data='admin_panel'))
    return markup

def get_admin_keyboard(is_initial_admin=False):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton('➕ Anime qo\'shish'), KeyboardButton('📋 Barcha animelar'))
    markup.add(KeyboardButton('🆕 Admin qo\'shish'), KeyboardButton('📢 Reklama yuborish'))
    markup.add(KeyboardButton('🔑 Premium promo yaratish'), KeyboardButton('📊 Bot statistikasi'))
    markup.add(KeyboardButton('🏆 Eng aktiv foydalanuvchilar'), KeyboardButton('🔙 Orqaga'))
    markup.add(KeyboardButton('🔍 Anime tahlil qilish'), KeyboardButton('📢 Majburiy obuna sozlamalari'))
    if is_initial_admin:
        markup.add(KeyboardButton('🗑 Admin o\'chirish'))
    return markup

def get_back_keyboard():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton('🔙 Orqaga', callback_data='back_to_main'))
    return markup

def get_finish_upload_keyboard(user_id):
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton('📼 Video yuklashni tugatish', callback_data=f'finish_upload_{user_id}'))
    return markup

def get_subscription_keyboard():
    channels = get_subscription_channels()
    markup = InlineKeyboardMarkup(row_width=1)
    for channel in channels:
        markup.add(InlineKeyboardButton('📢 Kanalga obuna bo\'lish', url=f'https://t.me/{channel[1:]}'))
    markup.add(InlineKeyboardButton('✅ Tekshirish', callback_data='check_subscription'))
    return markup

def get_search_type_inline_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton('🗨 Anime nomi orqali', callback_data='search_name'),
        InlineKeyboardButton('🎭 Janr orqali', callback_data='search_genre')
    )
    markup.add(
        InlineKeyboardButton('🎲 Tasodifiy anime', callback_data='search_random'),
        InlineKeyboardButton('📌 Kod orqali', callback_data='search_code')
    )
    markup.add(
        InlineKeyboardButton('👁 Eng ko\'p ko\'rilgan', callback_data='search_top'),
        InlineKeyboardButton('🔙 Orqaga', callback_data='back_to_main')
    )
    return markup

def get_status_keyboard(user_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton('Tugallangan', callback_data=f'set_status_Tugallangan_{user_id}'),
        InlineKeyboardButton('Davom etmoqda', callback_data=f'set_status_Davom etmoqda_{user_id}')
    )
    return markup

def get_quality_keyboard(user_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton('HD', callback_data=f'set_quality_HD_{user_id}'),
        InlineKeyboardButton('SD', callback_data=f'set_quality_SD_{user_id}')
    )
    return markup

def get_genres_keyboard(user_id):
    markup = InlineKeyboardMarkup(row_width=2)
    for genre in common_genres:
        markup.add(InlineKeyboardButton(genre, callback_data=f'add_genre_{genre}_{user_id}'))
    markup.add(InlineKeyboardButton('Tugatish', callback_data=f'finish_genres_{user_id}'))
    return markup

def get_yes_no_keyboard(user_id, field):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton('Ha', callback_data=f'set_{field}_yes_{user_id}'),
        InlineKeyboardButton('Yo\'q', callback_data=f'set_{field}_no_{user_id}')
    )
    return markup

def get_num_keyboard(user_id, field):
    markup = InlineKeyboardMarkup(row_width=3)
    for i in range(1, 6):
        markup.add(InlineKeyboardButton(str(i), callback_data=f'set_{field}_{i}_{user_id}'))
    return markup

def get_premium_keyboard(user_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton('Ha', callback_data=f'set_premium_1_{user_id}'),
        InlineKeyboardButton('Yo\'q', callback_data=f'set_premium_0_{user_id}')
    )
    return markup

# Anime ni ko'rsatish
def show_anime(user_id, code):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT name, episodes, status, quality, genres, referral_required, premium_only, views, poster, half_referral_required FROM animes WHERE code = ?', (code,))
        result = cursor.fetchone()
        if result:
            logging.info(f"Found anime with code {code}")
            name = result['name'] or 'Noma\'lum Anime'
            status = result['status'] or 'Noma\'lum'
            quality = result['quality'] or 'Noma\'lum'
            genres = result['genres'] or 'Noma\'lum'
            views = result['views'] or 0
            referral_required = result['referral_required'] or 0
            premium_only = result['premium_only'] or 0
            half_referral_required = result['half_referral_required'] or 0
            poster = result['poster']
            episode_file_ids = result['episodes'].split(',') if result['episodes'] and result['episodes'].strip() else []
            episodes_count = len(episode_file_ids)

            # Views ni oshirish
            cursor.execute('UPDATE animes SET views = views + 1 WHERE code = ?', (code,))
            conn.commit()

            if premium_only == 1:
                if not is_premium(user_id):
                    try:
                        bot.send_message(user_id, "❌ Bu anime faqat premium foydalanuvchilar uchun mavjud.")
                    except ApiTelegramException as e:
                        if e.error_code == 403:
                            logging.warning(f"User {user_id} has blocked the bot.")
                        else:
                            raise e
                    conn.close()
                    return
            else:
                if not is_premium(user_id):
                    if not is_subscribed(user_id):
                        channels = get_subscription_channels()
                        if channels:
                            try:
                                channel_list = '\n'.join([f"- {channel}" for channel in channels])
                                bot.send_message(user_id, f"🚫 Quyidagi kanallarga obuna bo'ling:\n{channel_list}", reply_markup=get_subscription_keyboard())
                            except ApiTelegramException as e:
                                if e.error_code == 403:
                                    logging.warning(f"User {user_id} has blocked the bot.")
                                else:
                                    raise e
                            conn.close()
                            return
                    cursor.execute('SELECT referral_count FROM anime_referrals WHERE user_id = ? AND anime_code = ?', (user_id, code))
                    user_result = cursor.fetchone()
                    user_referrals = user_result['referral_count'] if user_result else 0
                    if referral_required > 0 and user_referrals < referral_required:
                        try:
                            bot.send_message(user_id, f"❌ Bu animeni ko'rish uchun {referral_required} ta do'st taklif qilishingiz kerak. Hozirgi referallaringiz: {user_referrals}")
                            bot.send_message(user_id, f"Referal havolasi: https://t.me/{BOT_USERNAME}?start=ref_{user_id}_{code}")
                        except ApiTelegramException as e:
                            if e.error_code == 403:
                                logging.warning(f"User {user_id} has blocked the bot.")
                            else:
                                raise e
                        conn.close()
                        return

            channels = get_subscription_channels()
            channel_text = ', '.join(channels) if channels else 'Yo\'q'
            msg = (
                f"🎬 {name}\n\n"
                f"- Qism: {episodes_count}\n"
                f"- Holati: {status}\n"
                f"- Sifat: {quality}\n"
                f"- Janri: {genres}\n"
                f"- Kanallar: {channel_text}\n"
                f"- Ko'rishlar soni: {views + 1}\n"
            )

            watch_markup = InlineKeyboardMarkup(row_width=1)
            watch_markup.add(InlineKeyboardButton('Tomosha qilish', callback_data=f'watch_up_to_1_{code}'))

            if poster:
                try:
                    bot.send_photo(user_id, poster, caption=msg, reply_markup=watch_markup)
                except ApiTelegramException as e:
                    if e.error_code == 403:
                        logging.warning(f"User {user_id} has blocked the bot.")
                    else:
                        raise e
            else:
                try:
                    bot.send_message(user_id, msg, reply_markup=watch_markup)
                except ApiTelegramException as e:
                    if e.error_code == 403:
                        logging.warning(f"User {user_id} has blocked the bot.")
                    else:
                        raise e

            cursor.execute('UPDATE users SET search_count = search_count + 1 WHERE user_id = ?', (user_id,))
            conn.commit()
        else:
            not_found_text = (
                f"😔 Kod {code} bo'yicha anime topilmadi.\n\n"
                "Mavjud kodlarni bilish uchun admin bilan bog'laning yoki yangi kodlar kutilmoqda!\n\n"
                "Boshqa kodni sinab ko'ring."
            )
            try:
                bot.send_message(user_id, not_found_text, reply_markup=get_back_keyboard())
            except ApiTelegramException as e:
                if e.error_code == 403:
                    logging.warning(f"User {user_id} has blocked the bot.")
                else:
                    raise e
    except Exception as e:
        logging.error(f"Anime ko'rsatishda xatolik: {e}")
        try:
            bot.send_message(user_id, "😔 Kutilmagan xatolik yuz berdi. Keyinroq urinib ko'ring.", reply_markup=get_back_keyboard())
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
    finally:
        conn.close()

# Start buyrug'i
@bot.message_handler(commands=['start'])
def start_handler(message):
    user_id = message.chat.id
    username = message.from_user.username or 'Nomalum'
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id, search_count, username) VALUES (?, ?, ?)', (user_id, 0, username))
    cursor.execute('UPDATE users SET username = ? WHERE user_id = ?', (username, user_id))
    args = message.text.split()
    if len(args) > 1 and args[1].startswith('ref_'):
        try:
            parts = args[1].split('_')
            referrer_id = int(parts[1])
            anime_code = int(parts[2]) if len(parts) > 2 else None
            if referrer_id != user_id:
                cursor.execute('SELECT referred_by FROM users WHERE user_id = ?', (user_id,))
                existing_referrer = cursor.fetchone()['referred_by']
                if existing_referrer is None:
                    cursor.execute('UPDATE users SET referred_by = ? WHERE user_id = ?', (referrer_id, user_id))
                    if anime_code:
                        cursor.execute('INSERT OR IGNORE INTO anime_referrals (user_id, anime_code, referral_count) VALUES (?, ?, 0)', (referrer_id, anime_code))
                        cursor.execute('UPDATE anime_referrals SET referral_count = referral_count + 1 WHERE user_id = ? AND anime_code = ?', (referrer_id, anime_code))
                    conn.commit()
                    try:
                        bot.send_message(referrer_id, f"✅ Yangi referal qo'shildi! Anime kodi: {anime_code if anime_code else 'Umumiy'}")
                    except ApiTelegramException as e:
                        if e.error_code == 403:
                            logging.warning(f"Referrer {referrer_id} has blocked the bot.")
                        else:
                            raise e
                else:
                    try:
                        bot.send_message(user_id, "❌ Siz allaqachon boshqa foydalanuvchi tomonidan taklif qilingansiz. Ikkinchi marta taklif qilish mumkin emas.")
                    except ApiTelegramException as e:
                        if e.error_code == 403:
                            logging.warning(f"User {user_id} has blocked the bot.")
                        else:
                            raise e
        except ValueError:
            pass
    conn.commit()
    conn.close()
    upload_sessions.pop(user_id, None)
    ad_sessions.pop(user_id, None)

    if not (is_subscribed(user_id) or is_premium(user_id)):
        channels = get_subscription_channels()
        if channels:
            try:
                channel_list = '\n'.join([f"- {channel}" for channel in channels])
                bot.send_message(user_id, f"🚫 Quyidagi kanallarga obuna bo'ling:\n{channel_list}", reply_markup=get_subscription_keyboard())
            except ApiTelegramException as e:
                if e.error_code == 403:
                    logging.warning(f"User {user_id} has blocked the bot.")
                else:
                    raise e
            return

    if len(args) > 1 and not args[1].startswith('ref_'):
        try:
            code = int(args[1])
            show_anime(user_id, code)
            return
        except ValueError:
            pass

    welcome_text = (
        "🌸 *Assalomu alaykum!* 🌸\n\n"
        "🎉 *Anime Bot*ga xush kelibsiz! Bu yerda siz sevimli animelaringizni kod bo'yicha topishingiz mumkin.\n"
        "Adminlar esa yangi animelarni qo'shishi va boshqarishi mumkin.\n\n"
        "Qanday yordam kerak? Quyidagi tugmalardan tanlang! ✨"
    )
    try:
        bot.send_message(user_id, welcome_text, parse_mode='Markdown', reply_markup=get_main_keyboard(is_admin(user_id), is_premium(user_id)))
    except ApiTelegramException as e:
        if e.error_code == 403:
            logging.warning(f"User {user_id} has blocked the bot.")
        else:
            raise e

# Profil funksiyasi
@bot.callback_query_handler(func=lambda call: call.data == 'profile')
@bot.message_handler(func=lambda message: message.text == '📋 Profil')
def profile_handler(message_or_call):
    if isinstance(message_or_call, telebot.types.CallbackQuery):
        user_id = message_or_call.from_user.id
        message = message_or_call.message
    else:
        user_id = message_or_call.chat.id
        message = message_or_call

    if not (is_subscribed(user_id) or is_premium(user_id)):
        channels = get_subscription_channels()
        if channels:
            try:
                channel_list = '\n'.join([f"- {channel}" for channel in channels])
                bot.send_message(user_id, f"🚫 Quyidagi kanallarga obuna bo'ling:\n{channel_list}", reply_markup=get_subscription_keyboard())
            except ApiTelegramException as e:
                if e.error_code == 403:
                    logging.warning(f"User {user_id} has blocked the bot.")
                else:
                    raise e
            return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT username, search_count, premium_until FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    cursor.execute('SELECT SUM(referral_count) as total_referrals FROM anime_referrals WHERE user_id = ?', (user_id,))
    referrals = cursor.fetchone()['total_referrals'] or 0
    conn.close()

    username = user['username'] or 'Nomalum'
    search_count = user['search_count'] or 0
    premium_status = "Faol" if is_premium(user_id) else "Faol emas"
    premium_until = user['premium_until'] or "Hech qachon"

    profile_text = (
        f"📋 *Sizning profilingiz* 📋\n\n"
        f"👤 *Foydalanuvchi:* @{username}\n"
        f"🔍 *Qidiruvlar soni:* {search_count}\n"
        f"💎 *Premium holati:* {premium_status}\n"
        f"⏰ *Premium muddati:* {premium_until}\n"
        f"🤝 *Referallar soni:* {referrals}\n\n"
        f"Yana nima qilmoqchisiz?"
    )
    try:
        bot.send_message(user_id, profile_text, parse_mode='Markdown', reply_markup=get_main_keyboard(is_admin(user_id), is_premium(user_id)))
    except ApiTelegramException as e:
        if e.error_code == 400 and "can't parse entities" in str(e):
            logging.warning(f"Markdown parsing error in profile_handler: {e}")
            bot.send_message(user_id, profile_text.replace('*', '').replace('_', '').replace('`', ''), reply_markup=get_main_keyboard(is_admin(user_id), is_premium(user_id)))
        elif e.error_code == 403:
            logging.warning(f"User {user_id} has blocked the bot.")
        else:
            raise e

# Admin panel funksiyasi
@bot.callback_query_handler(func=lambda call: call.data == 'admin_panel')
@bot.message_handler(func=lambda message: message.text == '🛠 Admin panel')
def admin_panel_handler(message_or_call):
    if isinstance(message_or_call, telebot.types.CallbackQuery):
        user_id = message_or_call.from_user.id
        message = message_or_call.message
    else:
        user_id = message_or_call.chat.id
        message = message_or_call
    if not is_admin(user_id):
        try:
            bot.send_message(user_id, "❌ Sizda admin paneliga kirish huquqi yo'q.")
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
        return
    is_initial = user_id == INITIAL_ADMIN_ID
    try:
        bot.send_message(user_id, "🛠 *Admin panel* 🛠\n\nQuyidagi amallardan birini tanlang:", parse_mode='Markdown', reply_markup=get_admin_keyboard(is_initial))
    except ApiTelegramException as e:
        if e.error_code == 403:
            logging.warning(f"User {user_id} has blocked the bot.")
        else:
            raise e

# Premium funksiyasi
@bot.callback_query_handler(func=lambda call: call.data == 'premium')
@bot.message_handler(func=lambda message: message.text == '💎 Bot premium')
def premium_handler(message_or_call):
    if isinstance(message_or_call, telebot.types.CallbackQuery):
        user_id = message_or_call.from_user.id
        message = message_or_call.message
    else:
        user_id = message_or_call.chat.id
        message = message_or_call
    if not (is_subscribed(user_id) or is_premium(user_id)):
        channels = get_subscription_channels()
        if channels:
            try:
                channel_list = '\n'.join([f"- {channel}" for channel in channels])
                bot.send_message(user_id, f"🚫 Quyidagi kanallarga obuna bo'ling:\n{channel_list}", reply_markup=get_subscription_keyboard())
            except ApiTelegramException as e:
                if e.error_code == 403:
                    logging.warning(f"User {user_id} has blocked the bot.")
                else:
                    raise e
            return
    if is_premium(user_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT premium_until FROM users WHERE user_id = ?', (user_id,))
        premium_until = cursor.fetchone()['premium_until']
        conn.close()
        try:
            bot.send_message(user_id, f"💎 Siz allaqachon premium obunachisiz!\nMuddati: {premium_until}", reply_markup=get_main_keyboard(is_admin(user_id), is_premium(user_id)))
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
    else:
        premium_text = (
            f"💎 *Bot Premium* 💎\n\n"
            f"Premium obuna sizga quyidagi imkoniyatlarni beradi:\n"
            f"- Kanal obunasiz ham anime ko'rish\n"
            f"- Maxsus premium animelarga kirish\n"
            f"- Qidiruv cheklovlarisiz foydalanish\n\n"
            f"Premium olish uchun promo-kodni kiriting yoki admin bilan bog'laning: {', '.join(ADMIN_CONTACTS)}\n\n"
            f"📌 Promo-kod kiritish uchun kodni yuboring:"
        )
        try:
            bot.send_message(user_id, premium_text, parse_mode='Markdown', reply_markup=get_main_keyboard(is_admin(user_id), is_premium(user_id)))
            bot.register_next_step_handler(message, process_promo_code)
        except ApiTelegramException as e:
            if e.error_code == 400 and "can't parse entities" in str(e):
                logging.warning(f"Markdown parsing error in premium_handler: {e}")
                bot.send_message(user_id, premium_text.replace('*', '').replace('_', '').replace('`', ''), reply_markup=get_main_keyboard(is_admin(user_id), is_premium(user_id)))
                bot.register_next_step_handler(message, process_promo_code)
            elif e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e

# Promo-kod qayta ishlash
def process_promo_code(message):
    user_id = message.chat.id
    code = message.text.strip()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT used_by FROM promo_codes WHERE code = ?', (code,))
    result = cursor.fetchone()
    if result and result['used_by'] is None:
        premium_until = (datetime.now() + timedelta(days=30)).isoformat()
        cursor.execute('UPDATE promo_codes SET used_by = ? WHERE code = ?', (user_id, code))
        cursor.execute('UPDATE users SET premium_until = ? WHERE user_id = ?', (premium_until, user_id))
        conn.commit()
        try:
            bot.send_message(user_id, f"✅ Promo-kod faollashtirildi! Premium holati 1 oyga ({premium_until}) uzaytirildi.", reply_markup=get_main_keyboard(is_admin(user_id), is_premium(user_id)))
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
    else:
        try:
            bot.send_message(user_id, "❌ Noto'g'ri yoki ishlatilgan promo-kod. Qaytadan urinib ko'ring yoki admin bilan bog'laning.", reply_markup=get_main_keyboard(is_admin(user_id), is_premium(user_id)))
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
    conn.close()

# Majburiy obuna sozlamalari
@bot.message_handler(func=lambda message: message.text == '📢 Majburiy obuna sozlamalari')
def subscription_settings_handler(message):
    user_id = message.chat.id
    if not is_admin(user_id):
        try:
            bot.send_message(user_id, "❌ Sizda majburiy obuna sozlamalariga kirish huquqi yo'q.")
            return
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
    current_channels = get_subscription_channels()
    markup = InlineKeyboardMarkup(row_width=1)
    if len(current_channels) < 10:
        markup.add(InlineKeyboardButton('➕ Yangi kanal qo\'shish', callback_data='add_subscription_channel'))
    for channel in current_channels:
        markup.add(InlineKeyboardButton(f'❌ O\'chirish: {channel}', callback_data=f'remove_subscription_channel_{channel}'))
    if current_channels:
        markup.add(InlineKeyboardButton('❌ Barchasini o\'chirish', callback_data='remove_all_subscription_channels'))
    markup.add(InlineKeyboardButton('🔙 Orqaga', callback_data='back_to_admin'))
    channel_list = '\n'.join(current_channels) if current_channels else 'Yo\'q'
    text = (
        f"📢 *Majburiy obuna sozlamalari* 🛠\n\n"
        f"Hozirgi kanallar (maks 10 ta):\n{channel_list}\n\n"
        f"Quyidagi amallardan birini tanlang:"
    )
    try:
        bot.send_message(user_id, text, parse_mode='Markdown', reply_markup=markup)
    except ApiTelegramException as e:
        if e.error_code == 400 and "can't parse entities" in str(e):
            logging.warning(f"Markdown parsing error in subscription_settings_handler: {e}")
            plain_text = (
                f"📢 Majburiy obuna sozlamalari 🛠\n\n"
                f"Hozirgi kanallar (maks 10 ta):\n{channel_list}\n\n"
                f"Quyidagi amallardan birini tanlang:"
            )
            bot.send_message(user_id, plain_text, reply_markup=markup)
        elif e.error_code == 403:
            logging.warning(f"User {user_id} has blocked the bot.")
        else:
            raise e

# Majburiy obuna callback
@bot.callback_query_handler(func=lambda call: call.data in ['add_subscription_channel', 'remove_all_subscription_channels', 'back_to_admin'] or call.data.startswith('remove_subscription_channel_'))
def subscription_settings_callback(call):
    user_id = call.from_user.id
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "❌ Sizda bu amalni bajarish huquqi yo'q.", show_alert=True)
        return
    if call.data == 'add_subscription_channel':
        try:
            bot.edit_message_text(
                "Yangi majburiy obuna kanali uchun @ bilan boshlanadigan kanal nomini kiriting (masalan, @ChannelName):",
                call.message.chat.id,
                call.message.message_id
            )
            bot.register_next_step_handler(call.message, process_add_subscription_channel)
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
    elif call.data.startswith('remove_subscription_channel_'):
        channel_to_remove = call.data.split('_', 3)[3]
        current_channels = get_subscription_channels()
        if channel_to_remove in current_channels:
            current_channels.remove(channel_to_remove)
            update_subscription_channels(current_channels)
            bot.answer_callback_query(call.id, f"✅ {channel_to_remove} kanali o'chirildi!", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "❌ Kanal topilmadi.", show_alert=True)
        # Refresh the message
        subscription_settings_handler(call.message)
    elif call.data == 'remove_all_subscription_channels':
        update_subscription_channels([])
        try:
            bot.edit_message_text(
                "✅ Barcha majburiy obuna kanallari o'chirildi!",
                call.message.chat.id,
                call.message.message_id
            )
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
    elif call.data == 'back_to_admin':
        try:
            bot.edit_message_text(
                "🛠 Admin panelga qaytdik!",
                call.message.chat.id,
                call.message.message_id
            )
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
    bot.answer_callback_query(call.id)

def process_add_subscription_channel(message):
    user_id = message.chat.id
    channel = message.text.strip()
    if not channel.startswith('@'):
        try:
            bot.send_message(user_id, "❌ Kanal nomi @ bilan boshlanishi kerak. Qaytadan kiriting:")
            bot.register_next_step_handler(message, process_add_subscription_channel)
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
        return
    current_channels = get_subscription_channels()
    if channel in current_channels:
        try:
            bot.send_message(user_id, "❌ Bu kanal allaqachon qo'shilgan. Boshqa kanal kiriting:")
            bot.register_next_step_handler(message, process_add_subscription_channel)
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
        return
    if len(current_channels) >= 10:
        try:
            bot.send_message(user_id, "❌ Maksimal 10 ta kanal qo'shish mumkin. Avval birontasini o'chiring.", reply_markup=get_admin_keyboard())
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
        return
    current_channels.append(channel)
    update_subscription_channels(current_channels)
    try:
        bot.send_message(user_id, f"✅ Majburiy obuna kanali qo'shildi: {channel}", reply_markup=get_admin_keyboard())
    except ApiTelegramException as e:
        if e.error_code == 403:
            logging.warning(f"User {user_id} has blocked the bot.")
        else:
            raise e

# Barcha animelar ro'yxati
@bot.callback_query_handler(func=lambda call: call.data == 'list_animes')
@bot.message_handler(func=lambda message: message.text == '📋 Barcha animelar')
def list_all_animes_handler(message_or_call):
    if isinstance(message_or_call, telebot.types.CallbackQuery):
        user_id = message_or_call.from_user.id
        message = message_or_call.message
    else:
        user_id = message_or_call.chat.id
        message = message_or_call
    if not (is_subscribed(user_id) or is_premium(user_id)):
        channels = get_subscription_channels()
        if channels:
            try:
                channel_list = '\n'.join([f"- {channel}" for channel in channels])
                bot.send_message(user_id, f"🚫 Quyidagi kanallarga obuna bo'ling:\n{channel_list}", reply_markup=get_subscription_keyboard())
            except ApiTelegramException as e:
                if e.error_code == 403:
                    logging.warning(f"User {user_id} has blocked the bot.")
                else:
                    raise e
            return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT code, name FROM animes')
    results = cursor.fetchall()
    conn.close()
    if not results:
        try:
            bot.send_message(user_id, "❌ Hozircha hech qanday anime yo'q.")
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
        return
    markup = InlineKeyboardMarkup(row_width=2)
    for res in results:
        markup.add(InlineKeyboardButton(res['name'], callback_data=f'show_{res["code"]}'))
    try:
        bot.send_message(user_id, "📋 Barcha animelar:", reply_markup=markup)
    except ApiTelegramException as e:
        if e.error_code == 403:
            logging.warning(f"User {user_id} has blocked the bot.")
        else:
            raise e

# Obuna tekshirish callback
@bot.callback_query_handler(func=lambda call: call.data == 'check_subscription')
def check_subscription_callback(call):
    user_id = call.from_user.id
    if is_subscribed(user_id) or is_premium(user_id):
        try:
            bot.edit_message_text(
                "✅ Obuna tasdiqlandi! Botdan foydalaning.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=get_main_inline_keyboard(is_admin(user_id), is_premium(user_id))
            )
            start_handler(call.message)
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
    else:
        bot.answer_callback_query(call.id, "🚫 Hali obuna bo'lmagansiz! Iltimos, obuna bo'ling.", show_alert=True)
    bot.answer_callback_query(call.id)

# Anime qidirish
@bot.callback_query_handler(func=lambda call: call.data == 'search_anime')
@bot.message_handler(func=lambda message: message.text == '🔍 Anime qidirish')
def search_anime_handler(message_or_call):
    if isinstance(message_or_call, telebot.types.CallbackQuery):
        user_id = message_or_call.from_user.id
        message = message_or_call.message
    else:
        user_id = message_or_call.chat.id
        message = message_or_call
    if not (is_subscribed(user_id) or is_premium(user_id)):
        channels = get_subscription_channels()
        if channels:
            try:
                channel_list = '\n'.join([f"- {channel}" for channel in channels])
                bot.send_message(user_id, f"🚫 Quyidagi kanallarga obuna bo'ling:\n{channel_list}", reply_markup=get_subscription_keyboard())
            except ApiTelegramException as e:
                if e.error_code == 403:
                    logging.warning(f"User {user_id} has blocked the bot.")
                else:
                    raise e
            return
    try:
        bot.send_message(user_id, "Qidiruv turkumini tanlang:", reply_markup=get_search_type_inline_keyboard())
    except ApiTelegramException as e:
        if e.error_code == 403:
            logging.warning(f"User {user_id} has blocked the bot.")
        else:
            raise e

# Qidiruv turlari callback
@bot.callback_query_handler(func=lambda call: call.data.startswith('search_'))
def search_type_callback(call):
    user_id = call.from_user.id
    data = call.data
    if data == 'search_code':
        try:
            bot.edit_message_text("Anime kodini kiriting:", call.message.chat.id, call.message.message_id)
            bot.register_next_step_handler(call.message, process_code)
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
    elif data == 'search_name':
        try:
            bot.edit_message_text("Anime nomini kiriting:", call.message.chat.id, call.message.message_id)
            bot.register_next_step_handler(call.message, process_name_search)
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
    elif data == 'search_genre':
        try:
            bot.edit_message_text("Janrni kiriting (masalan, Fantastik):", call.message.chat.id, call.message.message_id)
            bot.register_next_step_handler(call.message, process_genre_search)
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
    elif data == 'search_random':
        process_random_anime(call.message)
    elif data == 'search_top':
        top10_handler(call.message)
    bot.answer_callback_query(call.id)

# Kod bo'yicha qidirish
def process_code(message):
    user_id = message.chat.id
    try:
        code = int(message.text.strip())
        show_anime(user_id, code)
    except ValueError:
        bot.send_message(user_id, "❌ Noto'g'ri kod. Raqam kiriting.")

# Nomi bo'yicha qidirish
def process_name_search(message):
    user_id = message.chat.id
    name = message.text.strip()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT code, name FROM animes WHERE name LIKE ?', (f'%{name}%',))
    results = cursor.fetchall()
    conn.close()
    if not results:
        bot.send_message(user_id, "❌ Hech nima topilmadi.")
        return
    markup = InlineKeyboardMarkup(row_width=2)
    for res in results:
        markup.add(InlineKeyboardButton(res['name'], callback_data=f'show_{res["code"]}'))
    bot.send_message(user_id, "Topilgan animelar:", reply_markup=markup)

# Janr bo'yicha qidirish
def process_genre_search(message):
    user_id = message.chat.id
    genre = message.text.strip()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT code, name FROM animes WHERE genres LIKE ?', (f'%{genre}%',))
    results = cursor.fetchall()
    conn.close()
    if not results:
        bot.send_message(user_id, "❌ Hech nima topilmadi.")
        return
    markup = InlineKeyboardMarkup(row_width=2)
    for res in results:
        markup.add(InlineKeyboardButton(res['name'], callback_data=f'show_{res["code"]}'))
    bot.send_message(user_id, "Topilgan animelar:", reply_markup=markup)

# Tasodifiy anime
def process_random_anime(message):
    user_id = message.chat.id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT code FROM animes ORDER BY RANDOM() LIMIT 1')
    result = cursor.fetchone()
    conn.close()
    if result:
        code = result['code']
        show_anime(user_id, code)
    else:
        try:
            bot.send_message(user_id, "❌ Hech qanday anime topilmadi.")
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e

# Top 10 eng ko'p ko'rilgan animelar
@bot.callback_query_handler(func=lambda call: call.data == 'top10')
@bot.message_handler(func=lambda message: message.text == '🏆 Top 10')
def top10_handler(message_or_call):
    if isinstance(message_or_call, telebot.types.CallbackQuery):
        user_id = message_or_call.from_user.id
        message = message_or_call.message
    else:
        user_id = message_or_call.chat.id
        message = message_or_call
    if not (is_subscribed(user_id) or is_premium(user_id)):
        channels = get_subscription_channels()
        if channels:
            try:
                channel_list = '\n'.join([f"- {channel}" for channel in channels])
                bot.send_message(user_id, f"🚫 Quyidagi kanallarga obuna bo'ling:\n{channel_list}", reply_markup=get_subscription_keyboard())
            except ApiTelegramException as e:
                if e.error_code == 403:
                    logging.warning(f"User {user_id} has blocked the bot.")
                else:
                    raise e
            return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT code, name, views FROM animes ORDER BY views DESC LIMIT 10')
    tops = cursor.fetchall()
    conn.close()
    if not tops:
        try:
            bot.send_message(user_id, "🏆 Hozircha top animelar yo'q.")
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
        return
    markup = InlineKeyboardMarkup(row_width=2)
    for top in tops:
        markup.add(InlineKeyboardButton(top['name'], callback_data=f'show_{top["code"]}'))
    try:
        bot.send_message(user_id, "🏆 Eng ko'p ko'rilgan animelar:", reply_markup=markup)
    except ApiTelegramException as e:
        if e.error_code == 403:
            logging.warning(f"User {user_id} has blocked the bot.")
        else:
            raise e

# Anime qo'shish
@bot.message_handler(func=lambda message: message.text == '➕ Anime qo\'shish')
def add_anime_handler(message):
    user_id = message.chat.id
    if not is_admin(user_id):
        return
    try:
        bot.send_message(user_id, "Yangi anime uchun kod kiriting (unik raqam):")
        bot.register_next_step_handler(message, process_add_code)
    except ApiTelegramException as e:
        if e.error_code == 403:
            logging.warning(f"User {user_id} has blocked the bot.")
        else:
            raise e

def process_add_code(message):
    user_id = message.chat.id
    try:
        code = int(message.text.strip())
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT code FROM animes WHERE code = ?', (code,))
        if cursor.fetchone():
            try:
                bot.send_message(user_id, "❌ Bu kod allaqachon mavjud. Boshqa kod kiriting.")
                bot.register_next_step_handler(message, process_add_code)
            except ApiTelegramException as e:
                if e.error_code == 403:
                    logging.warning(f"User {user_id} has blocked the bot.")
                else:
                    raise e
            conn.close()
            return
        conn.close()
        upload_sessions[user_id] = {'code': code, 'episode_file_ids': [], 'genres_list': []}
        try:
            bot.send_message(user_id, "Anime nomini kiriting:")
            bot.register_next_step_handler(message, process_add_name)
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
    except ValueError:
        try:
            bot.send_message(user_id, "❌ Noto'g'ri kod. Raqam kiriting.")
            bot.register_next_step_handler(message, process_add_code)
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e

def process_add_name(message):
    user_id = message.chat.id
    upload_sessions[user_id]['name'] = message.text.strip()
    try:
        bot.send_message(user_id, "Holatini tanlang:", reply_markup=get_status_keyboard(user_id))
    except ApiTelegramException as e:
        if e.error_code == 403:
            logging.warning(f"User {user_id} has blocked the bot.")
        else:
            raise e

@bot.callback_query_handler(func=lambda call: call.data.startswith('set_status_'))
def set_status_callback(call):
    user_id = call.from_user.id
    if user_id in upload_sessions:
        status = call.data.split('_')[2]
        upload_sessions[user_id]['status'] = status
        try:
            bot.edit_message_text("Sifatini tanlang:", call.message.chat.id, call.message.message_id, reply_markup=get_quality_keyboard(user_id))
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('set_quality_'))
def set_quality_callback(call):
    user_id = call.from_user.id
    if user_id in upload_sessions:
        quality = call.data.split('_')[2]
        upload_sessions[user_id]['quality'] = quality
        try:
            bot.edit_message_text("Janrlarini tanlang (bir nechtasini tanlashingiz mumkin):", call.message.chat.id, call.message.message_id, reply_markup=get_genres_keyboard(user_id))
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('add_genre_'))
def add_genre_callback(call):
    user_id = call.from_user.id
    genre = call.data.split('_')[2]
    if user_id in upload_sessions:
        if 'genres_list' not in upload_sessions[user_id]:
            upload_sessions[user_id]['genres_list'] = []
        if genre not in upload_sessions[user_id]['genres_list']:
            upload_sessions[user_id]['genres_list'].append(genre)
        current_genres = ', '.join(upload_sessions[user_id]['genres_list'])
        try:
            bot.edit_message_text(f"Tanlangan janrlar: {current_genres if current_genres else 'Hech qaysi'}\nJanrlarini tanlang:", call.message.chat.id, call.message.message_id, reply_markup=get_genres_keyboard(user_id))
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('finish_genres_'))
def finish_genres_callback(call):
    user_id = call.from_user.id
    if user_id in upload_sessions:
        if 'genres_list' in upload_sessions[user_id]:
            upload_sessions[user_id]['genres'] = ', '.join(upload_sessions[user_id]['genres_list'])
        else:
            upload_sessions[user_id]['genres'] = ''
        try:
            bot.edit_message_text("Anime ko'rish uchun referal talab qilinsinmi?", call.message.chat.id, call.message.message_id, reply_markup=get_yes_no_keyboard(user_id, 'ref'))
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('set_ref_') or call.data.startswith('set_half_ref_'))
def set_yes_no_callback(call):
    user_id = call.from_user.id
    parts = call.data.split('_')
    field = parts[1]
    choice = parts[2]
    if field == 'half':
        field = 'half_ref'
        choice = parts[3]
    if choice == 'no':
        if field == 'ref':
            upload_sessions[user_id]['referral_required'] = 0
            next_text = "Qolgan qismlarni ko'rish uchun referal talab qilinsinmi?"
            next_markup = get_yes_no_keyboard(user_id, 'half_ref')
        elif field == 'half_ref':
            upload_sessions[user_id]['half_referral_required'] = 0
            next_text = "Premium faqat bo'lsinmi?"
            next_markup = get_premium_keyboard(user_id)
        try:
            bot.edit_message_text(next_text, call.message.chat.id, call.message.message_id, reply_markup=next_markup)
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
    elif choice == 'yes':
        if field == 'ref':
            next_text = "Necha ta referal talab qilinsin (anime ko'rish uchun)?"
            next_field = 'referral_required'
        elif field == 'half_ref':
            next_text = "Necha ta referal talab qilinsin (qolgan qismlar uchun)?"
            next_field = 'half_referral_required'
        try:
            bot.edit_message_text(next_text, call.message.chat.id, call.message.message_id, reply_markup=get_num_keyboard(user_id, next_field))
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('set_referral_required_') or call.data.startswith('set_half_referral_required_'))
def set_num_callback(call):
    user_id = call.from_user.id
    parts = call.data.split('_')
    if parts[1] == 'half':
        field = '_'.join(parts[1:4])  # half_referral_required
        num_index = 4
    else:
        field = '_'.join(parts[1:3])  # referral_required
        num_index = 3
    num = int(parts[num_index])
    upload_sessions[user_id][field] = num
    if field == 'referral_required':
        next_text = "Qolgan qismlarni ko'rish uchun referal talab qilinsinmi?"
        next_markup = get_yes_no_keyboard(user_id, 'half_ref')
    elif field == 'half_referral_required':
        next_text = "Premium faqat bo'lsinmi?"
        next_markup = get_premium_keyboard(user_id)
    try:
        bot.edit_message_text(next_text, call.message.chat.id, call.message.message_id, reply_markup=next_markup)
    except ApiTelegramException as e:
        if e.error_code == 403:
            logging.warning(f"User {user_id} has blocked the bot.")
        else:
            raise e
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('set_premium_'))
def set_premium_callback(call):
    user_id = call.from_user.id
    if user_id in upload_sessions:
        premium = int(call.data.split('_')[2])
        upload_sessions[user_id]['premium_only'] = premium
        try:
            bot.edit_message_text("Anime rasmini (poster) yuboring:", call.message.chat.id, call.message.message_id)
            bot.register_next_step_handler(call.message, process_add_poster)
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
    bot.answer_callback_query(call.id)

def process_add_poster(message):
    user_id = message.chat.id
    if message.photo:
        poster_id = message.photo[-1].file_id
        upload_sessions[user_id]['poster'] = poster_id
        try:
            bot.send_message(user_id, "Ma'lumotlar saqlandi. Endi qismlarni (videolarni) yuboring. Yuklab bo'lgach, tugatish tugmasini bosing.", reply_markup=get_finish_upload_keyboard(user_id))
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
    else:
        try:
            bot.send_message(user_id, "❌ Iltimos, rasm yuboring. Qaytadan urinib ko'ring.")
            bot.register_next_step_handler(message, process_add_poster)
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e

# Anime tahlil qilish
@bot.message_handler(func=lambda message: message.text == '🔍 Anime tahlil qilish')
def analyze_anime_handler(message):
    user_id = message.chat.id
    if not is_admin(user_id):
        return
    try:
        bot.send_message(user_id, "Tahlil qilish uchun anime kodini kiriting:")
        bot.register_next_step_handler(message, process_analyze_code)
    except ApiTelegramException as e:
        if e.error_code == 403:
            logging.warning(f"User {user_id} has blocked the bot.")
        else:
            raise e

def process_analyze_code(message):
    user_id = message.chat.id
    try:
        code = int(message.text.strip())
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM animes WHERE code = ?', (code,))
        result = cursor.fetchone()
        conn.close()
        if result:
            episodes_count = len(result['episodes'].split(',')) if result['episodes'] else 0
            text = f"Anime tahlili:\n\nNomi: {result['name']}\nQismlar soni: {episodes_count}\nHolati: {result['status']}\nSifat: {result['quality']}\nJanri: {result['genres']}\nKo'rishlar: {result['views']}\nReferal talab (anime): {result['referral_required']}\nReferal talab (qolgan qismlar): {result['half_referral_required']}\n"
            bot.send_message(user_id, text)
            upload_sessions[user_id] = {
                'code': code,
                'name': result['name'],
                'status': result['status'],
                'quality': result['quality'],
                'genres': result['genres'],
                'referral_required': result['referral_required'],
                'half_referral_required': result['half_referral_required'],
                'premium_only': result['premium_only'],
                'poster': result['poster'],
                'episode_file_ids': result['episodes'].split(',') if result['episodes'] else [],
                'genres_list': result['genres'].split(', ') if result['genres'] else []
            }
            bot.send_message(user_id, "Qo'shimcha qismlar qo'shishingiz mumkin. Yangi videolarni yuboring yoki tugatish uchun tugmani bosing.", reply_markup=get_finish_upload_keyboard(user_id))
        else:
            bot.send_message(user_id, "❌ Anime topilmadi.")
    except ValueError:
        bot.send_message(user_id, "❌ Noto'g'ri kod.")

# Video yuklash (birdaniga ko'p qism qo'llab-quvvatlash)
@bot.message_handler(content_types=['video'])
def process_video(message):
    user_id = message.chat.id
    if user_id in upload_sessions:
        file_id = message.video.file_id
        upload_sessions[user_id]['episode_file_ids'].append(file_id)
        current_count = len(upload_sessions[user_id]['episode_file_ids'])
        try:
            bot.send_message(user_id, f"✅ {current_count}-qism yuklandi! Yana video yuboring yoki tugatish uchun tugmani bosing.", reply_markup=get_finish_upload_keyboard(user_id))
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
    else:
        bot.send_message(user_id, "❌ Yuklash sessiyasi yo'q. Yangi anime qo'shing.")

# Video yuklashni tugatish callback
@bot.callback_query_handler(func=lambda call: call.data.startswith('finish_upload_'))
def finish_upload_callback(call):
    user_id = call.from_user.id
    try:
        session = upload_sessions.get(user_id)
        if not session:
            raise ValueError("Sessiya topilmadi.")

        code = session['code']
        name = session['name']
        status = session.get('status', 'Noma\'lum')
        quality = session.get('quality', 'Noma\'lum')
        genres = session.get('genres', 'Noma\'lum')
        referral_required = session.get('referral_required', 0)
        half_referral_required = session.get('half_referral_required', 0)
        premium_only = session.get('premium_only', 0)
        poster = session.get('poster', None)
        episode_file_ids = session['episode_file_ids']

        if not episode_file_ids:
            raise ValueError("Hech qanday video yuborilmadi.")

        episodes = ','.join(episode_file_ids)
        logging.info(f"Saving episodes for code {code}: {episodes}")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT OR REPLACE INTO animes (code, name, episodes, status, quality, genres, referral_required, half_referral_required, premium_only, poster) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (code, name, episodes, status, quality, genres, referral_required, half_referral_required, premium_only, poster)
        )
        conn.commit()
        cursor.execute('SELECT episodes FROM animes WHERE code = ?', (code,))
        result = cursor.fetchone()
        conn.close()

        episodes_count = len(result['episodes'].split(',')) if result and result['episodes'] else 0
        logging.info(f"Retrieved episodes count for code {code}: {episodes_count}")

        upload_sessions.pop(user_id, None)
        ad_sessions[user_id] = {
            'code': code,
            'name': name,
            'status': status,
            'quality': quality,
            'genres': genres,
            'episodes_count': episodes_count
        }

        if result:
            success_text = (
                f"🎉 *Anime muvaffaqiyatli qo'shildi!* ✅\n\n"
                f"📌 *Nomi:* {name}\n"
                f"🔢 *Kodi:* {code}\n"
                f"📺 *Qismlar soni:* {episodes_count}\n"
                f"- Holati: {status}\n"
                f"- Sifat: {quality}\n"
                f"- Janri: {genres}\n"
                f"- Referal talab (anime): {referral_required}\n"
                f"- Referal talab (qolgan qismlar): {half_referral_required}\n"
                f"- Premium faqat: {'Ha' if premium_only else 'Yo\'q'}\n\n"
                f"Endi reklama uchun rasm yuboring! ✨"
            )
            try:
                bot.edit_message_text(
                    success_text,
                    user_id,
                    call.message.message_id,
                    parse_mode='Markdown'
                )
                bot.register_next_step_handler(call.message, lambda m: process_ad_photo(m, user_id))
            except ApiTelegramException as e:
                if e.error_code == 400 and "can't parse entities" in str(e):
                    logging.warning(f"Markdown parsing error in finish_upload: {e}")
                    bot.edit_message_text(
                        success_text.replace('*', '').replace('_', '').replace('`', ''),
                        user_id,
                        call.message.message_id
                    )
                    bot.register_next_step_handler(call.message, lambda m: process_ad_photo(m, user_id))
                elif e.error_code == 403:
                    logging.warning(f"User {user_id} has blocked the bot.")
                else:
                    raise e
        else:
            raise Exception("Bazaga saqlashda xatolik yuz berdi.")
    except Exception as e:
        logging.error(f"Video yuklashni tugatishda xatolik: {str(e)}")
        try:
            bot.edit_message_text(
                f"😔 Xatolik yuz berdi: {str(e)}. Iltimos, qaytadan boshlang (/start).",
                user_id,
                call.message.message_id,
                reply_markup=get_back_keyboard()
            )
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
    bot.answer_callback_query(call.id)

# Reklama rasmini qayta ishlash
def process_ad_photo(message, user_id):
    if message.photo:
        photo_id = message.photo[-1].file_id
        ad_sessions[user_id]['photo_id'] = photo_id

        session = ad_sessions[user_id]
        name = session['name']
        episodes_count = session['episodes_count']
        status = session['status']
        quality = session['quality']
        genres = session['genres']
        code = session['code']

        caption = (
            f"{name}\n\n"
            f"- Qism: {episodes_count}\n"
            f"- Holati: {status}\n"
            f"- Sifat: {quality}\n"
            f"- Janri: {genres}\n"
            f"- Kanallar: {', '.join(get_subscription_channels()) or 'Yo\'q'}"
        )

        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton('Tomosha qilish', url=f'https://t.me/{BOT_USERNAME}?start={code}'))

        channels = get_subscription_channels()
        if not channels:
            try:
                bot.send_message(user_id, "❌ Reklama yuborish uchun hech qanday kanal sozlanmagan. Iltimos, majburiy obuna kanallarini sozlang.", reply_markup=get_admin_keyboard())
                ad_sessions.pop(user_id, None)
                return
            except ApiTelegramException as e:
                logging.error(f"Xabar yuborishda xatolik: {e}")
                return

        sent_channels = []
        failed_channels = []
        for channel in channels:
            try:
                bot.send_photo(channel, photo_id, caption=caption, reply_markup=markup)
                sent_channels.append(channel)
            except ApiTelegramException as e:
                logging.error(f"Reklama {channel} kanaliga yuborishda xatolik: {e}")
                failed_channels.append(channel)
                if e.error_code == 403:
                    logging.warning(f"Bot {channel} kanalida ruxsatga ega emas.")
                elif e.error_code == 400 and "can't parse entities" in str(e):
                    try:
                        bot.send_photo(channel, photo_id, caption=caption.replace('*', '').replace('_', '').replace('`', ''), reply_markup=markup)
                        sent_channels.append(channel)
                    except ApiTelegramException as e2:
                        logging.error(f"Markdownsiz reklama yuborishda xatolik: {e2}")
                        failed_channels.append(channel)

        result_text = f"✅ Reklama yuborildi: {', '.join(sent_channels) or 'Hech qaysi'}\n"
        if failed_channels:
            result_text += f"❌ Yuborilmadi: {', '.join(failed_channels)}\n"
        result_text += "Admin panelga qaytish uchun tugmalardan foydalaning."

        try:
            bot.send_message(user_id, result_text, reply_markup=get_admin_keyboard())
        except ApiTelegramException as e:
            logging.error(f"Admin {user_id} ga xabar yuborishda xatolik: {e}")

        ad_sessions.pop(user_id, None)
    else:
        try:
            bot.send_message(user_id, "❌ Iltimos, rasm yuboring (photo fayl). Qaytadan urinib ko'ring.")
            bot.register_next_step_handler(message, lambda m: process_ad_photo(m, user_id))
        except ApiTelegramException as e:
            logging.error(f"Rasm so'rovida xatolik: {e}")

# Admin qo'shish
@bot.message_handler(func=lambda message: message.text == '🆕 Admin qo\'shish')
def add_admin_handler(message):
    user_id = message.chat.id
    if not is_admin(user_id):
        return
    admin_add_text = (
        "🆕 *Yangi admin qo'shish* 👤\n\n"
        "Yangi adminning foydalanuvchi ID'sini kiriting:\n"
        "_ID-ni Telegram profilidan oling!_"
    )
    try:
        bot.send_message(user_id, admin_add_text, parse_mode='Markdown')
        bot.register_next_step_handler(message, process_add_admin_id)
    except ApiTelegramException as e:
        if e.error_code == 403:
            logging.warning(f"User {user_id} has blocked the bot.")
        else:
            raise e

def process_add_admin_id(message):
    user_id = message.chat.id
    try:
        new_admin_id = int(message.text.strip())
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (new_admin_id,))
        conn.commit()
        conn.close()
        success_text = f"✅ *Yangi admin qo'shildi!* ID: `{new_admin_id}`\n\nEndi u admin paneldan foydalanishi mumkin. 👑"
        try:
            bot.send_message(user_id, success_text, parse_mode='Markdown', reply_markup=get_admin_keyboard(user_id == INITIAL_ADMIN_ID))
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
    except ValueError:
        error_text = "❌ Noto'g'ri ID! Faqat raqam kiriting."
        try:
            bot.send_message(user_id, error_text, parse_mode='Markdown', reply_markup=get_admin_keyboard(user_id == INITIAL_ADMIN_ID))
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e

# Admin o'chirish
@bot.message_handler(func=lambda message: message.text == '🗑 Admin o\'chirish')
def remove_admin_handler(message):
    user_id = message.chat.id
    if user_id != INITIAL_ADMIN_ID:
        try:
            bot.send_message(user_id, "❌ Faqat bosh admin adminlarni o'chirishi mumkin.")
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM admins WHERE user_id != ?', (INITIAL_ADMIN_ID,))
    admins = cursor.fetchall()
    conn.close()
    if not admins:
        bot.send_message(user_id, "Hozircha boshqa adminlar yo'q.")
        return
    markup = InlineKeyboardMarkup(row_width=1)
    for admin in admins:
        markup.add(InlineKeyboardButton(f"O'chirish: {admin['user_id']}", callback_data=f'remove_admin_{admin["user_id"]}'))
    bot.send_message(user_id, "Adminlarni tanlang:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('remove_admin_'))
def remove_admin_callback(call):
    user_id = call.from_user.id
    if user_id != INITIAL_ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Faqat bosh admin adminlarni o'chirishi mumkin.", show_alert=True)
        return
    remove_id = int(call.data.split('_')[2])
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM admins WHERE user_id = ?', (remove_id,))
    conn.commit()
    conn.close()
    bot.answer_callback_query(call.id, f"✅ Admin o'chirildi: {remove_id}", show_alert=True)
    # Refresh list
    remove_admin_handler(call.message)

# Reklama yuborish
@bot.message_handler(func=lambda message: message.text == '📢 Reklama yuborish')
def broadcast_ad_handler(message):
    user_id = message.chat.id
    if not is_admin(user_id):
        return
    ad_text = (
        "📢 *Reklama yuborish* 📨\n\n"
        "Reklama xabarini kiriting (barcha foydalanuvchilarga yuboriladi):\n"
        "_Markdown formatidan foydalaning: *qalin*, _italik_, `kod`_"
    )
    try:
        bot.send_message(user_id, ad_text, parse_mode='Markdown')
        bot.register_next_step_handler(message, process_broadcast_message)
    except ApiTelegramException as e:
        if e.error_code == 403:
            logging.warning(f"User {user_id} has blocked the bot.")
        else:
            raise e

def process_broadcast_message(message):
    ad_text = message.text
    user_id = message.chat.id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    users = cursor.fetchall()
    conn.close()
    sent_count = 0
    failed_count = 0
    for user in users:
        try:
            bot.send_message(user['user_id'], ad_text, parse_mode='Markdown', reply_markup=get_main_keyboard(is_admin(user['user_id']), is_premium(user['user_id'])))
            sent_count += 1
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user['user_id']} has blocked the bot.")
                failed_count += 1
            elif e.error_code == 400 and "can't parse entities" in str(e):
                logging.warning(f"Markdown parsing error in broadcast: {e}")
                bot.send_message(user['user_id'], ad_text.replace('*', '').replace('_', '').replace('`', ''), reply_markup=get_main_keyboard(is_admin(user['user_id']), is_premium(user['user_id'])))
                sent_count += 1
            else:
                logging.error(f"Reklama yuborishda xatolik: {e}")
                failed_count += 1
    broadcast_text = (
        f"📢 *Reklama yuborildi!* ✅\n\n"
        f"✅ *Muvaffaqiyatli:* {sent_count} ta foydalanuvchi\n"
        f"❌ *Xato:* {failed_count} ta foydalanuvchi\n\n"
        "Rahmat, admin! 🌟"
    )
    try:
        bot.send_message(user_id, broadcast_text, parse_mode='Markdown', reply_markup=get_admin_keyboard(user_id == INITIAL_ADMIN_ID))
    except ApiTelegramException as e:
        if e.error_code == 403:
            logging.warning(f"User {user_id} has blocked the bot.")
        else:
            raise e

# Premium promo yaratish
@bot.message_handler(func=lambda message: message.text == '🔑 Premium promo yaratish')
def create_promo_handler(message):
    user_id = message.chat.id
    if not is_admin(user_id):
        return
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO promo_codes (code, created_at) VALUES (?, ?)', (code, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    try:
        bot.send_message(message.chat.id, f"✅ Yangi promo-kod yaratildi: {code}\n1 oy premium uchun.")
    except ApiTelegramException as e:
        if e.error_code == 403:
            logging.warning(f"User {user_id} has blocked the bot.")
        else:
            raise e

# Bot statistikasi
@bot.message_handler(func=lambda message: message.text == '📊 Bot statistikasi')
def bot_stats_handler(message):
    user_id = message.chat.id
    if not is_admin(user_id):
        try:
            bot.send_message(user_id, "❌ Sizda statistikani ko'rish huquqi yo'q.")
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as user_count FROM users')
    user_count = cursor.fetchone()['user_count']
    cursor.execute('SELECT COUNT(*) as anime_count FROM animes')
    anime_count = cursor.fetchone()['anime_count']
    cursor.execute('SELECT SUM(views) as total_views FROM animes')
    total_views = cursor.fetchone()['total_views'] or 0
    cursor.execute('SELECT COUNT(*) as premium_users FROM users WHERE premium_until > ?', (datetime.now().isoformat(),))
    premium_users = cursor.fetchone()['premium_users']
    conn.close()
    msg = (
        f"📊 *Bot Statistikasi*\n\n"
        f"👥 Foydalanuvchilar soni: {user_count}\n"
        f"🎬 Animelar soni: {anime_count}\n"
        f"👀 Umumiy ko'rishlar: {total_views}\n"
        f"💎 Premium foydalanuvchilar: {premium_users}"
    )
    try:
        bot.send_message(user_id, msg, parse_mode='Markdown', reply_markup=get_admin_keyboard(user_id == INITIAL_ADMIN_ID))
    except ApiTelegramException as e:
        if e.error_code == 403:
            logging.warning(f"User {user_id} has blocked the bot.")
        else:
            raise e

# Eng aktiv foydalanuvchilar
@bot.message_handler(func=lambda message: message.text == '🏆 Eng aktiv foydalanuvchilar')
def active_users_handler(message):
    user_id = message.chat.id
    if not is_admin(user_id):
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT username, SUM(referral_count) as total_referrals FROM anime_referrals ar JOIN users u ON ar.user_id = u.user_id GROUP BY ar.user_id ORDER BY total_referrals DESC LIMIT 10')
    tops = cursor.fetchall()
    conn.close()
    if not tops:
        try:
            bot.send_message(user_id, "🏆 Hozircha aktiv foydalanuvchilar yo'q.")
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
        return
    top_text = "🏆 *Eng aktiv foydalanuvchilar (referallar bo'yicha):* 🏆\n\n"
    for i, top in enumerate(tops, 1):
        username = top['username'] or 'Nomalum'
        escaped_username = username.replace('_', '\\_')
        top_text += f"{i}. @{escaped_username} - {top['total_referrals']} ta referal\n"
    try:
        bot.send_message(user_id, top_text, parse_mode='Markdown')
    except ApiTelegramException as e:
        if e.error_code == 400 and "can't parse entities" in str(e):
            logging.warning(f"Markdown parsing error in active_users: {e}")
            bot.send_message(user_id, top_text.replace('*', '').replace('_', '').replace('`', ''))
        elif e.error_code == 403:
            logging.warning(f"User {user_id} has blocked the bot.")
        else:
            raise e

# Orqaga tugmasi
@bot.message_handler(func=lambda message: message.text == '🔙 Orqaga')
def back_handler(message):
    user_id = message.chat.id
    upload_sessions.pop(user_id, None)
    ad_sessions.pop(user_id, None)
    try:
        bot.send_message(user_id, "🔙 Asosiy menyuga qaytdik! 🎉", reply_markup=get_main_keyboard(is_admin(user_id), is_premium(user_id)))
    except ApiTelegramException as e:
        if e.error_code == 403:
            logging.warning(f"User {user_id} has blocked the bot.")
        else:
            raise e

# Inline tugmalar uchun callback
@bot.callback_query_handler(func=lambda call: call.data == 'back_to_main')
def back_to_main_callback(call):
    user_id = call.from_user.id
    upload_sessions.pop(user_id, None)
    ad_sessions.pop(user_id, None)
    try:
        bot.edit_message_text(
            "🔙 Asosiy menyuga qaytdik! 🎉",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=get_main_inline_keyboard(is_admin(user_id), is_premium(user_id))
        )
    except ApiTelegramException as e:
        if e.error_code == 403:
            logging.warning(f"User {user_id} has blocked the bot.")
        else:
            raise e
    bot.answer_callback_query(call.id)

# Show anime callback
@bot.callback_query_handler(func=lambda call: call.data.startswith('show_'))
def show_anime_callback(call):
    user_id = call.from_user.id
    code = int(call.data.split('_')[1])
    show_anime(user_id, code)
    bot.answer_callback_query(call.id)

# Watch up to episode callback
@bot.callback_query_handler(func=lambda call: call.data.startswith('watch_up_to_'))
def watch_up_to_callback(call):
    user_id = call.from_user.id
    parts = call.data.split('_')
    ep = int(parts[3])
    code = int(parts[4])
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT episodes, name, half_referral_required FROM animes WHERE code = ?', (code,))
    result = cursor.fetchone()
    conn.close()
    if result:
        episode_file_ids = result['episodes'].split(',') if result['episodes'] else []
        name = result['name']
        half_referral_required = result['half_referral_required']
        half_point = len(episode_file_ids) // 2
        # Oldingi xabarlarni o'chirish
        if user_id in watching_sessions:
            for mid in watching_sessions[user_id].get('messages', []):
                try:
                    bot.delete_message(user_id, mid)
                except ApiTelegramException:
                    pass
        else:
            watching_sessions[user_id] = {}
        watching_sessions[user_id]['messages'] = []
        # Yangi qismlarni yuborish
        for i in range(1, ep + 1):
            if i <= len(episode_file_ids):
                if i > half_point and half_referral_required > 0 and not is_premium(user_id):
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute('SELECT referral_count FROM anime_referrals WHERE user_id = ? AND anime_code = ?', (user_id, code))
                    user_result = cursor.fetchone()
                    user_referrals = user_result['referral_count'] if user_result else 0
                    conn.close()
                    if user_referrals < half_referral_required:
                        try:
                            bot.send_message(user_id, f"❌ Qolgan qismlarni ko'rish uchun {half_referral_required} ta do'st taklif qilishingiz kerak. Hozirgi referallaringiz: {user_referrals}")
                            bot.send_message(user_id, f"Referal havolasi: https://t.me/{BOT_USERNAME}?start=ref_{user_id}_{code}")
                            return
                        except ApiTelegramException as e:
                            if e.error_code == 403:
                                logging.warning(f"User {user_id} has blocked the bot.")
                            else:
                                raise e
                file_id = episode_file_ids[i - 1].strip()
                try:
                    msg = bot.send_video(user_id, file_id, caption=f"📼 {i}-qism - {name}")
                    watching_sessions[user_id]['messages'].append(msg.message_id)
                except ApiTelegramException as e:
                    logging.error(f"Video yuborishda xatolik: {e}")
        # Keyingi qismlar uchun markup
        if ep < len(episode_file_ids):
            markup = InlineKeyboardMarkup(row_width=2)
            for j in range(ep + 1, len(episode_file_ids) + 1):
                markup.add(InlineKeyboardButton(f"{j}", callback_data=f'watch_up_to_{j}_{code}'))
            try:
                button_msg = bot.send_message(user_id, "Qolgan qismlar:", reply_markup=markup)
                watching_sessions[user_id]['messages'].append(button_msg.message_id)
            except ApiTelegramException as e:
                if e.error_code == 403:
                    logging.warning(f"User {user_id} has blocked the bot.")
                else:
                    raise e
        else:
            try:
                end_msg = bot.send_message(user_id, "✅ Anime tugadi!")
                watching_sessions[user_id]['messages'].append(end_msg.message_id)
            except ApiTelegramException as e:
                if e.error_code == 403:
                    logging.warning(f"User {user_id} has blocked the bot.")
                else:
                    raise e
    bot.answer_callback_query(call.id)

# Inline tugmalar uchun qo'shimcha callbacklar
@bot.callback_query_handler(func=lambda call: call.data in ['search_anime', 'list_animes', 'profile', 'premium', 'top10', 'admin_panel'])
def handle_main_menu_callbacks(call):
    user_id = call.from_user.id
    try:
        if call.data == 'search_anime':
            search_anime_handler(call)
        elif call.data == 'list_animes':
            list_all_animes_handler(call)
        elif call.data == 'profile':
            profile_handler(call)
        elif call.data == 'premium':
            premium_handler(call)
        elif call.data == 'top10':
            top10_handler(call)
        elif call.data == 'admin_panel':
            admin_panel_handler(call)
        try:
            bot.edit_message_text(
                "🔄 Amal bajarildi!",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=get_main_inline_keyboard(is_admin(user_id), is_premium(user_id))
            )
        except ApiTelegramException as e:
            if e.error_code == 403:
                logging.warning(f"User {user_id} has blocked the bot.")
            else:
                raise e
    except ApiTelegramException as e:
        if e.error_code == 403:
            logging.warning(f"User {user_id} has blocked the bot.")
        else:
            raise e
    bot.answer_callback_query(call.id)

# Noma'lum xabarlar
@bot.message_handler(func=lambda message: True)
def unknown_handler(message):
    user_id = message.chat.id
    if not (is_subscribed(user_id) or is_premium(user_id)):
        channels = get_subscription_channels()
        if channels:
            try:
                channel_list = '\n'.join([f"- {channel}" for channel in channels])
                bot.send_message(user_id, f"🚫 Quyidagi kanallarga obuna bo'ling:\n{channel_list}", reply_markup=get_subscription_keyboard())
            except ApiTelegramException as e:
                if e.error_code == 403:
                    logging.warning(f"User {user_id} has blocked the bot.")
                else:
                    raise e
        return
    unknown_text = (
        "🤔 Tushunmadim... Quyidagi tugmalardan foydalaning yoki /start buyrug'ini bosing!\n\n"
        "Yordam kerakmi? Admin bilan bog'laning. 💬"
    )
    try:
        bot.send_message(user_id, unknown_text, reply_markup=get_main_keyboard(is_admin(user_id), is_premium(user_id)))
    except ApiTelegramException as e:
        if e.error_code == 403:
            logging.warning(f"User {user_id} has blocked the bot.")
        else:
            raise e

# Botni ishga tushirish
if __name__ == '__main__':
    logging.info("Bot ishga tushdi... 🚀")
    try:
        bot.infinity_polling(none_stop=True)
    except Exception as e:
        logging.error(f"Polling xatoligi: {e}")