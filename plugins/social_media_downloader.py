from pyrogram import Client, filters
from pyrogram.types import Message
import yt_dlp
import os
from plugins.config import Config
from plugins.functions.display_progress import progress_for_pyrogram
from datetime import datetime
import time
from plugins.dl_button import download_coroutine

@Client.on_message(filters.private & filters.regex(r"https?://(?:www\.)?(?:pinterest\.com|twitter\.com|instagram\.com|reddit\.com)\S+"))
async def social_media_downloader(bot, update):
    await download_media(bot, update, update.text)

async def download_media(bot, update, url):
    sent_message = await update.reply_text("Processing link...")

    ydl_opts = {
        'outtmpl': os.path.join(Config.DOWNLOAD_LOCATION, '%(title)s.%(ext)s'),
        'progress_hooks': [lambda d: on_progress(d, bot, sent_message)],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

            # Upload the downloaded file
            await upload_file(bot, update, filename, sent_message)
        except Exception as e:
            await sent_message.edit(f"Error: {e}")

progress_times = {}

async def on_progress(d, bot, message):
    message_id = message.id
    if d['status'] == 'downloading':
        if message_id not in progress_times:
            progress_times[message_id] = 0

        current_time = time.time()
        if current_time - progress_times[message_id] > 2:
            total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate')
            if total_bytes:
                downloaded_bytes = d.get('downloaded_bytes')
                percentage = downloaded_bytes * 100 / total_bytes
                await message.edit(f"Downloading: {int(percentage)}%")
            progress_times[message_id] = current_time

async def upload_file(bot, update, filename, sent_message):
    start_time = time.time()
    await bot.send_document(
        chat_id=update.chat.id,
        document=filename,
        caption=os.path.basename(filename),
        progress=progress_for_pyrogram,
        progress_args=(
            "Uploading...",
            sent_message,
            start_time
        )
    )
    os.remove(filename)
    await sent_message.delete()
    if sent_message.id in progress_times:
        del progress_times[sent_message.id]
