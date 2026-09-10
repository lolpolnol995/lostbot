# key_generator.py - Генерация и валидация 20-значных динамических лицензионных ключей
import random
import hashlib

CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
SECRET = "LostBotPro_2026_Key"

def generate_app_key() -> str:
    """
    Генерирует уникальный 20-символьный ключ (заглавные, строчные буквы, цифры)
    с криптографической контрольной суммой SHA-256, которую валидирует приложение без интернета.
    """
    while True:
        payload = "".join(random.choices(CHARSET, k=14))
        # Гарантируем разнообразие символов: заглавная, строчная, цифра
        if any(c.isupper() for c in payload) and any(c.islower() for c in payload) and any(c.isdigit() for c in payload):
            break
            
    digest = hashlib.sha256((payload + SECRET).encode("utf-8")).digest()
    checksum = "".join(CHARSET[b % 62] for b in digest[:6])
    return payload + checksum

def verify_app_key(key: str) -> bool:
    """
    Проверяет валидность 20-значного ключа.
    """
    if not key:
        return False
    key = key.strip().replace("-", "").replace(" ", "")
    if len(key) != 20:
        return False
        
    payload = key[:14]
    expected_checksum = key[14:]
    digest = hashlib.sha256((payload + SECRET).encode("utf-8")).digest()
    calc_checksum = "".join(CHARSET[b % 62] for b in digest[:6])
    return calc_checksum == expected_checksum
