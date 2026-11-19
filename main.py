import os
import io
import logging
import threading
import urllib.request

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    MessageHandler, filters,
)

from database import (
    init_db, get_user, add_credits, deduct_credits, ban_user, unban_user,
    set_bot_limit, add_bot, delete_bot, get_bot, get_user_bots, get_all_users,
)
from bot_runner import (
    start_bot_process, stop_bot_process, start_monitor,
    resume_running_bots, USER_BOTS_DIR,
)

# ============ CONFIG ============
ADMIN_ID = int(os.environ.get("7456508925", "0"))
MASTER_BOT_TOKEN = os.environ.get("9087396806:AAEiHOAHNH6_SoZg28abk-03E_8Z5wdqr8g", "")
SELF_URL = os.environ.get("SELF_URL", "")  # Render URL for self-ping

COST_ADD_BOT = 10  # प्रति बॉट जोड़ने का क्रेडिट

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)


def is_admin(uid):
    return uid == ADMIN_ID


def _banned_check(user_id):
    return get_user(user_id)["is_banned"] == 1


# ============ ADMIN COMMANDS ============
async def admin_addcredit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) < 2:
        await update.message.reply_text("उपयोग: /addcredit <user_id> <amount>")
        return
    try:
        uid = int(context.args[0]); amt = int(context.args[1])
        add_credits(uid, amt)
        await update.message.reply_text(f"✅ {uid} को {amt} क्रेडिट दिए गए।")
    except ValueError:
        await update.message.reply_text("❌ गलत फॉर्मेट।")


async def admin_removecredit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) < 2:
        await update.message.reply_text("उपयोग: /removecredit <user_id> <amount>")
        return
    try:
        uid = int(context.args[0]); amt = int(context.args[1])
        if deduct_credits(uid, amt):
            await update.message.reply_text(f"✅ {uid} से {amt} क्रेडिट निकाले गए।")
        else:
            await update.message.reply_text("❌ पर्याप्त क्रेडिट नहीं या यूज़र नहीं मिला।")
    except ValueError:
        await update.message.reply_text("❌ गलत फॉर्मेट।")


async def admin_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args:
        await update.message.reply_text("उपयोग: /ban <user_id>"); return
    try:
        uid = int(context.args[0]); ban_user(uid)
        await update.message.reply_text(f"🔨 यूज़र {uid} बैन कर दिया गया।")
    except ValueError:
        await update.message.reply_text("❌ गलत user_id।")


async def admin_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args:
        await update.message.reply_text("उपयोग: /unban <user_id>"); return
    try:
        uid = int(context.args[0]); unban_user(uid)
        await update.message.reply_text(f"✅ यूज़र {uid} अनबैन कर दिया गया।")
    except ValueError:
        await update.message.reply_text("❌ गलत user_id।")


async def admin_setlimit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if len(context.args) < 2:
        await update.message.reply_text("उपयोग: /setlimit <user_id> <limit>"); return
    try:
        uid = int(context.args[0]); lim = int(context.args[1]); set_bot_limit(uid, lim)
        await update.message.reply_text(f"✅ {uid} की बॉट लिमिट {lim} कर दी गई।")
    except ValueError:
        await update.message.reply_text("❌ गलत फॉर्मेट।")


async def admin_userinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args:
        await update.message.reply_text("उपयोग: /userinfo <user_id>"); return
    try:
        uid = int(context.args[0]); u = get_user(uid); bots = get_user_bots(uid)
        txt = (f"👤 User: `{uid}`\n💰 Credits: {u['credits']}\n"
               f"🚫 Banned: {'हाँ' if u['is_banned'] else 'नहीं'}\n"
               f"🤖 Limit: {u['bot_limit']}\n📦 Bots: {len(bots)}")
        await update.message.reply_text(txt, parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ गलत user_id।")


async def admin_allusers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    rows = get_all_users()
    if not rows:
        await update.message.reply_text("कोई यूज़र नहीं।"); return
    msg = "📋 **सभी यूज़र्स:**\n"
    for r in rows[:50]:
        msg += f"`{r[0]}` | ₹ {r[1]} | {'🚫' if r[2] else '✅'} | {r[3]} bots\n"
    if len(rows) > 50:
        msg += f"\n... और {len(rows)-50} यूज़र"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args:
        await update.message.reply_text("उपयोग: /broadcast <message>"); return
    text = " ".join(context.args)
    ok, fail = 0, 0
    for r in get_all_users():
        try:
            await context.bot.send_message(chat_id=r[0], text=f"📢 {text}")
            ok += 1
        except Exception:
            fail += 1
    await update.message.reply_text(f"✅ भेजा: {ok}, ❌ फेल: {fail}")


# ============ USER COMMANDS ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if _banned_check(uid):
        await update.message.reply_text("🚫 आप बैन हैं। एडमिन से संपर्क करें।"); return
    u = get_user(uid)
    txt = (
        f"👋 नमस्ते {update.effective_user.first_name}!\n\n"
        f"💰 क्रेडिट: {u['credits']}\n🤖 बॉट लिमिट: {u['bot_limit']}\n\n"
        "**यूज़र कमांड:**\n"
        "/upload — `.py` फाइल भेजें (फाइल डाक्यूमेंट के रूप में)\n"
        "/addbot <नाम> <टोकन> <फाइलनाम> — नया बॉट जोड़ें\n"
        "/mybots — अपने बॉट्स\n"
        "/startbot <नाम> — बॉट चलाएँ\n"
        "/stopbot <नाम> — बॉट रोकें\n"
        "/deletebot <नाम> — बॉट हटाएँ\n"
        "/credits — क्रेडिट जाँचें\n"
    )
    await update.message.reply_text(txt, parse_mode="Markdown")


async def upload_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if _banned_check(uid):
        await update.message.reply_text("🚫 आप बैन हैं।"); return
    doc = update.message.document
    if not doc or not doc.file_name.endswith(".py"):
        await update.message.reply_text("❌ केवल `.py` फाइल भेजें।"); return
    safe_name = f"{uid}_{doc.file_name}"
    path = os.path.join(USER_BOTS_DIR, safe_name)
    try:
        tg_file = await doc.get_file()
        await tg_file.download_to_drive(path)
        await update.message.reply_text(
            f"✅ फाइल सेव हो गई।\n\nअब जोड़ें:\n`/addbot <नाम> <टोकन> {safe_name}`",
            parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ अपलोड फेल: {e}")


async def add_bot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if _banned_check(uid):
        await update.message.reply_text("🚫 आप बैन हैं।"); return
    if len(context.args) < 3:
        await update.message.reply_text("उपयोग: /addbot <नाम> <टोकन> <फाइलनाम>"); return

    name, token, fname = context.args[0], context.args[1], context.args[2]

    if not name.replace("_", "").isalnum():
        await update.message.reply_text("❌ नाम में सिर्फ अक्षर/अंक/_ हो सकते हैं।"); return
    if ":" not in token:
        await update.message.reply_text("❌ गलत बॉट टोकन।"); return
    if not os.path.exists(os.path.join(USER_BOTS_DIR, fname)):
        await update.message.reply_text(f"❌ फाइल नहीं मिली: `{fname}`\nपहले /upload करें।",
                                        parse_mode="Markdown"); return

    existing = get_bot(name)
    if existing:
        await update.message.reply_text("❌ यह नाम पहले से मौजूद है।"); return

    u = get_user(uid)
    if len(get_user_bots(uid)) >= u["bot_limit"]:
        await update.message.reply_text(f"❌ लिमिट ({u['bot_limit']}) पूरी हो गई।"); return
    if not deduct_credits(uid, COST_ADD_BOT):
        await update.message.reply_text(f"❌ पर्याप्त क्रेडिट नहीं (चाहिए {COST_ADD_BOT})।"); return

    add_bot(name, uid, token, fname)
    await update.message.reply_text(f"✅ बॉट `{name}` जोड़ा गया। {COST_ADD_BOT} क्रेडिट कटे।",
                                    parse_mode="Markdown")


async def my_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if _banned_check(uid):
        await update.message.reply_text("🚫 आप बैन हैं।"); return
    bots = get_user_bots(uid)
    if not bots:
        await update.message.reply_text("आपके कोई बॉट नहीं।"); return
    msg = "📋 **आपके बॉट्स:**\n"
    for b in bots:
        st = "🟢" if b["is_running"] else "🔴"
        msg += f"{st} `{b['bot_name']}`\n"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def start_bot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if _banned_check(uid):
        await update.message.reply_text("🚫 आप बैन हैं।"); return
    if not context.args:
        await update.message.reply_text("उपयोग: /startbot <नाम>"); return
    name = context.args[0]
    b = get_bot(name)
    if not b or b["owner_id"] != uid:
        await update.message.reply_text("❌ यह बॉट आपका नहीं है।"); return
    ok, msg = start_bot_process(name)
    await update.message.reply_text(msg)


async def stop_bot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if _banned_check(uid):
        await update.message.reply_text("🚫 आप बैन हैं।"); return
    if not context.args:
        await update.message.reply_text("उपयोग: /stopbot <नाम>"); return
    name = context.args[0]
    b = get_bot(name)
    if not b or b["owner_id"] != uid:
        await update.message.reply_text("❌ यह बॉट आपका नहीं है।"); return
    ok, msg = stop_bot_process(name)
    await update.message.reply_text(msg)


async def delete_bot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if _banned_check(uid):
        await update.message.reply_text("🚫 आप बैन हैं।"); return
    if not context.args:
        await update.message.reply_text("उपयोग: /deletebot <नाम>"); return
    name = context.args[0]
    b = get_bot(name)
    if not b or b["owner_id"] != uid:
        await update.message.reply_text("❌ यह बॉट आपका नहीं है।"); return
    if b["is_running"]:
        stop_bot_process(name)
    delete_bot(name)
    await update.message.reply_text(f"🗑️ बॉट `{name}` हटा दिया गया।", parse_mode="Markdown")


async def credits_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _banned_check(update.effective_user.id):
        await update.message.reply_text("🚫 आप बैन हैं।"); return
    u = get_user(update.effective_user.id)
    await update.message.reply_text(f"💰 आपके क्रेडिट: {u['credits']}")


# ============ SELF-PING (Render sleep से बचाव) ============
def _self_ping():
    if not SELF_URL:
        return
    while True:
        try:
            urllib.request.urlopen(SELF_URL, timeout=10)
        except Exception:
            pass
        threading.Event().wait(600)  # 10 मिनट


# ============ MAIN ============
def main():
    if not MASTER_BOT_TOKEN:
        print("❌ MASTER_BOT_TOKEN environment variable सेट नहीं है!"); return
    if ADMIN_ID == 0:
        print("⚠️  ADMIN_ID सेट नहीं है! एडमिन कमांड काम नहीं करेंगे।")

    init_db()
    resume_running_bots()
    start_monitor()
    threading.Thread(target=_self_ping, daemon=True).start()

    app = Application.builder().token(MASTER_BOT_TOKEN).build()

    # Admin
    app.add_handler(CommandHandler("addcredit", admin_addcredit))
    app.add_handler(CommandHandler("removecredit", admin_removecredit))
    app.add_handler(CommandHandler("ban", admin_ban))
    app.add_handler(CommandHandler("unban", admin_unban))
    app.add_handler(CommandHandler("setlimit", admin_setlimit))
    app.add_handler(CommandHandler("userinfo", admin_userinfo))
    app.add_handler(CommandHandler("allusers", admin_allusers))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))

    # User
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addbot", add_bot_cmd))
    app.add_handler(CommandHandler("mybots", my_bots))
    app.add_handler(CommandHandler("startbot", start_bot_cmd))
    app.add_handler(CommandHandler("stopbot", stop_bot_cmd))
    app.add_handler(CommandHandler("deletebot", delete_bot_cmd))
    app.add_handler(CommandHandler("credits", credits_cmd))
    app.add_handler(MessageHandler(filters.Document.FileExtension("py"), upload_file))

    log.info("🚀 मास्टर बॉट चालू हो गया...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
