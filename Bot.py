<meta charset="utf-8"><pre><code class="language-python">import os, sqlite3, time
from telegram import Update
from telegram.constants import ChatMemberStatus
from telegram.ext import (ApplicationBuilder, MessageHandler,
                          CommandHandler, ContextTypes, filters)

TOKEN = os.environ.get("BOT_TOKEN", "PUT_YOUR_TOKEN")

db = sqlite3.connect("activity.db", check_same_thread=False)
db.execute("""CREATE TABLE IF NOT EXISTS act (
    chat_id INTEGER, user_id INTEGER, last_ts INTEGER,
    PRIMARY KEY (chat_id, user_id))""")
db.commit()

def touch(chat_id, user_id):
    db.execute("INSERT OR REPLACE INTO act VALUES (?,?,?)",
               (chat_id, user_id, int(time.time())))
    db.commit()

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Salam! Zidni f group w 3titni admin (Ban users).\n"
        "/purge 30 = preview\n/purge 30 go = tard li machi active")

async def track(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u, c = update.effective_user, update.effective_chat
    if u and not u.is_bot:
        touch(c.id, u.id)

async def track_joins(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    for m in update.effective_message.new_chat_members:
        if not m.is_bot:
            touch(update.effective_chat.id, m.id)

async def purge(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == "private":
        return await update.message.reply_text("Dir had l-commande f group.")

    caller = await chat.get_member(update.effective_user.id)
    if caller.status not in (ChatMemberStatus.ADMINISTRATOR,
                             ChatMemberStatus.OWNER):
        return await update.message.reply_text("Ghir l-admins.")

    try:
        days = int(ctx.args[0]) if ctx.args else 30
    except ValueError:
        return await update.message.reply_text("Mital: /purge 30")
    do_it = len(ctx.args) &gt; 1 and ctx.args[1] == "go"
    limit = int(time.time()) - days * 86400

    rows = db.execute(
        "SELECT user_id FROM act WHERE chat_id=? AND last_ts&lt;?",
        (chat.id, limit)).fetchall()

    removed, names = 0, []
    for (uid,) in rows:
        try:
            m = await chat.get_member(uid)
            if m.status in (ChatMemberStatus.ADMINISTRATOR,
                            ChatMemberStatus.OWNER,
                            ChatMemberStatus.LEFT,
                            ChatMemberStatus.BANNED):
                continue
            names.append(m.user.full_name)
            if do_it:
                await chat.ban_member(uid)
                await chat.unban_member(uid)
                db.execute("DELETE FROM act WHERE chat_id=? AND user_id=?",
                           (chat.id, uid))
                removed += 1
        except Exception as e:
            print("error", uid, e)
    db.commit()

    if do_it:
        await update.message.reply_text(f"Tkhrjo {removed} members.")
    else:
        await update.message.reply_text(
            f"{len(names)} machi active mn {days} yom:\n" +
            "\n".join(names[:50]) +
            f"\n\nBach tkhrjhom: /purge {days} go")

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("purge", purge))
app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, track_joins))
app.add_handler(MessageHandler(filters.ChatType.GROUPS &amp; ~filters.COMMAND, track))
app.run_polling()
</code></pre>
