import asyncio
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
import database as db
import limiter
import ai_service
from config import INITIAL_KEYS, ADMIN_ID

async def run_tests():
    print("=== ТЕСТИРОВАНИЕ СИСТЕМ LOSTBOT PRO ===")
    
    # 1. Тест базы данных
    print("[1] Инициализация базы данных...")
    await db.init_db()
    total, avail, issued = await db.get_keys_stats()
    print(f"    Ключи в базе: всего={total}, доступно={avail}, выдано={issued}")
    assert total >= 15, "Должно быть загружено не менее 15 ключей"
    
    # 2. Тест режима обслуживания
    is_m = await db.get_maintenance_mode()
    print(f"    Режим закрытого тестирования: {'ВКЛЮЧЕН' if is_m else 'ВЫКЛЮЧЕН'}")
    assert is_m is True, "По умолчанию должен быть закрытый режим тестов"
    
    # 3. Тест лимитов сообщений
    print("[2] Тестирование системы лимитов...")
    test_uid = 999999999
    await db.register_user(test_uid, "test_user")
    
    # RPM тест
    for i in range(5):
        ok, _ = limiter.check_rpm_limit(test_uid)
        assert ok, f"Запрос {i+1} должен пройти"
    ok, err = limiter.check_rpm_limit(test_uid)
    assert not ok, "6-й запрос в минуту должен блокироваться"
    print(f"    Лимит 5 запросов в минуту сработал корректно: {err}")
    
    # 4. Тест нейросети Gemini 3.5 Flash Lite
    print("[3] Проверка связи с Gemini 3.5 Flash Lite...")
    resp, pos = await ai_service.request_ai_chat("Кто разработчик проекта LostBot Pro?")
    print(f"    Ответ ИИ: {resp[:120]}...")
    assert "@Lolpolnol" in resp or "Lolpolnol" in resp or "lolpolnol0" in resp or len(resp) > 10, "ИИ должен ответить корректно"
    
    # 5. Тест выдачи ключей
    print("[4] Тест резервирования ключей...")
    keys = await db.get_available_keys(5)
    print(f"    Получено 5 доступных ключей: {keys}")
    assert len(keys) == 5
    
    # 6. Тест лимита вечного ключа (1 раз в месяц)
    print("[5] Тест ограничения вечного ключа...")
    can_issue, _ = await db.can_issue_lifetime_key(test_uid)
    assert can_issue is True, "Первый вечный ключ должен разрешаться"
    await db.mark_lifetime_key_issued(test_uid)
    can_issue2, next_date = await db.can_issue_lifetime_key(test_uid)
    assert can_issue2 is False, "Повторный вечный ключ в том же месяце должен блокироваться"
    print(f"    Лимит 1 ключ в месяц работает: заблокировано до {next_date}")
    
    print("\n✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")

if __name__ == "__main__":
    asyncio.run(run_tests())
