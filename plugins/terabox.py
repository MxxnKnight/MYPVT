from pyrogram import Client, filters
from pyrogram.types import Message
from plugins.config import Config
from plugins.database.database import db
from TeraboxDL import TeraboxDL
from plugins.dl_button import download_coroutine
import aiohttp
import asyncio
import time
import os
from plugins.functions.display_progress import humanbytes, progress_for_pyrogram
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from PIL import Image
from pyrogram import enums
from datetime import datetime
from plugins.script import Translation
from plugins.thumbnail import Gthumb01, Mdata01, Gthumb02, Mdata03, Mdata02
from plugins.dl_button import download_coroutine

@Client.on_message(filters.private & filters.command("set_cookie"))
async def set_cookie_handler(bot, update):
    await update.reply_text(
        "Please send me your Terabox cookie. For instructions on how to get it, please see the documentation for the `terabox-downloader` library."
    )

@Client.on_message(filters.private & filters.text & filters.reply)
async def handle_cookie_reply(bot, update):
    if update.reply_to_message.text.startswith("Please send me your Terabox cookie"):
        cookie = update.text
        await db.set_terabox_cookie(update.from_user.id, cookie)
        await update.reply_text("Your Terabox cookie has been saved.")

@Client.on_message(filters.private & filters.regex(r"https?://(?:www\.)?(?:terabox\.com|terabox\.app)\S+"))
async def terabox_downloader(bot, update):
    cookie = await db.get_terabox_cookie(update.from_user.id)
    if not cookie:
        await update.reply_text("You have not set your Terabox cookie yet. Please use the /set_cookie command to set it.")
        return

    terabox = TeraboxDL(cookie)
    sent_message = await update.reply_text("Fetching download link...")

        loop = asyncio.get_event_loop()
        file_info = await loop.run_in_executor(None, terabox.get_file_info, update.text, True)

    if "error" in file_info:
        await sent_message.edit(f"Error: {file_info['error']}")
        return

    download_link = file_info["download_link"]
    custom_file_name = file_info["file_name"]

    tmp_directory_for_each_user = Config.DOWNLOAD_LOCATION + "/" + str(update.from_user.id)
    if not os.path.isdir(tmp_directory_for_each_user):
        os.makedirs(tmp_directory_for_each_user)

    download_directory = tmp_directory_for_each_user + "/" + custom_file_name

    async with aiohttp.ClientSession() as session:
        c_time = time.time()
        try:
            await download_coroutine(
                bot,
                session,
                download_link,
                download_directory,
                update.chat.id,
                sent_message.id,
                c_time
            )
        except asyncio.TimeoutError:
            await bot.edit_message_text(
                text="Download timed out.",
                chat_id=update.chat.id,
                message_id=sent_message.id
            )
            return False

    if os.path.exists(download_directory):
        start_time = time.time()
        thumb_image_path = None
        if (await db.get_upload_as_doc(update.from_user.id)) is False:
            thumbnail = await Gthumb01(bot, update)
            await bot.send_document(
                chat_id=update.chat.id,
                document=download_directory,
                thumb=thumbnail,
                caption=custom_file_name,
                progress=progress_for_pyrogram,
                progress_args=(
                    "Uploading...",
                    sent_message,
                    start_time
                )
            )
        else:
             width, height, duration = await Mdata01(download_directory)
             thumb_image_path = await Gthumb02(bot, update, duration, download_directory)
             await bot.send_video(
                chat_id=update.chat.id,
                video=download_directory,
                caption=custom_file_name,
                duration=duration,
                width=width,
                height=height,
                supports_streaming=True,
                thumb=thumb_image_path,
                progress=progress_for_pyrogram,
                progress_args=(
                    "Uploading...",
                    sent_message,
                    start_time
                )
            )
        try:
            os.remove(download_directory)
            if thumb_image_path and os.path.exists(thumb_image_path):
                os.remove(thumb_image_path)
        except:
            pass
        await sent_message.delete()
    else:
        await sent_message.edit("Download failed.")
