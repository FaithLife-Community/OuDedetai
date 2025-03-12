import abc
from dataclasses import dataclass, field
import hashlib
import json
import logging
from math import ceil
import os
import time
from typing import Callable, Optional
import requests
import shutil
import sys
from base64 import b64encode
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import requests.structures

from ou_dedetai.app import App

from . import constants
from . import utils

class Props(abc.ABC):
    def __init__(self) -> None:
        self._md5: Optional[str] = None
        self._size: Optional[int] = None

    @property
    def size(self) -> Optional[int]:
        if self._size is None:
            self._size = self._get_size()
        return self._size

    @property
    def md5(self) -> Optional[str]:
        if self._md5 is None:
            self._md5 = self._get_md5()
        return self._md5

    @abc.abstractmethod
    def _get_size(self) -> Optional[int]:
        """Get the size"""
    
    @abc.abstractmethod
    def _get_md5(self) -> Optional[str]:
        """Calculate the md5 sum"""

class FileProps(Props):
    def __init__(self, path: str | Path | None):
        super(FileProps, self).__init__()
        self.path = None
        if path is not None:
            self.path = Path(path)

    def _get_size(self):
        if self.path is None:
            return
        if Path(self.path).is_file():
            return self.path.stat().st_size

    def _get_md5(self) -> Optional[str]:
        if self.path is None:
            return None
        md5 = hashlib.md5()
        with self.path.open('rb') as f:
            for chunk in iter(lambda: f.read(524288), b''):
                md5.update(chunk)
        return b64encode(md5.digest()).decode('utf-8')

@dataclass
class SoftwareReleaseInfo:
    version: str
    download_url: str


class UrlProps(Props):
    def __init__(self, url: str):
        super(UrlProps, self).__init__()
        self.path = url
        self._headers: Optional[requests.structures.CaseInsensitiveDict] = None

    @property
    def headers(self) -> requests.structures.CaseInsensitiveDict:
        if self._headers is None:
            self._headers = self._get_headers()
        return self._headers

    def _get_headers(self) -> requests.structures.CaseInsensitiveDict:
        logging.debug(f"Getting headers from {self.path}.")
        try:
            h = {'Accept-Encoding': 'identity'}  # force non-compressed txfr
            r = requests.head(self.path, allow_redirects=True, headers=h)
        except requests.exceptions.ConnectionError:
            logging.critical("Failed to connect to the server.")
            raise
        except Exception as e:
            logging.error(e)
            raise
        return r.headers

    def _get_size(self):
        content_length = self.headers.get('Content-Length')
        content_encoding = self.headers.get('Content-Encoding')
        if content_encoding is not None:
            logging.critical(f"The server requires receiving the file compressed as '{content_encoding}'.")
        logging.debug(f"{content_length=}")
        if content_length is not None:
            self._size = int(content_length)
        return self._size

    def _get_md5(self):
        if self.headers.get('server') == 'AmazonS3':
            content_md5 = self.headers.get('etag')
            if content_md5 is not None:
                # Convert from hex to base64
                content_md5_hex = content_md5.strip('"').strip("'")
                content_md5 = b64encode(bytes.fromhex(content_md5_hex)).decode()
        else:
            content_md5 = self.headers.get('Content-MD5')
        if content_md5 is not None:
            content_md5 = content_md5.strip('"').strip("'")
        logging.debug(f"{content_md5=}")
        if content_md5 is not None:
            self._md5 = content_md5
        return self._md5


@dataclass
class CachedRequests:
    """This struct all network requests and saves to a cache"""
    # Some of these values are cached to avoid github api rate-limits

    faithlife_product_releases: dict[str, dict[str, dict[str, list[str]]]] = field(default_factory=dict)
    """Cache of faithlife releases.
    
    Since this depends on the user's selection we need to scope the cache based on that
    The cache key is the product, version, and release channel
    """
    repository_latest_version: dict[str, str] = field(default_factory=dict)
    """Cache of the latest versions keyed by repository slug
    
    Keyed by repository slug Owner/Repo
    """
    repository_latest_url: dict[str, str] = field(default_factory=dict)
    """Cache of the latest download url keyed by repository slug
    
    Keyed by repository slug Owner/Repo
    """


    url_size_and_hash: dict[str, tuple[Optional[int], Optional[str]]] = field(default_factory=dict)

    last_updated: Optional[float] = None

    _update_hook: Optional[Callable[[], None]] = None


    @classmethod
    def load(cls) -> "CachedRequests":
        """Load the cache from file if exists"""
        path = Path(constants.NETWORK_CACHE_PATH)
        if path.exists():
            with open(path, "r") as f:
                try:
                    output: dict = json.load(f)
                    # Drop any unknown keys
                    known_keys = CachedRequests().__dict__.keys()
                    cache_keys = list(output.keys())
                    for k in cache_keys:
                        if k not in known_keys:
                            del output[k]
                    return CachedRequests(**output)
                except json.JSONDecodeError:
                    logging.warning("Failed to read cache JSON. Clearing…")
        return CachedRequests(
            last_updated=time.time()
        )
    
    def _as_dict(self) -> dict[str, str]:
        output = self.__dict__.copy()
        for output_key in self.__dict__.keys():
            if output_key.startswith("_"):
                del output[output_key]
        return output

    def _write(self) -> None:
        """Writes the cache to disk. Done internally when there are changes"""
        path = Path(constants.NETWORK_CACHE_PATH)
        path.parent.mkdir(exist_ok=True, parents=True)
        with open(path, "w") as f:
            json.dump(self._as_dict(), f, indent=4, sort_keys=True, default=vars)
            f.write("\n")
        if self._update_hook:
            self._update_hook()


    def _is_fresh(self) -> bool:
        """Returns whether or not this cache is valid"""
        if self.last_updated is None:
            return False
        valid_until = self.last_updated + constants.CACHE_LIFETIME_HOURS * 60 * 60
        if valid_until <= time.time():
            return False
        return True

    def clean_if_stale(self, force: bool = False):
        if force or not self._is_fresh():
            logging.debug("Cleaning out cache…")
            self = CachedRequests(last_updated=time.time())
            self._write()
        else:
            logging.debug("Cache is valid")


class NetworkRequests:
    """Uses the cache if found, otherwise retrieves the value from the network."""

    # This struct uses functions to call due to some of the values requiring parameters

    def __init__(
        self,
        force_clean: Optional[bool] = None,
        hook: Callable[[], None] | None = None
    ) -> None:
        self._cache = CachedRequests.load()
        self._cache._update_hook = hook
        self._cache.clean_if_stale(force=force_clean or False)

    def _faithlife_product_releases(
        self,
        product: Optional[str],
        version: Optional[str],
        channel: Optional[str]
    ) -> Optional[list[str]]:
        if product is None or version is None or channel is None:
            return None
        releases = self._cache.faithlife_product_releases
        if product not in releases:
            releases[product] = {}
        if version not in releases[product]:
            releases[product][version] = {}
        if (
            channel 
            not in releases[product][version]
        ):
            return None
        return releases[product][version][channel]

    def faithlife_product_releases(
        self,
        product: str,
        version: str,
        channel: str
    ) -> list[str]:
        output = self._faithlife_product_releases(product, version, channel)
        if output is not None and len(output) > 0:
            return output
        output = _get_faithlife_product_releases(
            faithlife_product=product,
            faithlife_product_version=version,
            faithlife_product_release_channel=channel
        )
        self._cache.faithlife_product_releases[product][version][channel] = output
        self._cache._write()
        return output
    
    def wine_appimage_recommended_url(self) -> str:
        repo = "FaithLife-Community/wine-appimages"
        return self._repo_latest_version(repo).download_url

    def _url_size_and_hash(self, url: str) -> tuple[Optional[int], Optional[str]]:
        """Attempts to get the size and hash from a URL.
        Uses cache if it exists
        
        Returns:
            bytes - from the Content-Length leader
            md5_hash - from the Content-MD5 header or S3's etag
        """
        if url not in self._cache.url_size_and_hash:
            props = UrlProps(url)
            self._cache.url_size_and_hash[url] = props.size, props.md5
            self._cache._write()
        return self._cache.url_size_and_hash[url]

    def url_size(self, url: str) -> Optional[int]:
        return self._url_size_and_hash(url)[0]
    
    def url_md5(self, url: str) -> Optional[str]:
        return self._url_size_and_hash(url)[1]

    def _repo_latest_version(self, repository: str) -> SoftwareReleaseInfo:
        if (
            repository not in self._cache.repository_latest_version
            or repository not in self._cache.repository_latest_url
        ):
            result = _get_latest_release_data(repository)
            self._cache.repository_latest_version[repository] = result.version
            self._cache.repository_latest_url[repository] = result.download_url
            self._cache._write()
        return SoftwareReleaseInfo(
            version=self._cache.repository_latest_version[repository],
            download_url=self._cache.repository_latest_url[repository]
        )

    def app_latest_version(self, channel: str) -> SoftwareReleaseInfo:
        if channel == "stable":
            repo = "FaithLife-Community/OuDedetai"
        else:
            repo = "FaithLife-Community/test-builds"
        return self._repo_latest_version(repo)
    
    def icu_latest_version(self) -> SoftwareReleaseInfo:
        return self._repo_latest_version("FaithLife-Community/icu")


def logos_reuse_download(
    sourceurl: str,
    file: str,
    targetdir: str,
    app: App,
    status_messages: bool = True
):
    dirs = [
        app.conf.user_download_dir,
        app.conf.download_dir,
    ]
    found = 1
    for i in dirs:
        if i is not None:
            logging.debug(f"Checking {i} for {file}.")
            file_path = Path(i) / file
            if os.path.isfile(file_path):
                logging.info(f"{file} exists in {i}. Verifying properties.")
                if _verify_downloaded_file(
                    sourceurl,
                    file_path,
                    app=app,
                    status_messages=status_messages
                ):
                    logging.info(f"{file} properties match. Using it…")
                    logging.debug(f"Copying {file} into {targetdir}")
                    try:
                        shutil.copy(os.path.join(i, file), targetdir)
                    except shutil.SameFileError:
                        pass
                    found = 0
                    break
                else:
                    logging.info(f"Incomplete file: {file_path}.")
    if found == 1:
        file_path = Path(os.path.join(app.conf.download_dir, file))
        # Start download.
        _net_get(
            sourceurl,
            target=file_path,
            app=app,
        )
        if _verify_downloaded_file(
            sourceurl,
            file_path,
            app=app,
            status_messages=status_messages
        ):
            logging.debug(f"Copying: {file} into: {targetdir}")
            try:
                shutil.copy(os.path.join(app.conf.download_dir, file), targetdir)
            except shutil.SameFileError:
                pass
        else:
            app.exit(f"Bad file size or checksum: {file_path}")


# FIXME: refactor to raise rather than return None
def _net_get(url: str, target: Optional[Path]=None, app: Optional[App] = None):
    # TODO:
    # - Check available disk space before starting download
    logging.debug(f"Download source: {url}")
    logging.debug(f"Download destination: {target}")
    target_props = FileProps(target)  # sets path and size attribs
    if app and target_props.path:
        app.status(f"Downloading {target_props.path.name}…", 0)
    parsed_url = urlparse(url)
    domain = parsed_url.netloc  # Gets the requested domain
    url_props = UrlProps(url)  # uses requests to set headers, size, md5 attribs

    # Initialize variables.
    local_size = 0
    total_size = url_props.size  # None or int
    logging.debug(f"File size on server: {total_size}")
    percent = None
    chunk_size = 100 * 1024  # 100 KB default
    if type(total_size) is int:
        # Use smaller of 2% of filesize or 2 MB for chunk_size.
        chunk_size = min([int(total_size / 50), 2 * 1024 * 1024])
    # Force non-compressed file transfer for accurate progress tracking.
    headers = {'Accept-Encoding': 'identity'}
    file_mode = 'wb'

    # If file exists and URL is resumable, set download Range.
    if target_props.size:
        logging.debug(f"File exists: {str(target_props.path)}")
        local_size = target_props.size
        logging.info(f"Current downloaded size in bytes: {local_size}")
        if url_props.headers.get('Accept-Ranges') == 'bytes':
            logging.debug("Server accepts byte range; attempting to resume download.")
            file_mode = 'ab'
            if type(url_props.size) is int:
                headers['Range'] = f'bytes={local_size}-{total_size}'
            else:
                headers['Range'] = f'bytes={local_size}-'

    logging.debug(f"{chunk_size=}; {file_mode=}; {headers=}")

    # Log download type.
    if 'Range' in headers.keys():
        message = f"Continuing download for {url_props.path}."
    else:
        message = f"Starting new download for {url_props.path}."
    logging.info(message)

    # Initiate download request.
    try:
        # FIXME: consider splitting this into two functions with a common base.
        # One that writes into a file, and one that returns a str, 
        # that share most of the internal logic
        if target_props.path is None:  # return url content as text
            with requests.get(url_props.path, headers=headers) as r:
                if callable(r):
                    logging.error("Failed to retrieve data from the URL.")
                    return None

                try:
                    r.raise_for_status()
                except requests.exceptions.HTTPError as e:
                    if domain in ["github.com", "api.github.com"]:
                        if (
                            e.response.status_code == 403
                            or e.response.status_code == 429
                        ):
                            message = "GitHub API rate limit exceeded. Please wait "
                            if "x-ratelimit-reset" in r.headers:
                                epoch_to_reset: str = r.headers["x-ratelimit-reset"]
                                seconds_until_reset = ceil(int(epoch_to_reset) - time.time()) 
                                if seconds_until_reset < 120:
                                    message += f"{seconds_until_reset} seconds "
                                else:
                                    # More human readable to display in minutes
                                    message += f"{ceil(seconds_until_reset / 60)} minutes " 
                            message += "before trying again."
                            logging.error(message)
                    else:
                        logging.error(f"HTTP error occurred: {e.response.status_code}")
                    return None

                return r._content  # raw bytes
        else:  # download url to target.path
            with requests.get(url_props.path, stream=True, headers=headers) as r:
                with target_props.path.open(mode=file_mode) as f:
                    if file_mode == 'wb':
                        mode_text = 'Writing'
                    else:
                        mode_text = 'Appending'
                    logging.debug(f"{mode_text} data to file {target_props.path}.")
                    for chunk in r.iter_content(chunk_size=chunk_size):
                        f.write(chunk)
                        local_size = os.fstat(f.fileno()).st_size
                        if type(total_size) is int:
                            percent = local_size / total_size
                            # if None not in [app, evt]:
                            if app:
                                # This assumes that there is a 1:1 relationship between
                                # steps and download jobs, which is presently true
                                # If at some point in the future it is no longer true
                                # the worst that'll happen is the progress bar will
                                # appear to go backwards.
                                app.status(
                                    f"Downloading {target_props.path.name}…",
                                    percent
                                )
    except requests.exceptions.RequestException as e:
        logging.error(f"Error occurred during HTTP request: {e}")
        return None  # Return None values to indicate an error condition


def _verify_downloaded_file(url: str, file_path: Path | str, app: App, status_messages: bool = True): 
    if status_messages:
        app.status(f"Verifying {file_path}…", 0)
    file_props = FileProps(file_path)
    url_size = app.conf._network.url_size(url)
    if url_size is not None and file_props.size != url_size:
        logging.warning(f"{file_path} is the wrong size.")
        return False
    url_md5 = app.conf._network.url_md5(url)
    if url_md5 is not None and file_props.md5 != url_md5:
        logging.warning(f"{file_path} has the wrong MD5 sum.")
        return False
    logging.debug(f"{file_path} is verified.")
    return True


def _get_first_asset_url(json_data: dict) -> str:
    """Parses the github api response to find the first asset's download url
    """
    assets = json_data.get('assets') or []
    if len(assets) == 0:
        raise Exception("Failed to find the first asset in the repository data: "
                        f"{json_data}")
    first_asset = assets[0]
    download_url: Optional[str] = first_asset.get('browser_download_url')
    if download_url is None:
        raise Exception("Failed to find the download URL in the repository data: "
                        f"{json_data}")
    return download_url


def _get_version_name(json_data: dict) -> str:
    """Gets tag name from json data, strips leading v if exists"""
    tag_name: Optional[str] = json_data.get('tag_name')
    if tag_name is None:
        raise Exception("Failed to find the tag_name in the repository data: "
                        f"{json_data}")
    # Trim a leading v to normalize the version
    tag_name = tag_name.lstrip("v")
    return tag_name


def _get_latest_release_data(repository) -> SoftwareReleaseInfo:
    """Gets latest release information
    
    Raises:
        Exception - on failure to make network operation or parse github API
        
    Returns:
        SoftwareReleaseInfo
    """
    release_url = f"https://api.github.com/repos/{repository}/releases/latest"
    data = _net_get(release_url)
    if data is None:
        raise Exception("Could not get latest release URL.")
    try:
        json_data: dict = json.loads(data.decode())
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding Github's JSON response: {e}")
        raise

    download_url = _get_first_asset_url(json_data)
    version = _get_version_name(json_data)
    return SoftwareReleaseInfo(
        version=version,
        download_url=download_url
    )

def download_recommended_appimage(app: App):
    wine64_appimage_full_filename = Path(app.conf.wine_appimage_recommended_file_name)
    dest_path = Path(app.conf.installer_binary_dir) / wine64_appimage_full_filename
    if dest_path.is_file():
        return
    else:
        logos_reuse_download(
            app.conf.wine_appimage_recommended_url,
            app.conf.wine_appimage_recommended_file_name,
            app.conf.installer_binary_dir,
            app=app
        )

def _get_faithlife_product_releases(
    faithlife_product: str,
    faithlife_product_version: str,
    faithlife_product_release_channel: str
) -> list[str]:
    logging.debug(f"Downloading release list for {faithlife_product} {faithlife_product_version}…")
    # NOTE: This assumes that Verbum release numbers continue to mirror Logos.
    if faithlife_product_release_channel == "beta":
        url = "https://clientservices.logos.com/update/v1/feed/logos10/beta.xml"
    else:
        url = f"https://clientservices.logos.com/update/v1/feed/logos{faithlife_product_version}/stable.xml"
    
    response_xml_bytes = _net_get(url)
    if response_xml_bytes is None:
        raise Exception("Failed to get logos releases")

    # Parse XML
    root = ET.fromstring(response_xml_bytes.decode('utf-8-sig'))

    # Define namespaces
    namespaces = {
        'ns0': 'http://www.w3.org/2005/Atom',
        'ns1': 'http://services.logos.com/update/v1/'
    }

    # Extract versions
    releases = []
    # Obtain all listed releases.
    for entry in root.findall('.//ns1:version', namespaces):
        if entry.text:
            releases.append(entry.text)
        # if len(releases) == 5:
        #    break

    #Filtering not needed at the moment but left here in case we want it later.
    #Double check this works before releasing.
    #from packaging.versions import Version
    #filtered_releases = [version for version in releases if Version("40.0.0.0") > Version(version)]
    #logging.debug(f"Available releases: {', '.join(releases)}")
    #logging.debug(f"Filtered releases: {', '.join(filtered_releases)}")

    return releases


def update_lli_binary(app: App):
    lli_file_path = os.path.realpath(sys.argv[0])
    lli_download_path = Path(app.conf.download_dir) / constants.BINARY_NAME
    temp_path = Path(app.conf.download_dir) / f"{constants.BINARY_NAME}.tmp"
    logging.debug(
        f"Updating {constants.APP_NAME} to latest version by overwriting: {lli_file_path}")

    # Remove existing downloaded file if different version.
    if lli_download_path.is_file():
        logging.info("Checking if existing LLI binary is latest version.")
        lli_download_ver = utils.get_lli_release_version(lli_download_path)
        if not lli_download_ver or lli_download_ver != app.conf.app_latest_version:
            logging.info(f"Removing \"{lli_download_path}\", version: {lli_download_ver}")
            # Remove incompatible file.
            lli_download_path.unlink()

    logos_reuse_download(
        app.conf.app_latest_version_url,
        constants.BINARY_NAME,
        app.conf.download_dir,
        app=app,
    )
    shutil.copy(lli_download_path, temp_path)
    try:
        shutil.move(temp_path, lli_file_path)
    except Exception as e:
        logging.error(f"Failed to replace the binary: {e}")
        return

    os.chmod(sys.argv[0], os.stat(sys.argv[0]).st_mode | 0o111)
    logging.debug(f"Successfully updated {constants.APP_NAME}.")
    utils.restart_lli()
