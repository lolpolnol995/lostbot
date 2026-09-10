@echo off
chcp 65001 >nul
title LostBot Pro Telegram Bot
echo ===================================================
echo   Запуск Telegram-бота LostBot Pro (@Lostbotik_bot)
echo ===================================================
cd /d "%~dp0"
python bot.py
pause
