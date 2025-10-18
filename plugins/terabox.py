from pyrogram import Client, filters
from pyrogram.types import Message
from plugins.config import Config
from plugins.database.database import db
import aiohttp
import asyncio
import time
import os
import logging
from plugins.functions.display_progress import humanbytes, progress_for_pyrogram
from plugins.thumbnail import Gthumb01, Mdata01, Gthumb02
from plugins.dl_button import download_coroutine
import requests
import json

# Set up logging
logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

@Client.on_message(filters.private & filters.command("set_cookie"))
async def set_cookie_handler(bot, update):
    await update.reply_text(
        "Please reply to this message with your Terabox cookie (ndus value).\n\n"
        "To get your cookie:\n"
        "1. Login to Terabox in your browser\n"
        "2. Open Developer Tools (F12)\n"
        "3. Go to Application/Storage > Cookies\n"
        "4. Find and copy the 'ndus' cookie value"
    )

@Client.on_message(filters.private & filters.text & filters.reply)
async def handle_cookie_reply(bot, update):
    if update.reply_to_message and "reply to this message with your Terabox cookie" in update.reply_to_message.text:
        cookie = f"ndus={update.text.strip()}"
        await db.set_terabox_cookie(update.from_user.id, cookie)
        await update.reply_text("✅ Your Terabox cookie has been saved successfully!")

def get_formatted_size(size_in_bytes):
    if size_in_bytes is None:
        return "N/A"
    power = 1024
    n = 0
    power_labels = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size_in_bytes >= power and n < len(power_labels):
        size_in_bytes /= power
        n += 1
    return f"{size_in_bytes:.2f} {power_labels[n]}B"

@Client.on_message(filters.private & filters.regex(r"https?://(?:www\.)?(?:1024tera\.com|terabox\.com|terabox\.app|teraboxlink\.com|mirrobox\.com|nephobox\.com|4funbox\.com|momerybox\.com|teraboxapp\.com|gibibox\.com|goaibox\.com|terasharelink\.com|terafileshare\.com)\S+"))
async def terabox_downloader(bot, update):
    logger.info(f"Received terabox link from user {update.from_user.id}: {update.text}")
    sent_message = await update.reply_text("🔄 Resolving Terabox link, please wait...")

    try:
        cookie = await db.get_terabox_cookie(update.from_user.id)
        if not cookie:
            await sent_message.edit("You haven't set your Terabox cookie. Please use /set_cookie to set it.")
            return

        headers = {'Cookie': cookie}
        api_url = f"https://terabox-debrid.vercel.app/api?url={update.text}"

        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        data = response.json()

        if not data.get("success"):
            await sent_message.edit(f"❌ Error: {data.get('error', 'Failed to retrieve link details.')}")
            return

        await sent_message.edit("✅ Link resolved successfully. Starting download...")

        for item in data["data"]:
            item_message = await bot.send_message(update.chat.id, f"📥 Downloading: `{item['title']}`")

            download_directory = os.path.join(Config.DOWNLOAD_LOCATION, str(update.from_user.id), item['title'])
            os.makedirs(os.path.dirname(download_directory), exist_ok=True)

            async with aiohttp.ClientSession() as session:
                try:
                    await download_coroutine(bot, session, item['download_link'], download_directory, update.chat.id, item_message.id, time.time())
                except asyncio.TimeoutError:
                    await item_message.edit("⏱️ Download timed out.")
                    continue

            if not os.path.exists(download_directory):
                await item_message.edit("❌ Download failed.")
                continue

            await item_message.edit("📤 Uploading to Telegram...")

            try:
                if await db.get_upload_as_doc(update.from_user.id):
                    thumbnail = await Gthumb01(bot, update)
                    await bot.send_document(
                        chat_id=update.chat.id,
                        document=download_directory,
                        thumb=thumbnail,
                        caption=item['title'],
                        progress=progress_for_pyrogram,
                        progress_args=("Uploading...", item_message, time.time())
                    )
                else:
                    width, height, duration = await Mdata01(download_directory)
                    thumb_path = await Gthumb02(bot, update, duration, download_directory)
                    await bot.send_video(
                        chat_id=update.chat.id,
                        video=download_directory,
                        caption=item['title'],
                        duration=duration,
                        width=width,
                        height=height,
                        supports_streaming=True,
                        thumb=thumb_path,
                        progress=progress_for_pyrogram,
                        progress_args=("Uploading...", item_message, time.time())
                    )
            finally:
                if os.path.exists(download_directory):
                    os.remove(download_directory)
                if 'thumb_path' in locals() and os.path.exists(thumb_path):
                    os.remove(thumb_path)

            await item_message.delete()

        await sent_message.edit("✅ All files processed.")

    except requests.exceptions.RequestException as e:
        await sent_message.edit(f"❌ Network Error: {e}")
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        await sent_message.edit("❌ An unexpected error occurred.")