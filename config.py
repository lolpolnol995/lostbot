import os

# Загрузка локальных переменных из .env (файл не публикуется в репозиторий)
env_file = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_file):
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# Основные токены (берутся из переменных окружения)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# Администратор и каналы
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "")
SECRET_ADMIN_PASS = os.getenv("SECRET_ADMIN_PASS", "")

# Лимиты
MAX_RPM = 5                  # Максимум сообщений в минуту
MAX_DAILY_MESSAGES = 20      # Максимум сообщений в день на пользователя
SCREENSHOT_BATCH_TIMEOUT = 1800 # Таймер ожидания 5 скриншотов (30 минут)
SCREENSHOT_COOLDOWN = 180     # Кулдаун отправки скриншотов (в секундах)
LIFETIME_KEY_COOLDOWN_DAYS = 30 # Лимит вечного ключа: 1 в 30 дней на пользователя

# Тарифы Telegram Stars
STARS_PRICE_10_KEYS = 15     # 10 ключей = 15 Stars
STARS_PRICE_ALL_KEYS = 25    # Все 15 ключей = 25 Stars
BONUS_LIFETIME_THRESHOLD = 20 # Порог для получения бонусного вечного ключа

# Базовый пул ключей (загружается из защищенного окружения)
_raw_keys = os.getenv("INITIAL_KEYS", "")
INITIAL_KEYS = [k.strip() for k in _raw_keys.split(",") if k.strip()]

# Закрепленный обучающий пост
PINNED_POST_TEXT = (
    "📌 <b>ИНСТРУКЦИЯ ПО ИСПОЛЬЗОВАНИЮ И АНЛОКУ</b>\n\n"
    "Канал проекта: @lolpolnol0\n\n"
    "<b>Как получить ключи бесплатно:</b>\n"
    "1) В поиске TikTok введите: <code>lostbot</code>\n"
    "2) Найдите 5 разных видео и ответьте на комментарии, где спрашивают про ключ:\n"
    "   <i>@lolpolnol0 фри премка + лайфтайм + ключи</i>\n"
    "3) Сделайте 5 РАЗНЫХ скриншотов ваших комментариев и отправьте их сюда в бота @Lostbotik_bot.\n\n"
    "<b>Как купить за Telegram Stars:</b>\n"
    "• 10 ключей = 15 ⭐️ Stars\n"
    "• Все 15 ключей = 25 ⭐️ Stars (включает бонусный вечный ключ)\n\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "⚡️ <b>КАК ПРАВИЛЬНО АНЛОКАТЬ САМОКАТ (ЕСЛИ НЕ СРАБАТЫВАЕТ):</b>\n\n"
    "1. <b>Задержка спама:</b> НЕ ставьте 2 мс! Ставьте задержку строго <b>250–300 мс</b>. На 2 мс Bluetooth глушит сам себя и контроллер уходит в аварийную защиту.\n"
    "2. <b>Порядок действий:</b>\n"
    "   • Подключитесь к самокату\n"
    "   • Нажмите <b>Handshake</b> (дождитесь статуса <code>Ready</code>)\n"
    "   • Нажмите кнопку <b>Unlock</b>\n"
    "3. <b>Разбудите дисплей:</b> В момент нажатия Unlock или при включенном спаме обязательно <b>нажмите курок газа или зажмите тормоз</b>, чтобы разбудить контроллер из спящего режима!\n"
    "4. <b>Подбор ключей:</b> По очереди пробуйте все 6 выданных ботом ключей в настройках (Update key).\n"
    "5. <b>Если приложение уже активировано:</b> Вводить ключ заново не нужно, лицензия навсегда привязана к вашему устройству!"
)
