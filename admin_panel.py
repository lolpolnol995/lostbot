from aiogram import Bot, Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import ADMIN_ID, SECRET_ADMIN_PASS
from database import (
    get_maintenance_mode, set_maintenance_mode, get_keys_stats, 
    add_keys, get_active_users, get_user_chat_history, get_all_user_ids
)

admin_router = Router()

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_manual_reply = State()
    target_user_id = State()

def get_admin_keyboard(is_maintenance: bool) -> InlineKeyboardMarkup:
    m_text = "🟢 Открыть для всех" if is_maintenance else "🔴 Включить режим тестов (Закрыть)"
    kb = [
        [InlineKeyboardButton(text=f"Статус: {m_text}", callback_data="toggle_maintenance")],
        [InlineKeyboardButton(text="📢 Сделать рассылку всем", callback_data="start_broadcast")],
        [InlineKeyboardButton(text="📂 Чаты пользователей", callback_data="view_chats:0")],
        [InlineKeyboardButton(text="🔑 База ключей", callback_data="view_keys_info")],
        [InlineKeyboardButton(text="🔙 Вернуться в меню пользователя", callback_data="exit_to_user_menu")],
        [InlineKeyboardButton(text="❌ Закрыть панель", callback_data="close_admin")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

async def show_admin_panel(message: Message, bot: Bot, user_id: int = None):
    uid = user_id if user_id is not None else (message.from_user.id if message.from_user else 0)
    if uid != ADMIN_ID:
        return
    is_m = await get_maintenance_mode()
    total, avail, issued = await get_keys_stats()
    all_users = await get_all_user_ids()
    
    status_str = "🔒 ЗАКРЫТ (Только админ)" if is_m else "🌐 ОТКРЫТ (Для всех пользователей)"
    text = (
        f"👑 <b>ПАНЕЛЬ АДМИНИСТРАТОРА LostBot Pro</b>\n\n"
        f"<b>Режим работы бота:</b> {status_str}\n"
        f"<b>Всего пользователей в БД:</b> {len(all_users)}\n"
        f"<b>Ключи:</b> всего {total} | доступно {avail} | выдано {issued}\n\n"
        f"Выберите действие ниже:"
    )
    try:
        await message.edit_text(text, reply_markup=get_admin_keyboard(is_m), parse_mode="HTML")
    except Exception:
        await message.answer(text, reply_markup=get_admin_keyboard(is_m), parse_mode="HTML")

# --- Переключение режима обслуживания ---
@admin_router.callback_query(F.data == "toggle_maintenance")
async def cb_toggle_maintenance(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("Доступ запрещен", show_alert=True)
        
    current = await get_maintenance_mode()
    new_mode = not current
    await set_maintenance_mode(new_mode)
    
    mode_text = "Закрытый режим включен (доступ только вам)" if new_mode else "Открытый режим включен (доступ открыт всем)"
    await call.answer(f"Статус обновлен: {mode_text}", show_alert=True)
    
    total, avail, issued = await get_keys_stats()
    all_users = await get_all_user_ids()
    status_str = "🔒 ЗАКРЫТ (Только админ)" if new_mode else "🌐 ОТКРЫТ (Для всех пользователей)"
    text = (
        f"👑 <b>ПАНЕЛЬ АДМИНИСТРАТОРА LostBot Pro</b>\n\n"
        f"<b>Режим работы бота:</b> {status_str}\n"
        f"<b>Всего пользователей в БД:</b> {len(all_users)}\n"
        f"<b>Ключи:</b> всего {total} | доступно {avail} | выдано {issued}\n\n"
        f"Выберите действие ниже:"
    )
    await call.message.edit_text(text, reply_markup=get_admin_keyboard(new_mode), parse_mode="HTML")

# --- Информация о ключах ---
@admin_router.callback_query(F.data == "view_keys_info")
async def cb_view_keys_info(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("Доступ запрещен")
        
    total, avail, issued = await get_keys_stats()
    text = (
        f"🔑 <b>СТАТИСТИКА КЛЮЧЕЙ:</b>\n\n"
        f"• Всего ключей в базе: <b>{total}</b>\n"
        f"• Доступно для выдачи: <b>{avail}</b>\n"
        f"• Уже выдано: <b>{issued}</b>\n\n"
        f"💡 <i>Чтобы добавить новую пачку ключей, отправьте команду:</i>\n"
        f"<code>/addkeys KEY1 KEY2 KEY3</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Сгенерировать 20-значный ключ", callback_data="admin_gen_key")],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_admin")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

from key_generator import generate_app_key

@admin_router.callback_query(F.data == "admin_gen_key")
async def cb_admin_gen_key(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("Доступ запрещен")
    new_k = generate_app_key()
    await call.message.answer(
        f"🎲 <b>Сгенерирован новый 20-значный ключ приложения:</b>\n\n"
        f"<code>{new_k}</code>\n\n"
        f"Этот ключ моментально валидируется приложением LostBot Pro без интернета!",
        parse_mode="HTML"
    )
    await call.answer("Ключ сгенерирован!")

# --- Просмотр чатов пользователей ---
@admin_router.callback_query(F.data.startswith("view_chats:"))
async def cb_view_chats(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("Доступ запрещен")
        
    page = int(call.data.split(":")[1])
    page_size = 5
    offset = page * page_size
    users = await get_active_users(limit=page_size + 1, offset=offset)
    
    has_next = len(users) > page_size
    current_users = users[:page_size]
    
    if not current_users:
        text = "📂 <b>Чаты пользователей</b>\n\nПока нет сохраненных переписок."
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_admin")]
        ])
        return await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        
    text = f"📂 <b>Чаты пользователей (Страница {page + 1}):</b>\nНажмите на пользователя для просмотра диалога:"
    kb = []
    
    for u_id, username, count in current_users:
        u_name = f"@{username}" if username else f"ID: {u_id}"
        btn_text = f"👤 {u_name} ({count} сооб.)"
        kb.append([InlineKeyboardButton(text=btn_text, callback_data=f"user_chat:{u_id}:0")])
        
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"view_chats:{page - 1}"))
    if has_next:
        nav_row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"view_chats:{page + 1}"))
    if nav_row:
        kb.append(nav_row)
        
    kb.append([InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_admin")])
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

# --- Просмотр переписки конкретного пользователя ---
@admin_router.callback_query(F.data.startswith("user_chat:"))
async def cb_view_user_chat(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("Доступ запрещен")
        
    parts = call.data.split(":")
    user_id = int(parts[1])
    page = int(parts[2])
    page_size = 8
    offset = page * page_size
    
    messages = await get_user_chat_history(user_id, limit=page_size, offset=offset)
    
    if not messages:
        chat_text = "<i>Нет истории сообщений.</i>"
    else:
        lines = []
        for role, msg, t in messages:
            r_icon = "👤" if role == "user" else "🤖"
            lines.append(f"{r_icon} <b>{role.upper()}</b>: {msg}")
        chat_text = "\n\n".join(lines)
        
    text = (
        f"💬 <b>Диалог с пользователем ID: {user_id}</b>\n\n"
        f"{chat_text}"
    )
    
    kb = [
        [InlineKeyboardButton(text="✉️ Написать пользователю", callback_data=f"reply_to:{user_id}")],
        [
            InlineKeyboardButton(text="⬅️ Предыдущие", callback_data=f"user_chat:{user_id}:{page + 1}"),
            InlineKeyboardButton(text="Следующие ➡️", callback_data=f"user_chat:{user_id}:{max(0, page - 1)}")
        ],
        [InlineKeyboardButton(text="🔙 К списку чатов", callback_data="view_chats:0")]
    ]
    try:
        await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    except TelegramBadRequest:
        await call.answer()

import support_chat

@admin_router.callback_query(F.data.startswith("end_chat:"))
async def cb_end_chat(call: CallbackQuery, bot: Bot):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("Доступ запрещен")
    target_uid = int(call.data.split(":")[1])
    support_chat.end_session(target_uid)
    try:
        await bot.send_message(
            target_uid,
            "✅ <b>Диалог с разработчиком завершен.</b>\n"
            "Спасибо за обращение! Если у вас появятся новые вопросы, бот снова готов помочь.",
            parse_mode="HTML"
        )
    except Exception:
        pass
    try:
        await call.message.edit_text(
            f"🔴 <b>Диалог с пользователем [ID: <code>{target_uid}</code>] завершен.</b>\n"
            f"Бот вернулся в стандартный режим.",
            parse_mode="HTML"
        )
    except Exception:
        await call.message.answer(
            f"🔴 <b>Диалог с пользователем [ID: <code>{target_uid}</code>] завершен.</b>",
            parse_mode="HTML"
        )
    await call.answer("Диалог завершен")

# --- Ручной ответ пользователю ---
@admin_router.callback_query(F.data.startswith("reply_to:"))
async def cb_reply_to_user(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("Доступ запрещен")
        
    target_uid = int(call.data.split(":")[1])
    await state.set_state(AdminStates.waiting_for_manual_reply)
    await state.update_data(target_user_id=target_uid)
    
    await call.message.answer(
        f"✍️ <b>Введите текст ответа для пользователя ID: {target_uid}:</b>\n\n"
        f"(Или отправьте /cancel для отмены)"
    )
    await call.answer()

@admin_router.message(AdminStates.waiting_for_manual_reply)
async def process_manual_reply(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id != ADMIN_ID:
        return
    if message.text and message.text.startswith("/cancel"):
        await state.clear()
        return await message.answer("❌ Ответ отменен.")
        
    data = await state.get_data()
    target_uid = data.get("target_user_id")
    await state.clear()
    
    try:
        user_msg = (
            f"👨‍💻 <b>С вами на связи разработчик (@Lolpolnol):</b>\n\n"
            f"{message.text or 'Вам прислано вложение.'}\n\n"
            f"<i>(Вы можете отвечать прямо сюда, ваши сообщения дойдут разработчику напрямую)</i>"
        )
        if message.text:
            await bot.send_message(target_uid, user_msg, parse_mode="HTML")
        elif message.photo:
            await bot.send_photo(target_uid, message.photo[-1].file_id, caption=user_msg, parse_mode="HTML")
            
        support_chat.start_session(target_uid)
        end_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛑 Завершить диалог", callback_data=f"end_chat:{target_uid}")]
        ])
        await message.answer(
            f"🟢 <b>Прямой диалог с пользователем [ID: <code>{target_uid}</code>] открыт!</b>\n\n"
            f"• Отправлено: <i>\"{message.text}\"</i>\n"
            f"• Все следующие сообщения пользователя будут приходить сюда.\n"
            f"• Все ваши сообщения будут отправляться ему (нейросеть отключена).\n\n"
            f"Для завершения нажмите кнопку ниже или отправьте /end.",
            reply_markup=end_kb,
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Не удалось отправить сообщение: {e}")

# --- Рассылка всем пользователям ---
@admin_router.callback_query(F.data == "start_broadcast")
async def cb_start_broadcast(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("Доступ запрещен")
        
    await state.set_state(AdminStates.waiting_for_broadcast)
    await call.message.answer(
        "📢 <b>Режим рассылки:</b>\n"
        "Отправьте сообщение (текст или с фото), которое вы хотите разослать всем пользователям бота.\n\n"
        "Отправьте /cancel для отмены."
    )
    await call.answer()

@admin_router.message(AdminStates.waiting_for_broadcast)
async def process_broadcast(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id != ADMIN_ID:
        return
    if message.text and message.text.startswith("/cancel"):
        await state.clear()
        return await message.answer("❌ Рассылка отменена.")
        
    await state.clear()
    users = await get_all_user_ids()
    status_msg = await message.answer(f"⏳ Начинаем рассылку для {len(users)} пользователей...")
    
    sent = 0
    errors = 0
    for uid in users:
        try:
            if message.text:
                await bot.send_message(uid, message.text, parse_mode="HTML")
            elif message.photo:
                await bot.send_photo(uid, message.photo[-1].file_id, caption=message.caption or "", parse_mode="HTML")
            sent += 1
        except Exception:
            errors += 1
            
    await status_msg.edit_text(f"✅ <b>Рассылка завершена!</b>\nУспешно доставлено: {sent}\nНе удалось доставить (блок): {errors}", parse_mode="HTML")

# --- Возврат в главное меню админки ---
@admin_router.callback_query(F.data == "back_to_admin")
async def cb_back_to_admin(call: CallbackQuery, bot: Bot):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("Доступ запрещен")
    is_m = await get_maintenance_mode()
    total, avail, issued = await get_keys_stats()
    all_users = await get_all_user_ids()
    status_str = "🔒 ЗАКРЫТ (Только админ)" if is_m else "🌐 ОТКРЫТ (Для всех пользователей)"
    text = (
        f"👑 <b>ПАНЕЛЬ АДМИНИСТРАТОРА LostBot Pro</b>\n\n"
        f"<b>Режим работы бота:</b> {status_str}\n"
        f"<b>Всего пользователей в БД:</b> {len(all_users)}\n"
        f"<b>Ключи:</b> всего {total} | доступно {avail} | выдано {issued}\n\n"
        f"Выберите действие ниже:"
    )
    await call.message.edit_text(text, reply_markup=get_admin_keyboard(is_m), parse_mode="HTML")

@admin_router.callback_query(F.data == "exit_to_user_menu")
async def cb_exit_to_user_menu(call: CallbackQuery):
    from config import CHANNEL_USERNAME
    uid = call.from_user.id
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
        [InlineKeyboardButton(text="⭐️ Купить ключи за Stars", callback_data="show_stars_buy")],
        [InlineKeyboardButton(text="📢 Официальный канал", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")]
    ]
    if uid == ADMIN_ID:
        kb.append([InlineKeyboardButton(text="👑 Открыть панель управления", callback_data="open_admin_panel")])
    await call.message.edit_text(welcome_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@admin_router.callback_query(F.data == "close_admin")
async def cb_close_admin(call: CallbackQuery):
    await call.message.delete()
