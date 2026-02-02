"""Telegram message formatting utilities."""

import telegramify_markdown


async def send_markdown(bot_or_msg, text: str, *, chat_id: int | None = None):
    """Send markdown text to Telegram, converting to MarkdownV2.

    bot_or_msg: a Bot instance (pass chat_id) or an Update.message (calls reply_text).
    """
    converted = telegramify_markdown.markdownify(text)
    chunks = [converted[i : i + 4000] for i in range(0, len(converted), 4000)]
    for chunk in chunks:
        if chat_id is not None:
            await bot_or_msg.send_message(chat_id=chat_id, text=chunk, parse_mode="MarkdownV2")
        else:
            await bot_or_msg.reply_text(chunk, parse_mode="MarkdownV2")
