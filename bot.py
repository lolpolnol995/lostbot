import asyncio
import io
import re
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message, CallbackQuery, PreCheckoutQuery, LabeledPrice,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.enums import ParseMode

from config import (
    BOT_TOKEN, ADMIN_ID, ADMIN_USERNAME, CHANNEL_USERNAME, SECRET_ADMIN_PASS,
    STARS_PRICE_10_KEYS, STARS_PRICE_ALL_KEYS, PINNED_POST_TEXT
)
import database as db
import limiter
import ai_service
from admin_panel import admin_router, show_admin_panel
from image_utils import calculate_image_hash
import support_chat

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.include_router(admin_router)

def get_main_keyboard() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text="📌 Инструкция (Как получить ключ)", callback_data="show_instructions")],
        [InlineKeyboardButton(text="⭐️ Купить ключи за Stars", callback_data="show_stars_buy")],
        [InlineKeyboardButton(text="📢 Официальный канал", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_stars_keyboard() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text="⭐️ 10 ключей (15 Stars)", callback_data="buy_stars_10")],
        [InlineKeyboardButton(text="⭐️ Все 15 ключей + Бонус (25 Stars)", callback_data="buy_stars_all")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- Middleware проверки закрытого режима ---
@dp.message.outer_middleware()
async def maintenance_message_middleware(handler, event: Message, data: dict):
    if not isinstance(event, Message):
        return await handler(event, data)
        
    user_id = event.from_user.id if event.from_user else 0
    if user_id == ADMIN_ID:
        return await handler(event, data)
        
    if event.text and event.text.strip().lower() == SECRET_ADMIN_PASS.lower():
        return await handler(event, data)
        
    is_m = await db.get_maintenance_mode()
    if is_m:
        await event.answer(
            "🛠️ <b>Бот находится на техническом обслуживании / закрытом тестировании.</b>\n\n"
            f"Доступ скоро откроется! Следите за новостями и анонсами в нашем канале: {CHANNEL_USERNAME}",
            parse_mode="HTML"
        )
        return
        
    return await handler(event, data)

@dp.callback_query.outer_middleware()
async def maintenance_callback_middleware(handler, event: CallbackQuery, data: dict):
    user_id = event.from_user.id if event.from_user else 0
    if user_id == ADMIN_ID:
        return await handler(event, data)
        
    is_m = await db.get_maintenance_mode()
    if is_m:
        return await event.answer("🛠️ Бот на техработах/тестировании. Доступ закрыт.", show_alert=True)
        
    return await handler(event, data)

# --- Команда /start ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    uid = message.from_user.id
    uname = message.from_user.username
    await db.register_user(uid, uname)
    
    if uid != ADMIN_ID:
        is_m = await db.get_maintenance_mode()
        if is_m:
            return await message.answer(
                "🛠 <b>ТЕХНИЧЕСКИЕ РАБОТЫ</b>\n\n"
                "Бот временно отключен на техническое обслуживание. Пожалуйста, попробуйте позже!",
                parse_mode="HTML"
            )
    
    welcome_text = (
        f"👋 <b>Добро пожаловать в LostBot Pro!</b>\n\n"
        f"Здесь вы можете:\n"
        f"• Получить ключи активации бесплатно (за 5 скриншотов комментов в TikTok).\n"
        f"• Приобрести ключи за Telegram Stars.\n"
        f"• Задать любой вопрос поддержке или сообщить о найденном баге.\n\n"
        f"ℹ️ <b>Лимиты:</b>\n"
        f"• До 20 сообщений в день\n"
        f"• До 5 сообщений в минуту\n\n"
        f"Выберите действие ниже или просто напишите ваш вопрос:"
    )
    
    kb = [
        [InlineKeyboardButton(text="📌 Инструкция (Как получить ключ)", callback_data="show_instructions")],
        [InlineKeyboardButton(text="🔑 Мой ключ", callback_data="show_my_key")],
        [InlineKeyboardButton(text="⭐️ Купить ключи за Stars", callback_data="show_stars_buy")],
        [InlineKeyboardButton(text="📢 Официальный канал", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")]
    ]
    
    # Только для владельца добавляем кнопку входа в админ-панель
    if uid == ADMIN_ID:
        kb.append([InlineKeyboardButton(text="👑 Открыть панель управления", callback_data="open_admin_panel")])
        
    await message.answer(welcome_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@dp.callback_query(F.data == "open_admin_panel")
async def cb_open_admin_panel(call: CallbackQuery):
    if call.from_user.id == ADMIN_ID:
        await show_admin_panel(call.message, bot, user_id=call.from_user.id)
        await call.answer()
    else:
        await call.answer("⛔ Доступ запрещен", show_alert=True)

@dp.callback_query(F.data == "show_my_key")
async def cb_show_my_key(call: CallbackQuery):
    uid = call.from_user.id
    app_key = await db.get_user_app_key(uid)
    if not app_key:
        text = (
            "🔑 <b>У вас пока нет активного ключа для приложения.</b>\n\n"
            "Вы можете получить 20-значный ключ бесплатно за 5 скриншотов из TikTok "
            "или приобрести за Telegram Stars."
        )
    else:
        text = (
            f"🔑 <b>Ваш ключ приложения (20 символов):</b>\n<code>{app_key}</code>\n\n"
            f"⚠️ <b>ОБЯЗАТЕЛЬНО ВЫКЛЮЧИТЕ VPN при активации ключа в приложении!</b>\n"
            f"Ключ привязывается к вашему устройству навсегда."
        )
    await call.message.answer(text, parse_mode="HTML")
    await call.answer()

# --- Команда /admin и кодовое слово ---
@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id == ADMIN_ID:
        await show_admin_panel(message, bot)
    else:
        await message.answer("⛔ Доступ запрещен.")

@dp.message(F.text.lower() == SECRET_ADMIN_PASS.lower())
async def handle_admin_secret(message: Message):
    # Вход по кодовому слову админа
    await show_admin_panel(message, bot)

# --- Команда добавления ключей /addkeys ---
@dp.message(Command("addkeys"))
async def cmd_addkeys(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    keys = message.text.replace("/addkeys", "").strip().split()
    if not keys:
        return await message.answer("Использование: <code>/addkeys KEY1 KEY2 KEY3</code>", parse_mode="HTML")
    added = await db.add_keys(keys)
    await message.answer(f"✅ Добавлено <b>{added}</b> новых ключей в базу!", parse_mode="HTML")

# --- Ответ админа через Reply на пересланное сообщение ---
@dp.message(F.from_user.id == ADMIN_ID, F.reply_to_message)
async def handle_admin_reply_to_message(message: Message):
    reply = message.reply_to_message
    target_id = None
    
    # Ищем шаблон [ID: 12345678] в тексте или подписи реплая
    text_to_search = (reply.text or "") + " " + (reply.caption or "")
    match = re.search(r"\[ID:\s*(\d+)\]", text_to_search)
    if match:
        target_id = int(match.group(1))
        
    if not target_id:
        return  # Не сообщение от пользователя, игнорируем
        
    try:
        support_chat.start_session(target_id)
        user_msg = (
            f"👨‍💻 <b>С вами на связи разработчик ({ADMIN_USERNAME}):</b>\n\n"
            f"{message.text or 'Вам отправлено медиа-вложение.'}\n\n"
            f"<i>(Вы можете отвечать прямо сюда, ваши сообщения дойдут разработчику напрямую)</i>"
        )
        if message.text:
            await bot.send_message(target_id, user_msg, parse_mode="HTML")
        elif message.photo:
            await bot.send_photo(target_id, message.photo[-1].file_id, caption=user_msg, parse_mode="HTML")
        elif message.video:
            await bot.send_video(target_id, message.video.file_id, caption=user_msg, parse_mode="HTML")
            
        end_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛑 Завершить диалог", callback_data=f"end_chat:{target_id}")]
        ])
        await message.answer(
            f"🟢 <b>Прямой диалог с пользователем [ID: <code>{target_id}</code>] открыт!</b>\n\n"
            f"• Сообщение доставлено пользователю.\n"
            f"• Все следующие ответы пользователя будут приходить сюда (ИИ отключен).\n"
            f"• Все ваши сообщения будут пересылаться пользователю.\n\n"
            f"Чтобы закончить диалог, нажмите кнопку ниже или отправьте /end.",
            reply_markup=end_kb,
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка отправки пользователю: {e}")

# --- Инлайн-кнопки меню ---
@dp.callback_query(F.data == "show_instructions")
async def cb_show_instructions(call: CallbackQuery):
    await call.message.answer(PINNED_POST_TEXT, parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "show_stars_buy")
async def cb_show_stars_buy(call: CallbackQuery):
    text = (
        f"⭐️ <b>Покупка ключей за Telegram Stars:</b>\n\n"
        f"• <b>10 ключей</b> = 15 ⭐️ Stars\n"
        f"• <b>Все 15 ключей</b> = 25 ⭐️ Stars (+ бонусный вечный ключ для приложения!)\n\n"
        f"Ключи выдаются автоматически сразу после оплаты.\n"
        f"Выберите нужный вариант:"
    )
    await call.message.edit_text(text, reply_markup=get_stars_keyboard(), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "back_to_main")
async def cb_back_to_main(call: CallbackQuery):
    await call.message.edit_text("Выберите действие:", reply_markup=get_main_keyboard(), parse_mode="HTML")
    await call.answer()

# --- Выставление счетов Telegram Stars ---
@dp.callback_query(F.data == "buy_stars_10")
async def cb_buy_stars_10(call: CallbackQuery):
    prices = [LabeledPrice(label="10 ключей LostBot Pro", amount=STARS_PRICE_10_KEYS)]
    await bot.send_invoice(
        chat_id=call.from_user.id,
        title="10 Лицензионных Ключей",
        description="Пакет из 10 ключей для LostBot Pro. Моментальная выдача после оплаты.",
        payload="buy_10_keys",
        currency="XTR",
        prices=prices
    )
    await call.answer()

@dp.callback_query(F.data == "buy_stars_all")
async def cb_buy_stars_all(call: CallbackQuery):
    prices = [LabeledPrice(label="Все 15 ключей + Бонус", amount=STARS_PRICE_ALL_KEYS)]
    await bot.send_invoice(
        chat_id=call.from_user.id,
        title="Все 15 Ключей + Бонус Вечный Ключ",
        description="Полный пул из 15 ключей + Бонусный пожизненный ключ для приложения LostBot Pro.",
        payload="buy_all_keys",
        currency="XTR",
        prices=prices
    )
    await call.answer()

@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def process_successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    stars = message.successful_payment.total_amount
    uid = message.from_user.id
    uname = message.from_user.username or "без username"
    
    count = 10 if payload == "buy_10_keys" else 15
    from config import INITIAL_KEYS
    keys = INITIAL_KEYS[:count] if INITIAL_KEYS else [
        "Ulb8omSq", "S9oqBJM0", "w4S3Hqn5", "4BKNwi77", "78Hkw9NN",
        "2BXy8p0W", "9wYGaWn6", "k3X8trbN", "k8P2mX9v", "5TJ7qw1L",
        "z9R3Ne6M", "p9G4vK1X", "6WR8mz3B", "t2H7yQ5L", "4NJ3sc8P"
    ][:count]
    
    keys_formatted = "\n".join([f"<code>{k}</code>" for k in keys])
    bonus_text = ""
    
    # Если оплачено 20+ звезд — проверяем выдачу вечного ключа приложения (1 раз в месяц)
    if stars >= 20:
        can_issue, next_date = await db.can_issue_lifetime_key(uid)
        if can_issue:
            await db.mark_lifetime_key_issued(uid)
            bonus_key = await db.get_or_create_app_key(uid)
            bonus_text = (
                f"\n\n🎁 <b>БОНУС ЗА ОПЛАТУ 20+ ЗВЕЗД: КЛЮЧ ПРИЛОЖЕНИЯ!</b>\n"
                f"Ключ для входа в приложение (20 символов):\n<code>{bonus_key}</code>\n"
                f"⚠️ <b>ОБЯЗАТЕЛЬНО ВЫКЛЮЧИТЕ VPN ПРИ ВВОДЕ КЛЮЧА В ПРИЛОЖЕНИИ!</b>\n"
                f"<i>Лимит: 1 ключ в месяц на пользователя.</i>"
            )
        else:
            bonus_text = f"\n\n⚠️ <i>Лимит вечного ключа уже исчерпан на этот месяц (следующий доступен с {next_date}).</i>"
            
    response_msg = (
        f"🎉 <b>Оплата {stars} ⭐️ успешно получена!</b>\n\n"
        f"Ваши приобретенные ключи:\n{keys_formatted}"
        f"{bonus_text}\n\n"
        f"Спасибо за поддержку проекта!"
    )
    await message.answer(response_msg, parse_mode="HTML")
    
    # Мгновенное оповещение админу
    user_link = f"@{uname}" if uname != "без username" else f"<a href='tg://user?id={uid}'>Профиль</a>"
    admin_alert = (
        f"💰 <b>НОВАЯ ОПЛАТА STARS! [ID: {uid}]</b>\n\n"
        f"• Пользователь: {user_link} (ID: <code>{uid}</code>)\n"
        f"• Сумма: <b>{stars} ⭐️ Stars</b>\n"
        f"• Выдано ключей: <b>{count} шт.</b>\n\n"
        f"💬 Нажмите 'Ответить' (Reply) на это сообщение или кнопку ниже, чтобы начать диалог:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✉️ Написать пользователю", callback_data=f"reply_to:{uid}")]
    ])
    await bot.send_message(ADMIN_ID, admin_alert, reply_markup=kb, parse_mode="HTML")

# --- Обработка медиа (Фото, Скриншоты, Видео, Логи) ---
_photo_batches = {}
_batch_tasks = {}
_active_analysis_tasks = {}

@dp.callback_query(F.data.startswith("cancel_analysis:"))
async def cb_cancel_analysis(call: CallbackQuery):
    target_uid = int(call.data.split(":")[1])
    if call.from_user.id != target_uid and call.from_user.id != ADMIN_ID:
        return await call.answer("Это не ваш анализ", show_alert=True)
        
    task = _active_analysis_tasks.pop(target_uid, None)
    if task and not task.done():
        task.cancel()
        await call.answer("Анализ отменен")
        try:
            await call.message.edit_text(
                "❌ <b>Анализ скриншотов отменен.</b>\nВы можете отправить новые скриншоты в любое удобное время.", 
                parse_mode="HTML"
            )
        except Exception:
            pass
    else:
        await call.answer("Анализ уже завершен", show_alert=True)

@dp.message(F.photo, StateFilter(None))
async def handle_photo(message: Message):
    uid = message.from_user.id
    
    # Если админ в активной сессии - пересылаем фото пользователю
    if uid == ADMIN_ID:
        target = support_chat.get_active_admin_target()
        if target:
            caption = f"👨‍💻 <b>Разработчик:</b>\n{message.caption or ''}"
            await bot.send_photo(target, message.photo[-1].file_id, caption=caption, parse_mode="HTML")
            end_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🛑 Завершить диалог", callback_data=f"end_chat:{target}")]])
            return await message.answer(f"✅ Фото отправлено пользователю [ID: <code>{target}</code>]", reply_markup=end_kb, parse_mode="HTML")
            
    # Если пользователь в сессии с админом - пересылаем фото админу
    if support_chat.is_user_in_session(uid):
        end_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🛑 Завершить диалог", callback_data=f"end_chat:{uid}")]])
        caption = f"👤 <b>Фото от пользователя [ID: <code>{uid}</code>]:</b>\n{message.caption or ''}"
    if uid != ADMIN_ID:
        is_m = await db.get_maintenance_mode()
        if is_m:
            return await message.answer(
                "🛠 <b>ТЕХНИЧЕСКИЕ РАБОТЫ</b>\n\n"
                "Бот временно отключен на техническое обслуживание. Прием скриншотов приостановлен.",
                parse_mode="HTML"
            )

    if uid not in _photo_batches:
        _photo_batches[uid] = []
        
    _photo_batches[uid].append(message)
    
    # Сбрасываем старую отложенную задачу и ждем 0.6 сек, пока придут все фото из пачки
    if uid in _batch_tasks and not _batch_tasks[uid].done():
        _batch_tasks[uid].cancel()
        
    _batch_tasks[uid] = asyncio.create_task(_delayed_process_photos(uid, message.chat.id))

async def _delayed_process_photos(uid: int, chat_id: int):
    try:
        await asyncio.sleep(0.6)
        messages = _photo_batches.pop(uid, [])
        if not messages:
            return
            
        current_task = asyncio.current_task()
        _active_analysis_tasks[uid] = current_task
        
        current_valid = await db.get_screenshot_session_count(uid)
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить анализ", callback_data=f"cancel_analysis:{uid}")]
        ])
        status_msg = await bot.send_message(
            chat_id, 
            f"⚡️ <i>Быстрый анализ скриншотов... (Прогресс: {current_valid}/5)</i>", 
            reply_markup=cancel_kb,
            parse_mode="HTML"
        )
        
        # 1. Параллельная загрузка и параллельный анализ через нейросеть
        async def analyze_single(msg):
            photo = msg.photo[-1]
            file_io = io.BytesIO()
            await bot.download(photo, destination=file_io)
            img_bytes = file_io.getvalue()
            img_hash = calculate_image_hash(img_bytes)
            classification, _ = await ai_service.request_image_classification(img_bytes, msg.caption or "")
            return msg, photo, img_hash, classification

        analyzed_items = await asyncio.gather(*(analyze_single(m) for m in messages))
        
        valid_tiktok = current_valid
        duplicates = 0
        bugs = 0
        irrelevant = 0
        
        for msg, photo, img_hash, classification in analyzed_items:
            img_type = classification.get("type", "IRRELEVANT")
            if uid == ADMIN_ID and img_type != "BUG_REPORT":
                img_type = "TIKTOK_PROOF"
            
            if img_type == "BUG_REPORT":
                bugs += 1
                uname = msg.from_user.username or "без username"
                user_link = f"@{uname}" if uname != "без username" else f"<a href='tg://user?id={uid}'>Профиль</a>"
                report_text = (
                    f"🚨 <b>БАГ-РЕПОРТ ОТ ПОЛЬЗОВАТЕЛЯ [ID: {uid}]</b>\n\n"
                    f"• От: {user_link} (ID: <code>{uid}</code>)\n"
                    f"• Описание: {msg.caption if msg.caption else '<i>без описания</i>'}\n\n"
                    f"💬 Ответьте на это сообщение (Reply), чтобы написать пользователю."
                )
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✉️ Ответить пользователю", callback_data=f"reply_to:{uid}")]
                ])
                await bot.send_photo(ADMIN_ID, photo.file_id, caption=report_text, reply_markup=kb, parse_mode="HTML")
            elif img_type == "TIKTOK_PROOF":
                count, is_dup, is_exp = await db.add_screenshot_to_session(uid, img_hash)
                if is_dup:
                    duplicates += 1
                elif is_exp:
                    valid_tiktok = 1
                else:
                    valid_tiktok = count
            else:
                irrelevant += 1
                
        try:
            await status_msg.delete()
        except Exception:
            pass
            
        if bugs > 0 and valid_tiktok == 0 and duplicates == 0 and irrelevant == 0:
            return await bot.send_message(
                chat_id,
                f"✅ <b>Ваш баг-репорт передан разработчику ({ADMIN_USERNAME})!</b>",
                parse_mode="HTML"
            )
            
        if valid_tiktok >= 5:
            await db.reset_screenshot_session(uid)
            limiter.record_screenshot_batch_sent(uid)
            app_key = await db.get_or_create_app_key(uid)
            
            k1 = INITIAL_KEYS[0] if len(INITIAL_KEYS) > 0 else "KEY_1"
            k2 = INITIAL_KEYS[1] if len(INITIAL_KEYS) > 1 else "KEY_2"
            k3 = INITIAL_KEYS[2] if len(INITIAL_KEYS) > 2 else "KEY_3"
            k4 = INITIAL_KEYS[3] if len(INITIAL_KEYS) > 3 else "KEY_4"
            k5 = INITIAL_KEYS[4] if len(INITIAL_KEYS) > 4 else "KEY_5"
            k6 = INITIAL_KEYS[5] if len(INITIAL_KEYS) > 5 else "KEY_6"
            exact_template = (
                "🎉 <b>Задание выполнено! Все 5 скриншотов проверены.</b>\n\n"
                f"🔑 <b>Ваш ключ активации приложения (20 символов):</b>\n"
                f"<code>{app_key}</code>\n\n"
                "⚠️ <b>ОБЯЗАТЕЛЬНО ВЫКЛЮЧИТЕ VPN при вводе ключа в приложении!</b>\n"
                "Ключ навсегда привязывается к вашему устройству.\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "⚡️ <b>Ключи для подбора ВНУТРИ приложения:</b>\n\n"
                f"<code>{k1}</code> (топ 1)\n\n"
                f"<code>{k2}</code>\n\n"
                f"<code>{k3}</code>\n\n"
                f"<code>{k4}</code> (тоже хороший)\n\n"
                f"<code>{k5}</code>\n"
                "На крайняк\n"
                f"<code>{k6}</code>"
            )
            return await bot.send_message(chat_id, exact_template, parse_mode="HTML")
            
        res_lines = ["📊 <b>Результат проверки скриншотов:</b>"]
        if valid_tiktok > 0:
            res_lines.append(f"• Принято: <b>{valid_tiktok} из 5</b> (комментарии в TikTok подтверждены)")
        if duplicates > 0:
            res_lines.append(f"• Отклонено: <b>{duplicates} дубликат(ов)</b> (повторные скриншоты)")
        if irrelevant > 0:
            res_lines.append(f"• Отклонено: <b>{irrelevant} сторонних фото</b> (не распознаны как комментарий TikTok)")
        if bugs > 0:
            res_lines.append(f"• <b>{bugs} фото передано разработчику как баг-репорт</b>")
            
        remaining = 5 - valid_tiktok
        res_lines.append(f"\n⏳ Прогресс сохранен (<b>{valid_tiktok}/5</b>)! У вас есть 30 минут, чтобы прислать оставшиеся <b>{remaining}</b> шт.")
        await bot.send_message(chat_id, "\n".join(res_lines), parse_mode="HTML")
        
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"Error in batch photo processor: {e}")
    finally:
        _active_analysis_tasks.pop(uid, None)

# --- Обработка видео и файлов логов (как баг-репорты) ---
@dp.message(F.video | F.document, StateFilter(None))
async def handle_video_or_doc(message: Message):
    uid = message.from_user.id
    
    # Если админ в активной сессии - пересылаем пользователю
    if uid == ADMIN_ID:
        target = support_chat.get_active_admin_target()
        if target:
            caption = f"👨‍💻 <b>Разработчик:</b>\n{message.caption or ''}"
            if message.video:
                await bot.send_video(target, message.video.file_id, caption=caption, parse_mode="HTML")
            else:
                await bot.send_document(target, message.document.file_id, caption=caption, parse_mode="HTML")
            end_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🛑 Завершить диалог", callback_data=f"end_chat:{target}")]])
            return await message.answer(f"✅ Файл отправлен пользователю [ID: <code>{target}</code>]", reply_markup=end_kb, parse_mode="HTML")
            
    # Если пользователь в сессии с админом - пересылаем админу
    if support_chat.is_user_in_session(uid):
        end_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🛑 Завершить диалог", callback_data=f"end_chat:{uid}")]])
        caption = f"👤 <b>Файл от пользователя [ID: <code>{uid}</code>]:</b>\n{message.caption or ''}"
        if message.video:
            await bot.send_video(ADMIN_ID, message.video.file_id, caption=caption, reply_markup=end_kb, parse_mode="HTML")
        else:
            await bot.send_document(ADMIN_ID, message.document.file_id, caption=caption, reply_markup=end_kb, parse_mode="HTML")
        return await message.answer("<i>(Файл доставлен разработчику 👨‍💻)</i>", parse_mode="HTML")

    uname = message.from_user.username or "без username"
    caption = message.caption or "Лог/видео работы приложения"
    
    user_link = f"@{uname}" if uname != "без username" else f"<a href='tg://user?id={uid}'>Профиль</a>"
    alert_text = (
        f"🚨 <b>БАГ-РЕПОРТ / ФАЙЛ [ID: {uid}]</b>\n\n"
        f"• От: {user_link} (ID: <code>{uid}</code>)\n"
        f"• Описание: {caption}\n\n"
        f"💬 Ответьте на это сообщение (Reply), чтобы написать пользователю."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✉️ Ответить пользователю", callback_data=f"reply_to:{uid}")]
    ])
    
    if message.video:
        await bot.send_video(ADMIN_ID, message.video.file_id, caption=alert_text, reply_markup=kb, parse_mode="HTML")
    elif message.document:
        await bot.send_document(ADMIN_ID, message.document.file_id, caption=alert_text, reply_markup=kb, parse_mode="HTML")
        
    await message.answer(
        f"✅ <b>Вложение успешно передано разработчику ({ADMIN_USERNAME})!</b>\n"
        f"Спасибо за обратную связь.",
        parse_mode="HTML"
    )

# --- Обработка обычных текстовых сообщений ---
@dp.message(F.text, StateFilter(None))
async def handle_text(message: Message):
    uid = message.from_user.id
    text = message.text.strip()
    
    # 0. Проверка действий Администратора
    if uid == ADMIN_ID:
        # Команда завершения прямого диалога
        if text.lower() in ["/end", "/stop", "завершить", "завершено", "стоп"]:
            target = support_chat.end_session()
            if target:
                try:
                    await bot.send_message(
                        target,
                        "✅ <b>Диалог с разработчиком завершен.</b>\n"
                        "Спасибо за обращение! Если у вас появятся новые вопросы, бот снова готов помочь.",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
                return await message.answer(
                    f"🔴 <b>Диалог с пользователем [ID: <code>{target}</code>] завершен.</b>\n"
                    f"Бот вернулся в обычный режим.",
                    parse_mode="HTML"
                )
            else:
                return await message.answer("ℹ️ Сейчас нет активного прямого диалога с пользователем.")
                
        target = support_chat.get_active_admin_target()
        if target:
            try:
                await bot.send_message(target, f"👨‍💻 <b>Разработчик ({ADMIN_USERNAME}):</b>\n\n{text}", parse_mode="HTML")
                end_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🛑 Завершить диалог", callback_data=f"end_chat:{target}")]
                ])
                return await message.answer(f"✅ Доставлено пользователю [ID: <code>{target}</code>]", reply_markup=end_kb, parse_mode="HTML")
            except Exception as e:
                return await message.answer(f"❌ Ошибка отправки: {e}")

    # 1. Если пользователь находится в прямом диалоге с админом
    if support_chat.is_user_in_session(uid):
        end_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛑 Завершить диалог", callback_data=f"end_chat:{uid}")]
        ])
        uname = message.from_user.username or "без username"
        user_link = f"@{uname}" if uname != "без username" else f"<a href='tg://user?id={uid}'>Профиль</a>"
        await bot.send_message(
            ADMIN_ID,
            f"👤 <b>Сообщение от {user_link} [ID: <code>{uid}</code>]:</b>\n\n{text}",
            reply_markup=end_kb,
            parse_mode="HTML"
        )
    if uid != ADMIN_ID:
        is_m = await db.get_maintenance_mode()
        if is_m:
            return await message.answer(
                "🛠 <b>ТЕХНИЧЕСКИЕ РАБОТЫ</b>\n\n"
                "Бот временно отключен на техническое обслуживание. Пожалуйста, попробуйте позже!",
                parse_mode="HTML"
            )

    # Лимиты
    ok_rpm, err_rpm = limiter.check_rpm_limit(uid)
    if not ok_rpm:
        return await message.answer(err_rpm, parse_mode="HTML")
    ok_day, err_day = await limiter.check_daily_limit(uid)
    if not ok_day:
        return await message.answer(err_day, parse_mode="HTML")
        
    lower_text = text.lower()
    
    # 1. Быстрый ответ на вопросы о получении ключа / инструкции
    if any(k in lower_text for k in ["как ключ получить", "как получить ключ", "как пользоваться", "инструкция", "где ключ"]):
        await db.save_chat_message(uid, "user", text)
        await db.save_chat_message(uid, "bot", PINNED_POST_TEXT)
        return await message.answer(PINNED_POST_TEXT, parse_mode="HTML")
        
    # 2. Быстрый ответ на вопросы про Stars
    if any(k in lower_text for k in ["купить за звезды", "купить за stars", "сколько звезд", "сколько стоит"]):
        await db.save_chat_message(uid, "user", text)
        stars_reply = (
            f"⭐️ <b>Тарифы на ключи за Telegram Stars:</b>\n\n"
            f"• <b>10 ключей</b> = 15 Stars\n"
            f"• <b>Все 15 ключей</b> = 25 Stars (+ бонусный вечный ключ для приложения!)\n\n"
            f"Сколько ключей вы хотите приобрести?"
        )
        return await message.answer(stars_reply, reply_markup=get_stars_keyboard(), parse_mode="HTML")
        
    # 3. Диалог с Gemini 3.5 Flash Lite
    await db.save_chat_message(uid, "user", text)
    
    # Проверяем очередь
    queue_msg = None
    if ai_service.ai_queue.qsize() > 0:
        pos = ai_service.ai_queue.qsize() + 1
        queue_msg = await message.answer(f"⏳ <i>Вы в очереди: позиция #{pos}. Ожидайте...</i>", parse_mode="HTML")
        
    response, q_pos = await ai_service.request_ai_chat(text)
    
    if queue_msg:
        try:
            await queue_msg.delete()
        except Exception:
            pass
            
    await db.save_chat_message(uid, "bot", response)
    await message.answer(response)

async def health_check(request):
    return web.json_response({"status": "ok", "message": "LostBot Pro 24/7 is Live!"})

async def handle_api_verify(request):
    try:
        data = await request.json()
        key = data.get("key", "").strip()
        device_id = data.get("device_id", "").strip()
        if not key:
            return web.json_response({"ok": False, "message": "Введите ключ!"}, status=400)
            
        success, message = await db.verify_and_bind_app_key(key, device_id)
        return web.json_response({"ok": success, "message": message})
    except Exception as e:
        return web.json_response({"ok": False, "message": f"Ошибка сервера: {str(e)}"}, status=500)

async def start_web_server():
    import os
    port = int(os.environ.get("PORT", 8080))
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    app.router.add_post("/api/verify", handle_api_verify)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web server started on port {port}")

async def main():
    print("Инициализация базы данных...")
    await db.init_db()
    print("Запуск веб-сервера здоровья для хостинга...")
    await start_web_server()
    print("Бот запускается...")
    # Сбрасываем старые накопившиеся вебхуки
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
