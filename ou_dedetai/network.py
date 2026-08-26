import abc
from dataclasses import dataclass, field
import hashlib
import json
import logging
from math import ceil
import os
import tempfile
import time
from typing import Callable, Optional
import requests
import shutil
import sys
from base64 import b64decode, b64encode
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET
from datetime import datetime

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


@dataclass
class GithubSoftwareReleasesInfo:
    latest: Optional[SoftwareReleaseInfo]
    pre_release: Optional[SoftwareReleaseInfo]


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
            return requests.structures.CaseInsensitiveDict()
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
    repository_latest_pre_release_version: dict[str, str] = field(default_factory=dict)
    """Cache of the latest version (that may be a pre release) keyed by repository slug
    
    Keyed by repository slug Owner/Repo
    """
    repository_latest_pre_release_url: dict[str, str] = field(default_factory=dict)
    """Cache of the latest download url (that may be a pre release) keyed by repository slug
    
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

    def ensure_fresh(self, force: bool = False) -> "CachedRequests":
        """Returns a CachedRequests that is fresh 
        
        - Either an empty new one
        - Or the existing one
        """
        if force or not self._is_fresh():
            logging.debug("Cleaning out cache…")
            self = CachedRequests(last_updated=time.time())
            self._write()
        else:
            logging.debug("Cache is valid")
        return self


class NetworkRequests:
    """Uses the cache if found, otherwise retrieves the value from the network."""

    # This struct uses functions to call due to some of the values requiring parameters

    def __init__(
        self,
        force_clean: Optional[bool] = None,
        hook: Callable[[], None] | None = None
    ) -> None:
        self._cache = CachedRequests.load().ensure_fresh(force=force_clean or False)
        self._cache._update_hook = hook

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
    
    def wine_appimage_versions(self) -> GithubSoftwareReleasesInfo:
        repo = "FaithLife-Community/wine-appimages"
        return self._repo_version(repo)

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

    def _repo_version(self, repository: str) -> GithubSoftwareReleasesInfo:
        output = GithubSoftwareReleasesInfo(latest=None, pre_release=None)
        if (
            repository in self._cache.repository_latest_version
            and repository  in self._cache.repository_latest_url
        ):
            output.latest = SoftwareReleaseInfo(
                version=self._cache.repository_latest_version[repository],
                download_url=self._cache.repository_latest_url[repository]
            )
        if (
            repository in self._cache.repository_latest_pre_release_version
            and repository  in self._cache.repository_latest_pre_release_url
        ):
            output.pre_release = SoftwareReleaseInfo(
                version=self._cache.repository_latest_pre_release_version[repository],
                download_url=self._cache.repository_latest_pre_release_url[repository]
            )
        if (
            output.pre_release is None and output.latest is None
        ):
            output = _get_release_data(repository)
            if output.latest:
                self._cache.repository_latest_version[repository] = output.latest.version
                self._cache.repository_latest_url[repository] = output.latest.download_url
            if output.pre_release:
                self._cache.repository_latest_pre_release_version[repository] = output.pre_release.version
                self._cache.repository_latest_pre_release_url[repository] = output.pre_release.download_url
            self._cache._write()
        return output
            

    def _repo_latest_version(self, repository: str) -> SoftwareReleaseInfo:
        if (
            repository not in self._cache.repository_latest_version
            or repository not in self._cache.repository_latest_url
        ):
            result = _get_release_data(repository)
            if result.latest:
                self._cache.repository_latest_version[repository] = result.latest.version
                self._cache.repository_latest_url[repository] = result.latest.download_url
            if result.pre_release:
                self._cache.repository_latest_pre_release_version[repository] = result.pre_release.version
                self._cache.repository_latest_pre_release_url[repository] = result.pre_release.download_url
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
    # These local helpers keep download hardening contained here so callers
    # retain their established paths and return-value contract.
    def _metadata_from_headers(headers) -> tuple[Optional[int], Optional[str]]:
        size = None
        content_length = headers.get('Content-Length')
        if content_length is not None:
            length_text = str(content_length).strip()
            if length_text.isascii() and length_text.isdigit():
                size = int(length_text)

        md5 = None
        content_md5 = headers.get('Content-MD5')
        if content_md5 is not None:
            digest_text = str(content_md5).strip().strip('"').strip("'")
            try:
                digest = b64decode(digest_text, validate=True)
            except (ValueError, TypeError):
                pass
            else:
                if len(digest) == 16:
                    md5 = b64encode(digest).decode('ascii')

        if md5 is None and str(headers.get('Server', '')).lower() == 'amazons3':
            etag = str(headers.get('ETag', '')).strip()
            if len(etag) >= 2 and etag[0] == etag[-1] and etag[0] in {'"', "'"}:
                etag = etag[1:-1]
            if len(etag) == 32 and all(character in '0123456789abcdefABCDEF' for character in etag):
                md5 = b64encode(bytes.fromhex(etag)).decode('ascii')
        return size, md5

    def _file_matches(path: Path, size: Optional[int], md5: Optional[str]) -> bool:
        if size is None and md5 is None:
            return False
        try:
            if not path.is_file():
                return False
            properties = FileProps(path)
            if size is not None and properties.size != size:
                return False
            if md5 is not None and properties.md5 != md5:
                return False
        except OSError:
            return False
        return True

    owned_paths: set[Path] = set()

    def _stage_copy(
        source: Path,
        destination: Path,
        size: Optional[int],
        md5: Optional[str],
        mode: int,
    ) -> Path:
        with tempfile.NamedTemporaryFile(
            mode='wb',
            prefix=f'.{destination.name}.',
            suffix='.part',
            dir=destination.parent,
            delete=False,
        ) as staged_file:
            staged_path = Path(staged_file.name)
            owned_paths.add(staged_path)
            with source.open('rb') as source_file:
                shutil.copyfileobj(source_file, staged_file)
            staged_file.flush()
            os.fsync(staged_file.fileno())
        os.chmod(staged_path, mode)
        if (size is not None or md5 is not None) and not _file_matches(staged_path, size, md5):
            raise ValueError(f"Staged copy of {file} failed validation")
        return staged_path

    timeout = (10, 30)
    request_headers = {'Accept-Encoding': 'identity'}
    download_path = Path(app.conf.download_dir) / file
    target_path = Path(targetdir) / file
    download_rollback: Optional[Path] = None
    download_published = False
    download_had_file = False

    try:
        remote_size = None
        remote_md5 = None
        try:
            with requests.head(
                sourceurl,
                allow_redirects=True,
                headers=request_headers,
                timeout=timeout,
            ) as response:
                if response.status_code == 200:
                    remote_size, remote_md5 = _metadata_from_headers(response.headers)
        except Exception as error:
            logging.debug("Could not obtain validation metadata for %s: %s", file, type(error).__name__)

        candidate_paths = []
        seen_candidates = set()
        candidate_directories: list[Optional[str]] = [
            app.conf.user_download_dir,
            app.conf.download_dir,
            targetdir,
        ]
        for directory in candidate_directories:
            if directory is None:
                continue
            candidate = Path(directory) / file
            candidate_key = os.path.abspath(candidate)
            if candidate_key not in seen_candidates:
                seen_candidates.add(candidate_key)
                candidate_paths.append(candidate)

        if remote_size is not None or remote_md5 is not None:
            for candidate in candidate_paths:
                logging.debug("Checking %s for %s.", candidate.parent, file)
                if status_messages and candidate.is_file():
                    app.status(f"Verifying {candidate}…", 0)
                if not _file_matches(candidate, remote_size, remote_md5):
                    continue
                logging.info("%s matches available download metadata. Using it…", file)
                if os.path.abspath(candidate) != os.path.abspath(target_path):
                    target_mode = (
                        target_path.stat().st_mode & 0o7777
                        if target_path.is_file()
                        else candidate.stat().st_mode & 0o7777
                    )
                    candidate_target_stage = _stage_copy(
                        candidate,
                        target_path,
                        remote_size,
                        remote_md5,
                        target_mode,
                    )
                    os.replace(candidate_target_stage, target_path)
                    owned_paths.discard(candidate_target_stage)
                return

        app.status(f"Downloading {file}…", 0)
        with requests.get(
            sourceurl,
            stream=True,
            allow_redirects=True,
            headers=request_headers,
            timeout=timeout,
        ) as response:
            if response.status_code != 200:
                raise RuntimeError(f"Unexpected HTTP status {response.status_code}")
            get_size, get_md5 = _metadata_from_headers(response.headers)
            with tempfile.NamedTemporaryFile(
                mode='wb',
                prefix=f'.{download_path.name}.',
                suffix='.part',
                dir=download_path.parent,
                delete=False,
            ) as staged_file:
                download_stage = Path(staged_file.name)
                owned_paths.add(download_stage)
                bytes_written = 0
                for chunk in response.iter_content(chunk_size=100 * 1024):
                    if not chunk:
                        continue
                    staged_file.write(chunk)
                    bytes_written += len(chunk)
                    if get_size:
                        app.status(f"Downloading {file}…", bytes_written / get_size)
                staged_file.flush()
                os.fsync(staged_file.fileno())

        if (get_size is not None or get_md5 is not None) and not _file_matches(download_stage, get_size, get_md5):
            raise ValueError(f"Downloaded {file} failed validation")

        if download_path.is_file():
            download_mode = download_path.stat().st_mode & 0o7777
        else:
            mode_handle, mode_name = tempfile.mkstemp(
                prefix=f'.{download_path.name}.',
                suffix='.mode',
                dir=download_path.parent,
            )
            mode_path = Path(mode_name)
            owned_paths.add(mode_path)
            os.close(mode_handle)
            mode_path.unlink()
            mode_handle = os.open(mode_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
            os.close(mode_handle)
            download_mode = mode_path.stat().st_mode & 0o7777
            mode_path.unlink()
            owned_paths.discard(mode_path)
        os.chmod(download_stage, download_mode)

        paths_are_distinct = os.path.abspath(download_path) != os.path.abspath(target_path)
        target_stage: Optional[Path] = None
        if paths_are_distinct:
            target_mode = (
                target_path.stat().st_mode & 0o7777
                if target_path.is_file()
                else download_mode
            )
            target_stage = _stage_copy(download_stage, target_path, get_size, get_md5, target_mode)

        if not paths_are_distinct:
            os.replace(download_stage, download_path)
            owned_paths.discard(download_stage)
            return

        download_had_file = download_path.is_file()
        if download_had_file:
            rollback_handle, rollback_name = tempfile.mkstemp(
                prefix=f'.{download_path.name}.',
                suffix='.rollback',
                dir=download_path.parent,
            )
            rollback_candidate = Path(rollback_name)
            owned_paths.add(rollback_candidate)
            os.close(rollback_handle)
            shutil.copy2(download_path, rollback_candidate)
            with rollback_candidate.open('rb') as rollback_file:
                os.fsync(rollback_file.fileno())
            download_rollback = rollback_candidate
        os.replace(download_stage, download_path)
        owned_paths.discard(download_stage)
        download_published = True

        if target_stage is None:
            raise RuntimeError(f"No staged target available for {file}")
        os.replace(target_stage, target_path)
        owned_paths.discard(target_stage)

        if download_rollback is not None:
            try:
                download_rollback.unlink(missing_ok=True)
            except OSError as error:
                logging.warning("Could not remove download rollback file for %s: %s", file, type(error).__name__)
            owned_paths.discard(download_rollback)
    except Exception as error:
        if download_published and download_rollback is not None and download_rollback.exists():
            try:
                os.replace(download_rollback, download_path)
                owned_paths.discard(download_rollback)
            except OSError:
                # Keep the rollback copy if the destination cannot be restored.
                owned_paths.discard(download_rollback)
        elif download_published and not download_had_file:
            try:
                download_path.unlink(missing_ok=True)
            except OSError:
                pass
        for owned_path in owned_paths:
            try:
                owned_path.unlink(missing_ok=True)
            except OSError:
                pass
        logging.error("Failed to download %s: %s", file, type(error).__name__)
        app.exit(f"Failed to download {file}.")


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

    if target_props.size:
        logging.debug(f"File exists: {str(target_props.path)}")

    try_again = True
    last_size = None

    while try_again:
        try_again = False
        # Force non-compressed file transfer for accurate progress tracking.
        headers = {'Accept-Encoding': 'identity'}
        file_mode = 'wb'

        target_props = FileProps(target)  # sets path and size attribs
        # If file exists and URL is resumable, set download Range.
        if target_props.size:
            local_size = target_props.size
            logging.info(f"Current downloaded size in bytes: {local_size}")
            if url_props.headers.get('Accept-Ranges') == 'bytes':
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
            # If this was an incomplete read try again
            new_size = FileProps(target).size
            if (
                total_size is not None
                and new_size is not None
                and new_size < total_size 
                and (
                    last_size is None 
                    or new_size > last_size
                )
            ):
                logging.warning(f"Only downloaded a portion of the file on this attempt, retrying: {e}")
                try_again = True
                last_size = new_size
                continue

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


def _get_release_data(repository) -> GithubSoftwareReleasesInfo:
    """Gets latest release information
    
    Raises:
        Exception - on failure to make network operation or parse github API
        
    Returns:
        GithubSoftwareReleasesInfo
    """
    releases_url = f"https://api.github.com/repos/{repository}/releases"
    data = _net_get(releases_url)
    if data is None:
        logging.warning("Could not get releases from github.")
        return GithubSoftwareReleasesInfo(latest=None, pre_release=None)
    try:
        json_data: list[dict] = json.loads(data.decode())
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding Github's JSON response: {e}")
        raise

    json_data = sorted(json_data, key=lambda release: datetime.fromisoformat(release["updated_at"]), reverse=True)

    pre_release: Optional[SoftwareReleaseInfo] = None
    latest_release: Optional[SoftwareReleaseInfo] = None

    if json_data and json_data[0]["prerelease"]:
        pre_release = SoftwareReleaseInfo(
            version=_get_version_name(json_data[0]),
            download_url=_get_first_asset_url(json_data[0])
        )

    json_data = list(filter(lambda release: release["prerelease"] is False, json_data))

    if json_data:
        latest_release = SoftwareReleaseInfo(
            version=_get_version_name(json_data[0]),
            download_url=_get_first_asset_url(json_data[0])
        )

    return GithubSoftwareReleasesInfo(latest=latest_release, pre_release=pre_release)

def download_recommended_appimage(app: App):
    # Existing recommended AppImages must still pass through
    # logos_reuse_download so a partial or corrupt destination is
    # validated or replaced before use.
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
        logging.warning("Failed to get logos releases")
        return []

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

    # Do not execute a cached updater to inspect its version until
    # logos_reuse_download has validated or replaced it.
    logos_reuse_download(
        app.conf.app_latest_version_url,
        constants.BINARY_NAME,
        app.conf.download_dir,
        app=app,
    )
    logging.info("Checking if downloaded LLI binary is the latest version.")
    try:
        lli_download_ver = utils.get_lli_release_version(lli_download_path)
    except Exception as error:
        logging.error("Failed to inspect downloaded updater %s: %s", lli_download_path.name, type(error).__name__)
        lli_download_ver = None
    if not lli_download_ver or lli_download_ver != app.conf.app_latest_version:
        logging.info(f"Removing \"{lli_download_path}\", version: {lli_download_ver}")
        try:
            lli_download_path.unlink()
        except OSError as error:
            logging.error("Failed to remove mismatched updater %s: %s", lli_download_path.name, type(error).__name__)
        app.exit(f"Downloaded updater {lli_download_path.name} has an unexpected version.")
    shutil.copy(lli_download_path, temp_path)
    try:
        shutil.move(temp_path, lli_file_path)
    except Exception as e:
        logging.error(f"Failed to replace the binary: {e}")
        return

    os.chmod(sys.argv[0], os.stat(sys.argv[0]).st_mode | 0o111)
    logging.debug(f"Successfully updated {constants.APP_NAME}.")
    utils.restart_lli()
