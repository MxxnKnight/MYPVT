from pyrogram import Client, filters
from pyrogram.types import Message
from plugins.config import Config
from plugins.database.database import db
from plugins.terafetch_v2_utils import TeraFetchV2
import aiohttp
import asyncio
import time
import os
import logging
from plugins.functions.display_progress import humanbytes, progress_for_pyrogram
from plugins.thumbnail import Gthumb01, Mdata01, Gthumb02
from plugins.dl_button import download_coroutine

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
        cookie = update.text.strip()
        await db.set_terabox_cookie(update.from_user.id, cookie)
        await update.reply_text("✅ Your Terabox cookie has been saved successfully!")

@Client.on_message(filters.private & filters.regex(r"https?://(?:www\.)?(?:terabox\.com|terabox\.app|teraboxlink\.com)\S+"))
async def terabox_downloader(bot, update):
    logger.info(f"Received terabox link from user {update.from_user.id}: {update.text}")

    try:
        cookie = await db.get_terabox_cookie(update.from_user.id)

        sent_message = await update.reply_text("🔄 Resolving Terabox link, please wait...")

        loop = asyncio.get_running_loop()

        try:
            terafetch = TeraFetchV2(cookie)
            file_meta = await loop.run_in_executor(None, terafetch.resolve, update.text)

            if "error" in file_meta or not file_meta.get("dlink"):
                error_message = file_meta.get("error", "Could not resolve download link.")
                logger.error(f"Terabox resolution error: {error_message}")
                await sent_message.edit(f"❌ Error: {error_message}")
                return

            download_link = file_meta["dlink"]
            custom_file_name = file_meta.get("filename", "terabox_download")

            logger.info(f"Successfully resolved link. Filename: {custom_file_name}")

            # Create user-specific download directory
            tmp_directory_for_each_user = os.path.join(Config.DOWNLOAD_LOCATION, str(update.from_user.id))
            os.makedirs(tmp_directory_for_each_user, exist_ok=True)
            download_directory = os.path.join(tmp_directory_for_each_user, custom_file_name)

            await sent_message.edit("📥 Downloading from Terabox...")

            # Download the file
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
                    logger.error("Download timed out")
                    await sent_message.edit("⏱️ Download timed out. Please try again.")
                    return

            # Check if file was downloaded
            if not os.path.exists(download_directory):
                logger.error(f"File not found after download: {download_directory}")
                await sent_message.edit("❌ Download failed. File not found.")
                return

            logger.info(f"File downloaded successfully: {download_directory}")

            # Upload the file
            await sent_message.edit("📤 Uploading to Telegram...")
            start_time = time.time()
            thumb_image_path = None

            try:
                # Check user's upload preference
                upload_as_doc = await db.get_upload_as_doc(update.from_user.id)

                if not upload_as_doc:
                    # Upload as document
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
                    # Upload as video
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

                logger.info("Upload completed successfully")
                await sent_message.edit("✅ Upload completed successfully!")

            finally:
                # Clean up downloaded files
                try:
                    if os.path.exists(download_directory):
                        os.remove(download_directory)
                        logger.info(f"Cleaned up: {download_directory}")
                    if thumb_image_path and os.path.exists(thumb_image_path):
                        os.remove(thumb_image_path)
                        logger.info(f"Cleaned up thumbnail: {thumb_image_path}")
                except Exception as cleanup_error:
                    logger.error(f"Cleanup error: {cleanup_error}")

        except Exception as resolve_error:
            logger.error(f"Resolution error: {resolve_error}", exc_info=True)
            await sent_message.edit(f"❌ Error resolving link: {str(resolve_error)}")

    except Exception as e:
        logger.error(f"Unexpected error in terabox_downloader: {e}", exc_info=True)
        try:
            await update.reply_text(f"❌ An unexpected error occurred: {str(e)}")
        except:
            pass