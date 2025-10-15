# This file will contain the Python implementation of the TeraFetch logic.
import requests
import re
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class TeraFetch:
    def __init__(self, cookie: Optional[str] = None):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        })
        self.cookie = cookie
        if self.cookie:
            self.session.headers['Cookie'] = self.cookie

    def _get_shorturl(self, url: str) -> str:
        """Extracts the short URL identifier from a Terabox link."""
        res = self.session.get(url, allow_redirects=True)
        return re.search(r'surl=([^&]+)', res.url).group(1)

    def resolve(self, url: str) -> Dict[str, Any]:
        """
        Resolves a Terabox URL to get file metadata.
        Orchestrates the different resolution methods.
        """
        shorturl = self._get_shorturl(url)

        if self.cookie:
            logger.info("Attempting to resolve with private link method.")
            result = self._resolve_private_link(shorturl)
            if result:
                return result

        logger.info("Attempting to resolve with public link method.")
        result = self._resolve_public_link(shorturl)
        if result:
            return result

        logger.warning("Standard methods failed. Attempting bypass.")
        result = self._resolve_with_bypass(shorturl)
        if result:
            return result

        return {"error": "All resolution methods failed."}

    def _resolve_private_link(self, shorturl: str) -> Optional[Dict[str, Any]]:
        """Resolves a private Terabox URL using authentication."""
        # This is a simplified translation of the Go code's filemetas and download API calls.
        # For now, it will just try a basic authenticated request.
        # A more complete implementation would be needed for full folder support.
        try:
            api_url = f"https://www.terabox.com/api/shorturlinfo?app_id=250528&shorturl={shorturl}&root=1"
            res = self.session.get(api_url)
            data = res.json()

            if data.get("errno") != 0:
                return None

            file_list = data.get("list", [])
            if not file_list:
                return None

            # For simplicity, we'll handle the first file.
            # A full implementation would handle the entire list for folder support.
            first_file = file_list[0]

            return {
                "filename": first_file.get("server_filename"),
                "size": first_file.get("size"),
                "fs_id": first_file.get("fs_id"),
                "shareid": data.get("shareid"),
                "uk": data.get("uk"),
                "sign": data.get("sign"),
                "timestamp": data.get("timestamp"),
            }
        except Exception as e:
            logger.error(f"Private link resolution failed: {e}", exc_info=True)
            return None

    def _resolve_public_link(self, shorturl: str) -> Optional[Dict[str, Any]]:
        """Resolves a public Terabox share URL."""
        # This is a translation of the callShareDownloadAPI function.
        try:
            api_url = f"https://www.terabox.com/api/sharedownload?app_id=250528&shorturl={shorturl}&root=1"
            res = self.session.get(api_url)
            data = res.json()

            if data.get("errno") == 0 and data.get("dlink"):
                return {
                    "filename": data.get("filename"),
                    "size": data.get("size"),
                    "dlink": data.get("dlink"),
                }
            return None
        except Exception as e:
            logger.error(f"Public link resolution failed: {e}", exc_info=True)
            return None

    def _resolve_with_bypass(self, shorturl: str) -> Optional[Dict[str, Any]]:
        """Attempts to resolve URLs using bypass techniques."""
        # This is a simplified translation of the bypass logic.
        # It will try the direct share API approach from the Go code.
        try:
            api_url = f"https://www.terabox.com/api/sharedownload?surl={shorturl}&channel=chunlei&web=1&app_id=250528&clienttype=0"
            headers = {
                "Referer": "https://www.terabox.com/",
                "Origin": "https://www.terabox.com",
            }
            res = self.session.get(api_url, headers=headers)
            data = res.json()
            if data.get("errno") == 0 and data.get("dlink"):
                return {
                    "filename": data.get("list", [{}])[0].get("server_filename"),
                    "size": data.get("list", [{}])[0].get("size"),
                    "dlink": data.get("dlink"),
                }
            return None
        except Exception as e:
            logger.error(f"Bypass resolution failed: {e}", exc_info=True)
            return None

    def get_download_link(self, file_meta: Dict[str, Any]) -> Optional[str]:
        """Gets the final direct download link, for private link results."""
        if file_meta.get("dlink"):
            return file_meta["dlink"]

        try:
            params = {
                'app_id': '250528',
                'channel': 'dubox',
                'clienttype': '0',
                'web': '1',
                'uk': file_meta.get('uk'),
                'shareid': file_meta.get('shareid'),
                'timestamp': file_meta.get('timestamp'),
                'sign': file_meta.get('sign'),
                'fidlist': f'[{file_meta.get("fs_id")}]'
            }
            api_url = 'https://www.terabox.com/api/download'
            res = self.session.get(api_url, params=params)
            data = res.json()

            if data.get("errno") == 0 and data.get("dlink"):
                return data["dlink"]
            return None
        except Exception as e:
            logger.error(f"Failed to get final download link: {e}", exc_info=True)
            return None
