import os

from telegram import Bot

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
