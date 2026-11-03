
import os
import sqlite3
import logging
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ChatMemberHandler,
    ContextTypes,
    filters,
)

# Accept either environment variable name
TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("BOT_TOKEN")
)

if not TOKEN:
    raise RuntimeError("BOT_TOKEN or TELEGRAM_BOT_TOKEN is missing")

INACTIVE_DAYS = 3
WARNING_HOURS = 1
CHECK_INTERVAL = 60
DB_PATH = "jack_activity.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

db = sqlite3.connect(DB_PATH, check_same_thread=False)

db.execute("""
CREATE TABLE IF NOT EXISTS members (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    last_seen TEXT NOT NULL,
    warned_at TEXT DEFAULT NULL,
    PRIMARY KEY (chat_id, user_id)
)
""")
db.commit()


def now():
    return datetime.now(timezone.utc)


def save_activity(chat_id, user_id):
    """Save activity without sending any reply."""
    db.execute("""
        INSERT INTO members
        (chat_id, user_id, last_seen, warned_at)
        VALUES (?, ?, ?, NULL)

        ON CONFLICT(chat_id, user_id)
        DO UPDATE SET
            last_seen = excluded.last_seen,
            warned_at = NULL
    """, (chat_id, user_id, now().isoformat()))

    db.commit()


def delete_member(chat_id, user_id):
    db.execute("""
        DELETE FROM members
        WHERE chat_id=? AND user_id=?
    """, (chat_id, user_id))
    db.commit()


async def track_messages(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return

    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    # Never track bot messages.
    if user.is_bot:
        return

    # Ignore Telegram service messages.
    if message.new_chat_members or message.left_chat_member:
        return

    # Only record activity. NO reply, NO echo, NO forwarding.
    save_activity(chat.id, user.id)


async def track_join_leave(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    change = update.chat_member

    if not change:
        return

    chat_id = update.effective_chat.id
    user = change.new_chat_member.user

    if user.is_bot:
        return

    old_status = change.old_chat_member.status
    new_status = change.new_chat_member.status

    # A member joined or rejoined.
    if (
        old_status in ("left", "kicked")
        and new_status in ("member", "restricted")
    ):
        save_activity(chat_id, user.id)

    # A member left or was removed.
    elif new_status in ("left", "kicked"):
        delete_member(chat_id, user.id)


async def check_admin(context, chat_id, user_id):
    member = await context.bot.get_chat_member(
        chat_id, user_id
    )

    return member.status in ("administrator", "creator")


async def check_inactive(
    context: ContextTypes.DEFAULT_TYPE
):
    current = now()

    rows = db.execute("""
        SELECT chat_id, user_id, last_seen, warned_at
        FROM members
    """).fetchall()

    for chat_id, user_id, last_seen, warned_at in rows:
        try:
            last_activity = datetime.fromisoformat(last_seen)

            if current - last_activity < timedelta(days=INACTIVE_DAYS):
                continue

            member = await context.bot.get_chat_member(
                chat_id, user_id
            )

            if member.status in ("left", "kicked"):
                delete_member(chat_id, user_id)
                continue

            # Administrators and owners are never removed.
            if member.status in ("administrator", "creator"):
                continue

            # First warning after 3 days.
            if not warned_at:
                name = member.user.first_name or "خويا"

                await context.bot.send_message(
                    chat_id,
                    f"سلام {name} 👋\n\n"
                    "بقالك 1H، إلا ما صيفطتي حتى رسالة "
                    "غادي تخرج من GROUP JACK.\n\n"
                    "JACK 🛡️"
                )

                db.execute("""
                    UPDATE members
                    SET warned_at=?
                    WHERE chat_id=? AND user_id=?
                """, (
                    current.isoformat(),
                    chat_id,
                    user_id
                ))
                db.commit()
                continue

            warning_time = datetime.fromisoformat(warned_at)

            if current - warning_time < timedelta(hours=WARNING_HOURS):
                continue

            # Check again before removing.
            member = await context.bot.get_chat_member(
                chat_id, user_id
            )

            if member.status in ("administrator", "creator"):
                continue

            if member.status in ("left", "kicked"):
                delete_member(chat_id, user_id)
                continue

            # Remove from group without permanent ban.
            await context.bot.ban_chat_member(
                chat_id, user_id
            )

            await context.bot.unban_chat_member(
                chat_id,
                user_id,
                only_if_banned=True
            )

            logging.info(
                "Removed inactive user %s from group %s",
                user_id,
                chat_id
            )

            delete_member(chat_id, user_id)

        except Exception:
            logging.exception(
                "Error checking user %s in group %s",
                user_id,
                chat_id
            )


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Listen to group messages, but never reply to them.
    app.add_handler(
        MessageHandler(filters.ALL, track_messages)
    )

    # Track users who join or leave.
    app.add_handler(
        ChatMemberHandler(
            track_join_leave,
            ChatMemberHandler.CHAT_MEMBER
        )
    )

    # Check inactivity every minute.
    app.job_queue.run_repeating(
        check_inactive,
        interval=CHECK_INTERVAL,
        first=10
    )

    logging.info("JACK Anti-Inactive Bot started!")

    app.run_polling(
        allowed_updates=[
            "message",
            "chat_member"
        ]
    )


if __name__ == "__main__":
    main()
