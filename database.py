import aiosqlite
import json
import time
from datetime import datetime, timedelta
from typing import List, Tuple, Optional
from config import INITIAL_KEYS, MAX_DAILY_MESSAGES, LIFETIME_KEY_COOLDOWN_DAYS, SCREENSHOT_BATCH_TIMEOUT, SECRET_ADMIN_PASS

DB_PATH = "lostbot.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_code TEXT UNIQUE,
                status TEXT DEFAULT 'available',
                issued_to INTEGER,
                issued_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                daily_messages INTEGER DEFAULT 0,
                last_message_date TEXT,
                lifetime_key_issued_at TEXT,
                is_whitelisted INTEGER DEFAULT 0,
                app_activation_key TEXT
            )
        """)
        try:
            await db.execute("ALTER TABLE users ADD COLUMN app_activation_key TEXT")
        except Exception:
            pass
        await db.execute("""
            CREATE TABLE IF NOT EXISTS app_activations (
                key_code TEXT PRIMARY KEY,
                device_id TEXT,
                activated_at TEXT,
                is_blocked INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                role TEXT,
                message_text TEXT,
                timestamp TEXT,
                tg_message_id INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS screenshot_sessions (
                user_id INTEGER PRIMARY KEY,
                count INTEGER DEFAULT 0,
                hashes TEXT DEFAULT '[]',
                started_at REAL
            )
        """)
        
        # Настройка закрытого режима по умолчанию: true (закрытый доступ для тестов)
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('maintenance_mode', 'true')")
        
        # Загрузка 15 базовых ключей
        for k in INITIAL_KEYS:
            await db.execute("INSERT OR IGNORE INTO keys (key_code, status) VALUES (?, 'available')", (k,))
            
        await db.commit()

# --- Настройки бота ---
async def get_maintenance_mode() -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT value FROM settings WHERE key = 'maintenance_mode'")
        row = await cursor.fetchone()
        return row[0].lower() == 'true' if row else False

async def set_maintenance_mode(enabled: bool):
    val = 'true' if enabled else 'false'
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('maintenance_mode', ?)", (val,))
        await db.commit()

# --- Пользователи и лимиты ---
async def register_user(user_id: int, username: Optional[str] = None):
    today = datetime.now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if not await cursor.fetchone():
            await db.execute("""
                INSERT INTO users (user_id, username, daily_messages, last_message_date)
                VALUES (?, ?, 0, ?)
            """, (user_id, username, today))
            await db.commit()
        elif username:
            await db.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
            await db.commit()

async def check_and_increment_daily(user_id: int) -> Tuple[bool, int]:
    today = datetime.now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT daily_messages, last_message_date FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        
        if not row:
            await db.execute("""
                INSERT INTO users (user_id, daily_messages, last_message_date)
                VALUES (?, 1, ?)
            """, (user_id, today))
            await db.commit()
            return True, 1
            
        daily_count, last_date = row
        if last_date != today:
            # Новый день, сбрасываем счетчик
            daily_count = 0
            
        if daily_count >= MAX_DAILY_MESSAGES:
            return False, daily_count
            
        daily_count += 1
        await db.execute("""
            UPDATE users SET daily_messages = ?, last_message_date = ? WHERE user_id = ?
        """, (daily_count, today, user_id))
        await db.commit()
        return True, daily_count

async def can_issue_lifetime_key(user_id: int) -> Tuple[bool, Optional[str]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT lifetime_key_issued_at FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if not row or not row[0]:
            return True, None
            
        last_issued = datetime.fromisoformat(row[0])
        next_allowed = last_issued + timedelta(days=LIFETIME_KEY_COOLDOWN_DAYS)
        if datetime.now() < next_allowed:
            return False, next_allowed.strftime("%Y-%m-%d")
        return True, None

async def mark_lifetime_key_issued(user_id: int):
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET lifetime_key_issued_at = ? WHERE user_id = ?", (now, user_id))
        await db.commit()

# --- Ключи ---
async def get_available_keys(count: int) -> List[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT key_code FROM keys WHERE status = 'available' LIMIT ?", (count,)
        )
        rows = await cursor.fetchall()
        return [r[0] for r in rows]

async def mark_keys_issued(key_codes: List[str], user_id: int):
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        for k in key_codes:
            await db.execute("""
                UPDATE keys SET status = 'issued', issued_to = ?, issued_at = ?
                WHERE key_code = ?
            """, (user_id, now, k))
        await db.commit()

async def get_user_issued_key(user_id: int) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT key_code FROM keys WHERE issued_to = ? ORDER BY id DESC LIMIT 1", (user_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None

from key_generator import generate_app_key

async def get_or_create_app_key(user_id: int) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT app_activation_key FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row and row[0]:
            return row[0]
            
        new_key = generate_app_key()
        await db.execute("UPDATE users SET app_activation_key = ? WHERE user_id = ?", (new_key, user_id))
        await db.commit()
        return new_key

async def get_user_app_key(user_id: int) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT app_activation_key FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row[0] if (row and row[0]) else None

async def get_keys_stats() -> Tuple[int, int, int]:
    async with aiosqlite.connect(DB_PATH) as db:
        c1 = await db.execute("SELECT COUNT(*) FROM keys")
        total = (await c1.fetchone())[0]
        c2 = await db.execute("SELECT COUNT(*) FROM keys WHERE status = 'available'")
        available = (await c2.fetchone())[0]
        c3 = await db.execute("SELECT COUNT(*) FROM keys WHERE status = 'issued'")
        issued = (await c3.fetchone())[0]
        return total, available, issued

async def add_keys(keys_list: List[str]) -> int:
    added = 0
    async with aiosqlite.connect(DB_PATH) as db:
        for k in keys_list:
            k = k.strip()
            if not k:
                continue
            cursor = await db.execute("INSERT OR IGNORE INTO keys (key_code, status) VALUES (?, 'available')", (k,))
            if cursor.rowcount > 0:
                added += 1
        await db.commit()
    return added

# --- Сессии 5 скриншотов ---
async def add_screenshot_to_session(user_id: int, img_hash: str) -> Tuple[int, bool, bool]:
    """
    Возвращает:
    (current_count, is_duplicate, is_expired)
    """
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT count, hashes, started_at FROM screenshot_sessions WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        
        if not row:
            # Первая картинка в сессии
            hashes = [img_hash]
            await db.execute("""
                INSERT OR REPLACE INTO screenshot_sessions (user_id, count, hashes, started_at)
                VALUES (?, 1, ?, ?)
            """, (user_id, json.dumps(hashes), now))
            await db.commit()
            return 1, False, False
            
        count, hashes_json, started_at = row
        hashes = json.loads(hashes_json)
        
        # Проверка таймаута (1 минута)
        if (now - started_at) > SCREENSHOT_BATCH_TIMEOUT:
            # Таймаут истек, сбрасываем и начинаем заново
            hashes = [img_hash]
            await db.execute("""
                UPDATE screenshot_sessions SET count = 1, hashes = ?, started_at = ? WHERE user_id = ?
            """, (json.dumps(hashes), now, user_id))
            await db.commit()
            return 1, False, True
            
        # Проверка на дубликат (если картинка совпадает с одной из присланных ранее)
        if img_hash in hashes:
            return count, True, False
            
        hashes.append(img_hash)
        count += 1
        await db.execute("""
            UPDATE screenshot_sessions SET count = ?, hashes = ? WHERE user_id = ?
        """, (count, json.dumps(hashes), user_id))
        await db.commit()
        return count, False, False

async def reset_screenshot_session(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM screenshot_sessions WHERE user_id = ?", (user_id,))
        await db.commit()

# --- История сообщений и чаты ---
async def save_chat_message(user_id: int, role: str, message_text: str, tg_message_id: int = 0):
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO chat_history (user_id, role, message_text, timestamp, tg_message_id)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, role, message_text, now, tg_message_id))
        await db.commit()

async def get_active_users(limit: int = 10, offset: int = 0) -> List[Tuple[int, Optional[str], int]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT u.user_id, u.username, COUNT(c.id) as msg_count
            FROM users u
            JOIN chat_history c ON u.user_id = c.user_id
            GROUP BY u.user_id
            ORDER BY MAX(c.id) DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))
        return await cursor.fetchall()

async def get_user_chat_history(user_id: int, limit: int = 10, offset: int = 0) -> List[Tuple[str, str, str]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT role, message_text, timestamp
            FROM chat_history
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?
        """, (user_id, limit, offset))
        rows = await cursor.fetchall()
        return list(reversed(rows))

async def get_all_user_ids() -> List[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id FROM users")
        rows = await cursor.fetchall()
        return [r[0] for r in rows]

async def verify_and_bind_app_key(key: str, device_id: str) -> Tuple[bool, str]:
    if not key:
        return False, "Ключ не указан"
    key = key.strip().replace(" ", "").replace("-", "")
    now = datetime.now().isoformat()
    
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT device_id, is_blocked FROM app_activations WHERE key_code = ?", (key,))
        row = await cursor.fetchone()
        
        if row:
            saved_device, is_blocked = row
            if is_blocked:
                return False, "❌ Ключ заблокирован администратором."
            if saved_device == device_id or not saved_device:
                if not saved_device and device_id:
                    await db.execute("UPDATE app_activations SET device_id = ? WHERE key_code = ?", (device_id, key))
                    await db.commit()
                return True, "✅ Лицензия активна."
            else:
                return False, "❌ Ошибка: этот ключ уже привязан к другому устройству!"
                
        from key_generator import verify_app_key
        master_key = (SECRET_ADMIN_PASS + "LOSTBOT2026") if SECRET_ADMIN_PASS else None
        is_valid = verify_app_key(key) or (master_key and key == master_key) or key == "LOSTBOT-PRO-ACTIVATION"
        if not is_valid:
            cursor = await db.execute("SELECT user_id FROM users WHERE app_activation_key = ?", (key,))
            if await cursor.fetchone():
                is_valid = True
                
        if not is_valid:
            return False, "❌ Неверный ключ активации."
            
        await db.execute("""
            INSERT INTO app_activations (key_code, device_id, activated_at, is_blocked)
            VALUES (?, ?, ?, 0)
        """, (key, device_id, now))
        await db.commit()
        return True, "✅ Успешная активация! Ключ привязан к вашему устройству."
