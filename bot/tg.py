import asyncio
import os
import threading

from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_ACCESS_TOKEN = os.getenv("BOT_ACCESS_TOKEN", "")
if BOT_ACCESS_TOKEN == "":
    raise RuntimeError("!BOT_ACCESS_TOKEN")

GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "0"))
if GROUP_CHAT_ID == 0:
    raise RuntimeError("!GROUP_CHAT_ID")

ERROR_GROUP_CHAT_ID = int(os.getenv("ERROR_GROUP_CHAT_ID", "0"))
if ERROR_GROUP_CHAT_ID == 0:
    raise RuntimeError("!ERROR_GROUP_CHAT_ID")


async def notify_group_chat(
    text: str,
    parse_mode: str = "HTML",
    chat_id: int = GROUP_CHAT_ID,
    disable_web_page_preview: bool = True,
) -> None:
    try:
        bot = Bot(token=BOT_ACCESS_TOKEN)
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
        )
    except Exception as e:
        print(f"Failed to send message to group chat: {e}")


async def _status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command."""
    if update.effective_chat is None or update.effective_chat.id != GROUP_CHAT_ID:
        return

    from bot.utils import build_status_messages

    try:
        messages = build_status_messages()
    except Exception as e:
        messages = [f"Failed to fetch status: {e}"]

    if not messages:
        messages = ["No strategies configured."]

    for msg in messages:
        await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)  # type: ignore[union-attr]


def start_command_listener() -> None:
    """Start Telegram command polling in a daemon thread."""

    def _run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        app = Application.builder().token(BOT_ACCESS_TOKEN).build()
        app.add_handler(CommandHandler("status", _status_command))
        loop.run_until_complete(app.initialize())
        loop.run_until_complete(app.updater.start_polling(drop_pending_updates=True))  # type: ignore[union-attr]
        loop.run_until_complete(app.start())
        loop.run_forever()

    threading.Thread(target=_run, daemon=True).start()
