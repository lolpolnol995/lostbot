# support_chat.py - Управление интерактивным режимом диалога Админ <-> Пользователь

active_admin_session = None
active_user_sessions = set()

def get_active_admin_target():
    global active_admin_session
    return active_admin_session

def is_user_in_session(user_id: int):
    global active_user_sessions
    return user_id in active_user_sessions

def start_session(user_id: int):
    global active_admin_session, active_user_sessions
    active_admin_session = user_id
    active_user_sessions.add(user_id)

def end_session(user_id: int = None):
    global active_admin_session, active_user_sessions
    target = user_id if user_id is not None else active_admin_session
    if target:
        active_user_sessions.discard(target)
        if active_admin_session == target:
            active_admin_session = None
        return target
    return None
