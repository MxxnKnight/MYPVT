from pyrogram import Client, filters
from pyrogram.types import Message
from plugins.config import Config
from plugins.database.database import db
from plugins.terafetch_v2_utils import TeraFetchV2
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

@Client.on_message(filters.private & filters.regex(r"https?://(?:www\.)?(?:terabox\.com|terabox\.app|teraboxlink\.com)\S+"))
async def terabox_downloader(bot, update):
    logger.info(f"Received terabox link from user {update.from_user.id}: {update.text}")
    cookie = await db.get_terabox_cookie(update.from_user.id)
    # The new method might work even without a cookie, so we don't require it.
    # We'll pass it if it exists.

    sent_message = await update.reply_text("Resolving link, please wait...")

    loop = asyncio.get_running_loop()
    try:
        terafetch = TeraFetchV2(cookie)
        file_meta = await loop.run_in_executor(None, terafetch.resolve, update.text)

        if "error" in file_meta or not file_meta.get("dlink"):
            error_message = file_meta.get("error", "Could not resolve download link.")
            await sent_message.edit(f"Error: {error_message}")
            return

        download_link = file_meta["dlink"]
        custom_file_name = file_meta.get("filename", "terabox_download")

        logger.info(f"Successfully resolved link. Filename: {custom_file_name}, Link: {download_link}")

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
                await sent_message.edit("Download timed out.")
                return

        if os.path.exists(download_directory):
            start_time = time.time()
            thumb_image_path = None
            try:
                if (await db.get_upload_as_doc(update.from_user.id)) is False:
                    thumbnail = await Gthumb01(bot, update)
                    await bot.send_document(
                        chat_id=update.chat.id,
                        document=download_directory,
                        thumb=thumbnail,
                        caption=custom_file_name,
                        progress=progress_for_pyrogram,
                        progress_args=("Uploading...", sent_message, start_time)
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
                        progress_args=("Uploading...", sent_message, start_time)
                    )
            finally:
                try:
                    os.remove(download_directory)
                    if thumb_image_path and os.path.exists(thumb_image_path):
                        os.remove(thumb_image_path)
                except:
                    pass
            await sent_message.delete()
        else:
            await sent_message.edit("Download failed.")

    except Exception as e:
        logger.error(f"An error occurred in terabox_downloader: {e}", exc_info=True)
        await sent_message.edit("An unexpected error occurred. Please check the logs for details.")
