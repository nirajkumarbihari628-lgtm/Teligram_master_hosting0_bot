import sqlite3
import os
import threading

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hosting.db")
_db_lock = threading.Lock()


def _connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with _db_lock:
        conn = _connect()
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            credits INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            bot_limit INTEGER DEFAULT 1
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS bots (
            bot_name TEXT PRIMARY KEY,
            owner_id INTEGER NOT NULL,
            token TEXT NOT NULL,
            file_path TEXT NOT NULL,
            is_running INTEGER DEFAULT 0
        )''')
        conn.commit()
        conn.close()


def get_user(user_id):
    with _db_lock:
        conn = _connect()
        c = conn.cursor()
        c.execute("SELECT user_id, credits, is_banned, bot_limit FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        if row is None:
            c.execute("INSERT INTO users (user_id, credits, is_banned, bot_limit) VALUES (?, 0, 0, 1)", (user_id,))
            conn.commit()
            row = (user_id, 0, 0, 1)
        conn.close()
    return {"user_id": row[0], "credits": row[1], "is_banned": row[2], "bot_limit": row[3]}


def add_credits(user_id, amount):
    with _db_lock:
        conn = _connect()
        c = conn.cursor()
        get_user(user_id)  # ensure exists
        c.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        conn.close()


def deduct_credits(user_id, amount):
    with _db_lock:
        conn = _connect()
        c = conn.cursor()
        c.execute("UPDATE users SET credits = credits - ? WHERE user_id = ? AND credits >= ?",
                  (amount, user_id, amount))
        changed = c.rowcount
        conn.commit()
        conn.close()
    return changed > 0


def ban_user(user_id):
    with _db_lock:
        conn = _connect()
        c = conn.cursor()
        get_user(user_id)
        c.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()


def unban_user(user_id):
    with _db_lock:
        conn = _connect()
        c = conn.cursor()
        c.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()


def set_bot_limit(user_id, limit):
    with _db_lock:
        conn = _connect()
        c = conn.cursor()
        get_user(user_id)
        c.execute("UPDATE users SET bot_limit = ? WHERE user_id = ?", (limit, user_id))
        conn.commit()
        conn.close()


def add_bot(bot_name, owner_id, token, file_path):
    with _db_lock:
        conn = _connect()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO bots (bot_name, owner_id, token, file_path, is_running) VALUES (?, ?, ?, ?, 0)",
                  (bot_name, owner_id, token, file_path))
        conn.commit()
        conn.close()


def delete_bot(bot_name):
    with _db_lock:
        conn = _connect()
        c = conn.cursor()
        c.execute("DELETE FROM bots WHERE bot_name = ?", (bot_name,))
        conn.commit()
        conn.close()


def get_bot(bot_name):
    with _db_lock:
        conn = _connect()
        c = conn.cursor()
        c.execute("SELECT bot_name, owner_id, token, file_path, is_running FROM bots WHERE bot_name = ?", (bot_name,))
        row = c.fetchone()
        conn.close()
    if row:
        return {"bot_name": row[0], "owner_id": row[1], "token": row[2], "file_path": row[3], "is_running": row[4]}
    return None


def set_bot_running(bot_name, status):
    with _db_lock:
        conn = _connect()
        c = conn.cursor()
        c.execute("UPDATE bots SET is_running = ? WHERE bot_name = ?", (status, bot_name))
        conn.commit()
        conn.close()


def get_user_bots(owner_id):
    with _db_lock:
        conn = _connect()
        c = conn.cursor()
        c.execute("SELECT bot_name, token, file_path, is_running FROM bots WHERE owner_id = ?", (owner_id,))
        rows = c.fetchall()
        conn.close()
    return [{"bot_name": r[0], "token": r[1], "file_path": r[2], "is_running": r[3]} for r in rows]


def get_all_users():
    with _db_lock:
        conn = _connect()
        c = conn.cursor()
        c.execute("SELECT user_id, credits, is_banned, bot_limit FROM users ORDER BY user_id")
        rows = c.fetchall()
        conn.close()
    return rows


def get_all_running_bot_names():
    with _db_lock:
        conn = _connect()
        c = conn.cursor()
        c.execute("SELECT bot_name FROM bots WHERE is_running = 1")
        rows = c.fetchall()
        conn.close()
    return [r[0] for r in rows]
