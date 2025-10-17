# This file will contain a more faithful Python implementation of the TeraFetch logic.
import requests
import re
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class TeraFetchV2:
    def __init__(self, cookie: Optional[str] = None):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        })
        self.cookie = cookie
        if self.cookie:
            self.session.headers['Cookie'] = self.cookie

    def _get_shorturl(self, url: str) -> Optional[str]:
        """Extracts the short URL identifier from a Terabox link."""
        try:
            res = self.session.get(url, allow_redirects=True, timeout=10)
            match = re.search(r'surl=([^&]+)', res.url)
            if match:
                return match.group(1)
        except requests.RequestException as e:
            logger.error(f"Failed to get shorturl from {url}: {e}")
        return None

    def resolve(self, url: str) -> Dict[str, Any]:
        """
        Resolves a Terabox URL to get file metadata.
        Orchestrates the different resolution methods, similar to TeraFetch.
        """
        shorturl = self._get_shorturl(url)
        if not shorturl:
            return {"error": "Could not extract a valid Terabox shorturl."}

        if self.cookie:
            logger.info("Attempting to resolve with private link method.")
            result = self._resolve_private_link(shorturl)
            if result:
                return result

        logger.info("Falling back to public link method.")
        result = self._resolve_public_link(shorturl)
        if result:
            return result

        logger.warning("Public method failed. Attempting bypass.")
        result = self._resolve_with_bypass(shorturl)
        if result:
            return result

        return {"error": "All resolution methods failed."}

    def _resolve_private_link(self, shorturl: str) -> Optional[Dict[str, Any]]:
        """
        Resolves a private link using filemetas and download APIs.
        This is for authenticated users.
        """
        try:
            # Step 1: Call filemetas to get file list and info
            filemetas_url = f"https://www.terabox.com/api/filemetas?surl={shorturl}&dir=1"
            res = self.session.get(filemetas_url)
            res.raise_for_status()
            data = res.json()

            if data.get("errno") != 0 or not data.get("list"):
                logger.warning(f"Private resolve (filemetas) failed: {data.get('errmsg', 'No list')}")
                return None

            # Find the first file in the list (simplification)
            first_file = next((f for f in data["list"] if f.get("isdir") == 0), None)
            if not first_file:
                logger.warning("No files found in private link response.")
                return None

            # Step 2: Call download API to get the dlink
            download_api_url = f"https://www.terabox.com/api/download?fidlist=[{first_file['fs_id']}]"
            res = self.session.get(download_api_url)
            res.raise_for_status()
            dlink_data = res.json()

            if dlink_data.get("errno") == 0 and dlink_data.get("dlink"):
                return {
                    "filename": first_file.get("server_filename"),
                    "size": first_file.get("size"),
                    "dlink": dlink_data["dlink"],
                }
            else:
                logger.warning(f"Private resolve (download) failed: {dlink_data.get('errmsg', 'No dlink')}")
                return None

        except (requests.RequestException, json.JSONDecodeError) as e:
            logger.error(f"Private link resolution failed with exception: {e}", exc_info=True)
            return None

    def _resolve_public_link(self, shorturl: str) -> Optional[Dict[str, Any]]:
        """
        Resolves a public link using the sharedownload API.
        """
        try:
            api_url = f"https://www.terabox.com/api/sharedownload?surl={shorturl}"
            headers = {"Referer": f"https://www.terabox.com/s/{shorturl}"}
            res = self.session.get(api_url, headers=headers)
            res.raise_for_status()
            data = res.json()

            if data.get("errno") == 0 and data.get("dlink"):
                # The filename is often in a nested list in this response
                filename = data.get("filename")
                if not filename and data.get("list"):
                    filename = data["list"][0].get("server_filename")

                return {
                    "filename": filename,
                    "size": data.get("size"),
                    "dlink": data["dlink"],
                }
            else:
                logger.warning(f"Public resolve failed: {data.get('errmsg', 'No dlink')}")
                return None

        except (requests.RequestException, json.JSONDecodeError) as e:
            logger.error(f"Public link resolution failed with exception: {e}", exc_info=True)
            return None

    def _resolve_with_bypass(self, shorturl: str) -> Optional[Dict[str, Any]]:
        """
        Attempts to resolve the link using the bypass method from TeraFetch.
        """
        try:
            # This mimics the `tryDirectShareAPI` function from the Go code.
            params = {
                "surl": shorturl,
                "channel": "chunlei",
                "web": "1",
                "app_id": "250528",
                "clienttype": "0",
            }
            api_url = "https://www.terabox.com/api/sharedownload"
            headers = {
                "Referer": "https://www.terabox.com/",
                "Origin": "https://www.terabox.com",
            }
            res = self.session.get(api_url, params=params, headers=headers)
            res.raise_for_status()
            data = res.json()

            if data.get("errno") == 0 and data.get("dlink"):
                filename = ""
                size = 0
                if data.get("list"):
                    filename = data["list"][0].get("server_filename")
                    size = data["list"][0].get("size")

                return {
                    "filename": filename,
                    "size": size,
                    "dlink": data["dlink"],
                }
            else:
                logger.warning(f"Bypass resolve failed: {data.get('errmsg', 'No dlink')}")
                return None

        except (requests.RequestException, json.JSONDecodeError) as e:
            logger.error(f"Bypass resolution failed with exception: {e}", exc_info=True)
            return None
