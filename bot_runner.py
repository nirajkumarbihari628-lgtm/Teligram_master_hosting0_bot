import os
import sys
import time
import signal
import subprocess
import threading

from database import get_bot, set_bot_running, get_all_running_bot_names

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_BOTS_DIR = os.path.join(BASE_DIR, "user_bots")
os.makedirs(USER_BOTS_DIR, exist_ok=True)

running_processes = {}   # {bot_name: Popen}
restart_counts = {}      # {bot_name: int}
MAX_RESTARTS = 3
_monitor_started = False


def _safe_path(filename):
    """Path traversal से बचाव"""
    full = os.path.abspath(os.path.join(USER_BOTS_DIR, filename))
    if not full.startswith(os.path.abspath(USER_BOTS_DIR) + os.sep):
        return None
    return full


def start_bot_process(bot_name):
    bot = get_bot(bot_name)
    if not bot:
        return False, "❌ बॉट डेटाबेस में नहीं मिला।"
    if bot_name in running_processes and running_processes[bot_name].poll() is None:
        return False, "⚠️ बॉट पहले से चल रहा है।"

    file_path = _safe_path(bot["file_path"])
    if not file_path or not os.path.exists(file_path):
        return False, f"❌ फाइल नहीं मिली: {bot['file_path']}"

    env = os.environ.copy()
    env["BOT_TOKEN"] = bot["token"]
    env["PYTHONUNBUFFERED"] = "1"

    try:
        process = subprocess.Popen(
            [sys.executable, "-u", file_path],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        running_processes[bot_name] = process
        restart_counts[bot_name] = 0
        set_bot_running(bot_name, 1)
        return True, f"✅ बॉट `{bot_name}` शुरू हो गया (PID: {process.pid})"
    except Exception as e:
        return False, f"❌ त्रुटि: {e}"


def stop_bot_process(bot_name):
    if bot_name not in running_processes:
        set_bot_running(bot_name, 0)
        return False, "⚠️ बॉट नहीं चल रहा।"
    process = running_processes.pop(bot_name)
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except Exception:
        try:
            process.terminate()
        except Exception:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except Exception:
            process.kill()
    set_bot_running(bot_name, 0)
    return True, f"🛑 बॉट `{bot_name}` बंद कर दिया गया।"


def is_bot_alive(bot_name):
    p = running_processes.get(bot_name)
    return p is not None and p.poll() is None


def _monitor_loop():
    """क्रैश हुए बॉट्स को ऑटो-रीस्टार्ट करता है (max 3 बार)।"""
    while True:
        time.sleep(30)
        for bot_name, process in list(running_processes.items()):
            if process.poll() is not None:  # crashed
                del running_processes[bot_name]
                set_bot_running(bot_name, 0)
                count = restart_counts.get(bot_name, 0)
                if count < MAX_RESTARTS:
                    restart_counts[bot_name] = count + 1
                    ok, msg = start_bot_process(bot_name)
                    print(f"[MONITOR] {bot_name} restart #{count+1}: {msg}")
                else:
                    print(f"[MONITOR] {bot_name} crashed {MAX_RESTARTS} times — giving up.")


def start_monitor():
    global _monitor_started
    if _monitor_started:
        return
    _monitor_started = True
    t = threading.Thread(target=_monitor_loop, daemon=True)
    t.start()


def resume_running_bots():
    """Render restart होने पर पहले से चल रहे बॉट्स को फिर से शुरू करें"""
    for name in get_all_running_bot_names():
        start_bot_process(name)
