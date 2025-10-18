from pyrogram import Client, filters
from pyrogram.types import Message
from plugins.config import Config
from plugins.database.database import db
import aiohttp
import asyncio
import time
import os
import re
import logging
from plugins.functions.display_progress import humanbytes, progress_for_pyrogram
from plugins.thumbnail import Gthumb01, Mdata01, Gthumb02
from urllib.parse import unquote

# Set up logging
logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

class TeraboxDownloader:
    def __init__(self, cookie=None):
        self.cookie = cookie
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.terabox.com/',
            'Origin': 'https://www.terabox.com'
        }
        if self.cookie:
            self.headers['Cookie'] = f'ndus={self.cookie}'

    async def extract_surl(self, url):
        """Extract surl from various Terabox URL formats"""
        patterns = [
            r'surl=([a-zA-Z0-9_-]+)',
            r'/s/([a-zA-Z0-9_-]+)',
            r'1([a-zA-Z0-9_-]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        # Try to fetch and extract from redirect
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, allow_redirects=True, timeout=10) as response:
                    final_url = str(response.url)
                    for pattern in patterns:
                        match = re.search(pattern, final_url)
                        if match:
                            return match.group(1)
        except:
            pass

        return None

    async def get_file_info(self, surl):
        """Get file information from Terabox"""
        # Try different API endpoints
        apis = [
            f'https://www.terabox.com/share/list?app_id=250528&web=1&channel=dubox&clienttype=0&jsToken=&dp-logid=&page=1&num=20&by=name&order=asc&site_referer=&shorturl={surl}&root=1',
            f'https://www.terabox.com/api/shorturlinfo?shorturl={surl}&root=1',
        ]

        async with aiohttp.ClientSession() as session:
            for api in apis:
                try:
                    async with session.get(api, headers=self.headers, timeout=15, ssl=False) as response:
                        if response.status == 200:
                            data = await response.json()
                            logger.info(f"API Response: {data}")

                            # Check different response formats
                            if data.get('errno') == 0:
                                # Format 1: list in response
                                if 'list' in data and data['list']:
                                    file_info = data['list'][0]
                                    return {
                                        'filename': file_info.get('server_filename', 'terabox_file'),
                                        'size': file_info.get('size', 0),
                                        'fs_id': file_info.get('fs_id'),
                                        'uk': data.get('uk'),
                                        'shareid': data.get('shareid'),
                                        'timestamp': data.get('timestamp')
                                    }
                except Exception as e:
                    logger.error(f"API {api} failed: {e}")
                    continue

        return None

    async def get_download_link(self, file_info, surl):
        """Get direct download link"""
        try:
            # Method 1: Direct download API
            download_api = f'https://www.terabox.com/share/download?surl={surl}&fid={file_info["fs_id"]}'

            async with aiohttp.ClientSession() as session:
                async with session.get(download_api, headers=self.headers, timeout=15, ssl=False) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('errno') == 0 and data.get('dlink'):
                            return data['dlink']

                # Method 2: Try alternate API
                alt_api = f'https://www.terabox.com/api/download?shareid={file_info["shareid"]}&uk={file_info["uk"]}&fid={file_info["fs_id"]}&timestamp={file_info["timestamp"]}'

                async with session.get(alt_api, headers=self.headers, timeout=15, ssl=False) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('dlink'):
                            return data['dlink']
        except Exception as e:
            logger.error(f"Failed to get download link: {e}")

        return None

    async def resolve(self, url):
        """Main resolve method"""
        try:
            surl = await self.extract_surl(url)
            if not surl:
                return {'error': 'Could not extract surl from URL'}

            logger.info(f"Extracted surl: {surl}")

            file_info = await self.get_file_info(surl)
            if not file_info:
                return {'error': 'Could not fetch file information'}

            logger.info(f"File info: {file_info}")

            dlink = await self.get_download_link(file_info, surl)
            if not dlink:
                return {'error': 'Could not get download link'}

            return {
                'filename': file_info['filename'],
                'size': file_info['size'],
                'dlink': dlink
            }
        except Exception as e:
            logger.error(f"Resolution error: {e}", exc_info=True)
            return {'error': str(e)}


async def download_file(session, url, file_path, progress_callback, message):
    """Download file with progress tracking"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }

        async with session.get(url, headers=headers, timeout=None, ssl=False) as response:
            if response.status != 200:
                raise Exception(f"HTTP {response.status}")

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            start_time = time.time()

            with open(file_path, 'wb') as f:
                async for chunk in response.content.iter_chunked(1024 * 1024):  # 1MB chunks
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        # Update progress every 2 seconds
                        if time.time() - start_time > 2:
                            if progress_callback:
                                await progress_callback(downloaded, total_size, message)
                            start_time = time.time()

            return True
    except Exception as e:
        logger.error(f"Download error: {e}")
        return False


async def update_progress(current, total, message):
    """Update download progress"""
    try:
        percentage = (current * 100) / total if total > 0 else 0
        text = f"📥 Downloading from Terabox...\n\n"
        text += f"Progress: {percentage:.1f}%\n"
        text += f"Downloaded: {humanbytes(current)} / {humanbytes(total)}"
        await message.edit(text)
    except:
        pass


@Client.on_message(filters.private & filters.command("set_cookie"))
async def set_cookie_handler(bot, update):
    await update.reply_text(
        "Please reply to this message with your Terabox cookie (ndus value).\n\n"
        "📖 How to get your cookie:\n"
        "1. Login to Terabox in browser\n"
        "2. Open Developer Tools (F12)\n"
        "3. Go to Application/Storage > Cookies\n"
        "4. Find 'ndus' cookie and copy its value\n"
        "5. Reply to this message with that value"
    )


@Client.on_message(filters.private & filters.text & filters.reply)
async def handle_cookie_reply(bot, update):
    if update.reply_to_message and "reply to this message with your Terabox cookie" in update.reply_to_message.text:
        cookie = update.text.strip()
        await db.set_terabox_cookie(update.from_user.id, cookie)
        await update.reply_text("✅ Your Terabox cookie has been saved successfully!")


@Client.on_message(filters.private & filters.regex(r"https?://(?:www\.)?(?:terabox\.com|terabox\.app|teraboxlink\.com|1024tera\.com|4funbox\.com|mirrobox\.com|nephobox\.com|freeterabox\.com|teraboxapp\.com|gibibox\.com)\S+"))
async def terabox_downloader(bot, update):
    logger.info(f"Terabox link received from user {update.from_user.id}: {update.text}")

    sent_message = await update.reply_text("🔄 Processing Terabox link...")

    try:
        cookie = await db.get_terabox_cookie(update.from_user.id)
        downloader = TeraboxDownloader(cookie)

        await sent_message.edit("🔍 Resolving link...")

        file_meta = await downloader.resolve(update.text)

        if 'error' in file_meta:
            await sent_message.edit(f"❌ Error: {file_meta['error']}\n\nTry setting your cookie with /set_cookie")
            return

        filename = file_meta['filename']
        dlink = file_meta['dlink']

        logger.info(f"Resolved: {filename}")

        # Create download directory
        tmp_dir = os.path.join(Config.DOWNLOAD_LOCATION, str(update.from_user.id))
        os.makedirs(tmp_dir, exist_ok=True)
        file_path = os.path.join(tmp_dir, filename)

        await sent_message.edit("📥 Downloading...")

        # Download file
        async with aiohttp.ClientSession() as session:
            success = await download_file(session, dlink, file_path, update_progress, sent_message)

        if not success or not os.path.exists(file_path):
            await sent_message.edit("❌ Download failed!")
            return

        # Upload to Telegram
        await sent_message.edit("📤 Uploading to Telegram...")
        start_time = time.time()

        upload_as_doc = await db.get_upload_as_doc(update.from_user.id)

        try:
            if not upload_as_doc:
                thumbnail = await Gthumb01(bot, update)
                await bot.send_document(
                    chat_id=update.chat.id,
                    document=file_path,
                    thumb=thumbnail,
                    caption=filename,
                    progress=progress_for_pyrogram,
                    progress_args=("Uploading...", sent_message, start_time)
                )
            else:
                width, height, duration = await Mdata01(file_path)
                thumb = await Gthumb02(bot, update, duration, file_path)
                await bot.send_video(
                    chat_id=update.chat.id,
                    video=file_path,
                    caption=filename,
                    duration=duration,
                    width=width,
                    height=height,
                    supports_streaming=True,
                    thumb=thumb,
                    progress=progress_for_pyrogram,
                    progress_args=("Uploading...", sent_message, start_time)
                )

            await sent_message.delete()

        finally:
            # Cleanup
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except:
                pass

    except Exception as e:
        logger.error(f"Terabox error: {e}", exc_info=True)
        await sent_message.edit(f"❌ Error: {str(e)}")