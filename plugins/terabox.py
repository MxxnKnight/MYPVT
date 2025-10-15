import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from plugins.config import Config
from plugins.database.database import db
from plugins.terabox_utils import TeraboxFolder, TeraboxLink
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

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@Client.on_message(filters.private & filters.command("set_cookie"))
async def set_cookie_handler(bot, update):
    logger.info(f"User {update.from_user.id} initiated /set_cookie command.")
    await update.reply_text(
        "Please send me your Terabox cookie. For instructions on how to get it, please see the documentation for the `terabox-downloader` library."
    )

@Client.on_message(filters.private & filters.text & filters.reply)
async def handle_cookie_reply(bot, update):
    if update.reply_to_message.text.startswith("Please send me your Terabox cookie"):
        cookie = update.text
        logger.info(f"Received cookie from user {update.from_user.id}.")
        await db.set_terabox_cookie(update.from_user.id, cookie)
        logger.info(f"Successfully saved cookie for user {update.from_user.id}.")
        await update.reply_text("Your Terabox cookie has been saved.")

@Client.on_message(filters.private & filters.regex(r"https?://(?:www\.)?(?:terabox\.com|terabox\.app)\S+"))
async def terabox_downloader(bot, update):
    logger.info(f"Received terabox link from user {update.from_user.id}: {update.text}")
    cookie = await db.get_terabox_cookie(update.from_user.id)
    if not cookie:
        logger.warning(f"User {update.from_user.id} has not set their Terabox cookie.")
        await update.reply_text("You have not set your Terabox cookie yet. Please use the /set_cookie command to set it.")
        return

    sent_message = await update.reply_text("Processing link, please wait...")

    loop = asyncio.get_running_loop()
    try:
        folder = TeraboxFolder()
        await loop.run_in_executor(None, folder.search, update.text)

        # Inject the user's cookie
        folder.result['cookie'] = cookie

        if folder.result['status'] == 'failed':
            await sent_message.edit("Failed to retrieve file information. The link might be invalid or expired.")
            return

        all_files = folder.flatten_files()
        logger.info(f"Found a total of {len(all_files)} files to download.")

        if not all_files:
            await sent_message.edit("No files found in the provided link.")
            return

        await sent_message.edit(f"Found {len(all_files)} file(s). Starting download...")

        for i, file_info in enumerate(all_files):
            file_number = i + 1
            custom_file_name = file_info["name"]
            logger.info(f"Processing file {file_number}/{len(all_files)}: {custom_file_name}")

            try:
                await sent_message.edit(f"Downloading file {file_number} of {len(all_files)}: `{custom_file_name}`")

                link_generator = TeraboxLink(
                    fs_id=str(file_info['fs_id']),
                    uk=str(folder.result['uk']),
                    shareid=str(folder.result['shareid']),
                    timestamp=str(folder.result['timestamp']),
                    sign=str(folder.result['sign']),
                    js_token=str(folder.result['js_token']),
                    cookie=str(folder.result['cookie'])
                )
                await loop.run_in_executor(None, link_generator.generate)

                if link_generator.result['status'] == 'failed':
                    logger.error(f"Failed to get download link for {file_info['name']}")
                    await bot.send_message(update.chat.id, f"Could not get download link for `{file_info['name']}`. Skipping.")
                    continue

                download_link = link_generator.result['download_link']
                custom_file_name = file_info["name"]

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
                        await sent_message.edit(f"Download timed out for `{custom_file_name}`.")
                        continue

                if os.path.exists(download_directory):
                    start_time = time.time()
                    thumb_image_path = None
                    try:
                        await sent_message.edit(f"Uploading file {file_number} of {len(all_files)}: `{custom_file_name}`")
                        if (await db.get_upload_as_doc(update.from_user.id)) is False:
                            thumbnail = await Gthumb01(bot, update)
                            await bot.send_document(
                                chat_id=update.chat.id,
                                document=download_directory,
                                thumb=thumbnail,
                                caption=custom_file_name,
                                progress=progress_for_pyrogram,
                                progress_args=(
                                    f"Uploading: {custom_file_name}",
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
                                    f"Uploading: {custom_file_name}",
                                    sent_message,
                                    start_time
                                )
                            )
                        logger.info(f"Successfully uploaded {custom_file_name} for user {update.from_user.id}.")
                    except Exception as e:
                        logger.error(f"Error uploading {custom_file_name} for user {update.from_user.id}: {e}", exc_info=True)
                        await bot.send_message(update.chat.id, f"An error occurred during file upload for `{custom_file_name}`.")
                    finally:
                        try:
                            os.remove(download_directory)
                            if thumb_image_path and os.path.exists(thumb_image_path):
                                os.remove(thumb_image_path)
                        except:
                            pass
                else:
                    await sent_message.edit(f"Download failed for `{custom_file_name}`.")
            except Exception as e:
                logger.error(f"An error occurred while processing file {file_info['name']}: {e}", exc_info=True)
                await bot.send_message(update.chat.id, f"An unexpected error occurred for `{file_info['name']}`. Skipping.")
                continue

        await sent_message.edit(f"Finished processing all {len(all_files)} files.")
    except Exception as e:
        logger.error(f"A major error occurred in terabox_downloader for user {update.from_user.id}: {e}", exc_info=True)
        await sent_message.edit("A critical error occurred. Please check the logs for details.")
