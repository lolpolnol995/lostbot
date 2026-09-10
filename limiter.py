import time
from collections import defaultdict
from config import MAX_RPM, SCREENSHOT_COOLDOWN, ADMIN_ID
from database import check_and_increment_daily

# Хранилище временных меток запросов пользователей: user_id -> [timestamp1, timestamp2, ...]
_user_message_times = defaultdict(list)
_user_screenshot_batch_times = {}

def check_rpm_limit(user_id: int) -> tuple[bool, str]:
    """Проверка лимита: 5 сообщений в минуту"""
    if user_id == ADMIN_ID:
        return True, ""
        
    now = time.time()
    times = _user_message_times[user_id]
    
    # Удаляем метки старше 60 секунд
    _user_message_times[user_id] = [t for t in times if now - t < 60]
    
    if len(_user_message_times[user_id]) >= MAX_RPM:
        return False, "⏳ <b>Слишком быстро!</b> Лимит: 5 сообщений в минуту. Подождите пару секунд перед следующим сообщением."
        
    _user_message_times[user_id].append(now)
    return True, ""

async def check_daily_limit(user_id: int) -> tuple[bool, str]:
    """Проверка лимита: 20 сообщений в день"""
    if user_id == ADMIN_ID:
        return True, ""
        
    allowed, count = await check_and_increment_daily(user_id)
    if not allowed:
        return False, "⛔ <b>Дневной лимит исчерпан!</b>\nВы использовали все 20 сообщений на сегодня (20/20).\nЛимит обновится завтра в 00:00."
    return True, ""

def check_screenshot_cooldown(user_id: int) -> tuple[bool, str]:
    """Проверка кулдауна на отправку пачки скриншотов (3 минуты)"""
    if user_id == ADMIN_ID:
        return True, ""
        
    now = time.time()
    last_time = _user_screenshot_batch_times.get(user_id, 0)
    
    if now - last_time < SCREENSHOT_COOLDOWN:
        remaining = int(SCREENSHOT_COOLDOWN - (now - last_time))
        return False, f"⏳ <b>Слишком частая отправка скриншотов!</b>\nПожалуйста, подождите ещё {remaining} сек. (лимит: 1 попытка раз в 3 минуты)."
        
    return True, ""

def record_screenshot_batch_sent(user_id: int):
    _user_screenshot_batch_times[user_id] = time.time()
