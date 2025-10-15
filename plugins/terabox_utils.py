import re, requests, logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

headers : dict[str, str] = {'user-agent':'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36'}

class TeraboxFolder():

    #--> Initialization (requests, headers, and result)
    def __init__(self) -> None:
        self.r : object = requests.Session()
        self.headers : dict[str,str] = headers
        self.result : dict[str,any] = {'status':'failed', 'js_token':'', 'browser_id':'', 'cookie':'', 'sign':'', 'timestamp':'', 'shareid':'', 'uk':'', 'list':[]}

    #--> Main control (get short_url, init authorization, and get root file)
    def search(self, url:str) -> None:
        logger.info(f"Starting search for URL: {url}")
        try:
            req : str = self.r.get(url, allow_redirects=True)
            self.short_url : str = re.search(r'surl=([^ &]+)',str(req.url)).group(1)
            logger.info(f"Extracted short_url: {self.short_url}")
            self.getAuthorization()
            self.getMainFile()
        except Exception as e:
            logger.error(f"Error during search: {e}", exc_info=True)
            self.result['status'] = 'failed'

    #--> Get 'jsToken' & 'browserid' for cookies
    def getAuthorization(self) -> None:
        try:
            url = f'https://www.terabox.app/wap/share/filelist?surl={self.short_url}'
            logger.info(f"Getting authorization from: {url}")
            req : str = self.r.get(url, headers=self.headers, allow_redirects=True)
            js_token = re.search(r'%28%22(.*?)%22%29',str(req.text.replace('\\',''))).group(1)
            browser_id = req.cookies.get_dict().get('browserid')
            cookie = 'lang=id;' + ';'.join(['{}={}'.format(a,b) for a,b in self.r.cookies.get_dict().items()])

            self.result['js_token'] = js_token
            self.result['browser_id'] = browser_id
            self.result['cookie'] = cookie
            logger.info(f"Successfully got authorization. JS Token: {js_token}")
        except Exception as e:
            logger.error(f"Error getting authorization: {e}", exc_info=True)
            self.result['status'] = 'failed'


    #--> Get payload (root / top layer / overall data) and init packing file information
    def getMainFile(self) -> None:
        try:
            url: str = f'https://www.terabox.com/api/shorturlinfo?app_id=250528&shorturl=1{self.short_url}&root=1'
            logger.info(f"Getting main file list from: {url}")
            req : object = self.r.get(url, headers=self.headers, cookies={'cookie':''}).json()
            logger.info(f"Main file list response: {req}")

            all_file = self.packData(req, self.short_url)
            if len(all_file):
                self.result['sign']      = req['sign']
                self.result['timestamp'] = req['timestamp']
                self.result['shareid']   = req['shareid']
                self.result['uk']        = req['uk']
                self.result['list']      = all_file
                self.result['status']    = 'success'
                logger.info("Successfully processed main file list.")
        except Exception as e:
            logger.error(f"Error getting main file list: {e}", exc_info=True)
            self.result['status'] = 'failed'

    #--> Get child file data recursively (if any) and init packing file information
    def getChildFile(self, short_url, path:str='', root:str='0') -> list[dict[str, any]]:
        try:
            params = {'app_id':'250528', 'shorturl':short_url, 'root':root, 'dir':path}
            url = 'https://www.terabox.com/share/list?' + '&'.join([f'{a}={b}' for a,b in params.items()])
            logger.info(f"Getting child file list from: {url}")
            req : object = self.r.get(url, headers=self.headers, cookies={'cookie':''}).json()
            logger.info(f"Child file list response for path '{path}': {req}")
            return(self.packData(req, short_url))
        except Exception as e:
            logger.error(f"Error getting child file list for path '{path}': {e}", exc_info=True)
            return []

    #--> Pack each file information
    def packData(self, req:dict, short_url:str) -> list[dict[str, any]]:
        all_file = []
        try:
            for item in req.get('list', []):
                file_data = {
                    'is_dir' : item['isdir'],
                    'path'   : item['path'],
                    'fs_id'  : item['fs_id'],
                    'name'   : item['server_filename'],
                    'size'   : item.get('size') if not bool(int(item.get('isdir'))) else '',
                    'list'   : [],
                }
                if item.get('isdir'):
                    file_data['list'] = self.getChildFile(short_url, item['path'], '0')
                all_file.append(file_data)
        except Exception as e:
            logger.error(f"Error packing data: {e}", exc_info=True)
        return(all_file)

    def flatten_files(self) -> list[dict[str, any]]:
        """Flatten the nested list of files."""
        if self.result['status'] == 'failed':
            return []

        files_to_process = self.result['list'].copy()
        flattened_list = []

        while files_to_process:
            file_info = files_to_process.pop(0)
            if not file_info.get('is_dir'):
                flattened_list.append(file_info)

            if 'list' in file_info and file_info['list']:
                files_to_process.extend(file_info['list'])

        return flattened_list

class TeraboxLink():

    #--> Initialization (requests, headers, payload, and result)
    def __init__(self, fs_id:str, uk:str, shareid:str, timestamp:str, sign:str, js_token:str, cookie:str) -> None:

        self.r : object = requests.Session()
        self.headers : dict[str,str] = headers
        self.result : dict[str,dict] = {'status':'failed', 'download_link':{}}
        self.cookie : str = cookie

        #-> Dynamic params (change every requests)
        self.dynamic_params: dict[str,str] = {
            'uk'        : str(uk),
            'sign'      : str(sign),
            'shareid'   : str(shareid),
            'primaryid' : str(shareid),
            'timestamp' : str(timestamp),
            'jsToken'   : str(js_token),
            'fid_list'  : str(f'[{fs_id}]')}

        #--> Static params (doesn't change every request)
        self.static_param : dict[str,str] = {
            'app_id'     : '250528',
            'channel'    : 'dubox',
            'product'    : 'share',
            'clienttype' : '0',
            'dp-logid'   : '',
            'nozip'      : '0',
            'web'        : '1'}

    #--> Generate main download link
    def generate(self) -> None:
        try:
            params : str = {**self.dynamic_params, **self.static_param}
            url : str = 'https://www.terabox.com/share/download?' + '&'.join([f'{a}={b}' for a,b in params.items()])
            logger.info(f"Generating download link from: {url}")
            logger.info(f"Using cookie for link generation: {self.cookie}")

            req : object = self.r.get(url, cookies={'cookie':self.cookie}).json()
            logger.info(f"Generate link response: {req}")

            if not req['errno']:
                self.result['download_link'] = req['dlink']
                self.result['status'] = 'success'
                logger.info(f"Successfully generated download link: {req['dlink']}")
            else:
                logger.error(f"Error in generate link response: {req}")
                self.result['status'] = 'failed'
        except Exception as e:
            logger.error(f"Error generating download link: {e}", exc_info=True)
            self.result['status'] = 'failed'
        finally:
            self.r.close()
