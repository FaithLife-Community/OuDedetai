import abc
import binascii
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
from urllib.parse import urlparse, urlunparse
from xml.etree import ElementTree as ET
from datetime import datetime

import requests.structures

from ou_dedetai.app import App

from . import constants
from . import utils


# OuDedetai persists DEBUG logs, while urllib3's lower-level records include the
# raw request target. Keep those records out of application logs so query values
# cannot bypass the sanitized diagnostics below. Errors remain available.
logging.getLogger("urllib3").setLevel(logging.ERROR)


NETWORK_TIMEOUT = (10, 30)
"""Connect and read-inactivity timeouts, in seconds, for HTTP requests."""

MD5_DIGEST_SIZE = 16
"""The byte length of an MD5 digest, used without instantiating the algorithm."""


class DownloadError(Exception):
    """A download could not produce an accepted artifact or response body."""


class DownloadHTTPError(DownloadError):
    """The final HTTP response cannot represent a successful artifact transfer."""


class DownloadValidationError(DownloadError):
    """A downloaded or cached file did not satisfy required validation."""


def _safe_url_for_log(url: str) -> str:
    """Return a URL suitable for diagnostics without credentials or query data."""
    parsed = urlparse(url)
    authority = parsed.netloc.rsplit("@", 1)[-1]
    return urlunparse((parsed.scheme, authority, parsed.path, "", "", ""))


def _valid_base64_md5(value: object) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = value.strip().strip('"').strip("'")
    try:
        decoded = b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(decoded) != MD5_DIGEST_SIZE:
        return None
    return b64encode(decoded).decode()


def _size_and_md5_from_headers(
    headers: requests.structures.CaseInsensitiveDict | dict,
) -> tuple[Optional[int], Optional[str]]:
    """Extract trustworthy validation metadata for the represented bytes."""
    content_encoding = headers.get("Content-Encoding")
    if content_encoding is not None and content_encoding.lower() != "identity":
        logging.warning("Ignoring validation metadata for a content-encoded response.")
        return None, None

    size: Optional[int] = None
    content_length = headers.get("Content-Length")
    if content_length is not None:
        if not isinstance(content_length, str) or not content_length.isascii() or not content_length.isdecimal():
            logging.warning("Ignoring a malformed Content-Length header.")
        else:
            parsed_size = int(content_length)
            if parsed_size >= 0:
                size = parsed_size

    md5 = _valid_base64_md5(headers.get("Content-MD5"))
    if headers.get("Content-MD5") is not None and md5 is None:
        logging.warning("Ignoring a malformed Content-MD5 header.")

    if md5 is None and str(headers.get("Server", "")).lower() == "amazons3":
        etag = headers.get("ETag")
        if isinstance(etag, str):
            candidate = etag.strip()
            if (
                candidate.lower().startswith("w/")
                or len(candidate) < 2
                or candidate[0] != '"'
                or candidate[-1] != '"'
            ):
                candidate = ""
            else:
                candidate = candidate[1:-1]
            if len(candidate) == 32 and "-" not in candidate:
                try:
                    md5 = b64encode(bytes.fromhex(candidate)).decode()
                except ValueError:
                    md5 = None
        if etag is not None and md5 is None:
            logging.warning("Ignoring an ETag that is not a strong single-part MD5 value.")

    return size, md5


def _require_download_status(response: requests.Response, safe_url: str) -> None:
    if response.status_code != requests.codes.ok:
        if (
            urlparse(safe_url).netloc in {"github.com", "api.github.com"}
            and response.status_code in {403, 429}
        ):
            message = "GitHub API rate limit exceeded."
            reset = response.headers.get("x-ratelimit-reset")
            if reset is not None:
                try:
                    seconds_until_reset = max(0, ceil(int(reset) - time.time()))
                except (TypeError, ValueError):
                    pass
                else:
                    if seconds_until_reset < 120:
                        wait = f"{seconds_until_reset} seconds"
                    else:
                        wait = f"{ceil(seconds_until_reset / 60)} minutes"
                    message += f" Please wait {wait} before trying again."
            logging.error(message)
        raise DownloadHTTPError(
            f"GET for {safe_url} returned unsupported status {response.status_code}."
        )


def _remove_staging_file(staging_path: Optional[Path]) -> None:
    if staging_path is None:
        return
    try:
        staging_path.unlink(missing_ok=True)
    except OSError as error:
        logging.warning(
            "Failed to remove owned staging file %s (%s).",
            staging_path.name,
            type(error).__name__,
        )


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
        try:
            md5 = hashlib.md5(usedforsecurity=False)
            with self.path.open('rb') as f:
                for chunk in iter(lambda: f.read(524288), b''):
                    md5.update(chunk)
        except (TypeError, ValueError) as error:
            raise DownloadError(
                f"Could not calculate the MD5 checksum for {self.path.name} "
                f"({type(error).__name__})."
            ) from error
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
        safe_url = _safe_url_for_log(self.path)
        logging.debug("Getting headers from %s.", safe_url)
        try:
            h = {'Accept-Encoding': 'identity'}  # force non-compressed txfr
            with requests.head(
                self.path,
                allow_redirects=True,
                headers=h,
                timeout=NETWORK_TIMEOUT,
            ) as response:
                if response.status_code != requests.codes.ok:
                    logging.warning(
                        "Metadata probe for %s returned status %s; a fresh GET is required.",
                        safe_url,
                        response.status_code,
                    )
                    return requests.structures.CaseInsensitiveDict()
                return requests.structures.CaseInsensitiveDict(response.headers)
        except (
            requests.exceptions.MissingSchema,
            requests.exceptions.InvalidSchema,
            requests.exceptions.InvalidURL,
        ):
            raise
        except requests.exceptions.RequestException as error:
            logging.warning(
                "Metadata probe for %s failed (%s); a fresh GET is required.",
                safe_url,
                type(error).__name__,
            )
            return requests.structures.CaseInsensitiveDict()

    def _get_size(self):
        self._size = _size_and_md5_from_headers(self.headers)[0]
        logging.debug("Content length: %s", self._size)
        return self._size

    def _get_md5(self):
        self._md5 = _size_and_md5_from_headers(self.headers)[1]
        logging.debug("Content MD5 available: %s", self._md5 is not None)
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
        cached = self._cache.url_size_and_hash.get(url)
        cache_changed = False
        if isinstance(cached, (list, tuple)) and len(cached) == 2:
            size = cached[0] if isinstance(cached[0], int) and not isinstance(cached[0], bool) else None
            if size is not None and size < 0:
                size = None
            md5 = _valid_base64_md5(cached[1])
            if size is not None or md5 is not None:
                normalized = (size, md5)
                if cached != normalized:
                    self._cache.url_size_and_hash[url] = normalized
                    self._cache._write()
                return normalized

        if url in self._cache.url_size_and_hash:
            del self._cache.url_size_and_hash[url]
            cache_changed = True

        props = UrlProps(url)
        metadata = props.size, props.md5
        if metadata[0] is not None or metadata[1] is not None:
            self._cache.url_size_and_hash[url] = metadata
            cache_changed = True

        if cache_changed:
            self._cache._write()
        return metadata

    def url_size_and_hash(self, url: str) -> tuple[Optional[int], Optional[str]]:
        return self._url_size_and_hash(url)

    def url_size(self, url: str) -> Optional[int]:
        return self.url_size_and_hash(url)[0]
    
    def url_md5(self, url: str) -> Optional[str]:
        return self.url_size_and_hash(url)[1]

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


def _verify_downloaded_file(
    file_path: Path | str,
    *,
    expected_size: Optional[int],
    expected_md5: Optional[str],
    require_metadata: bool,
) -> None:
    """Validate a file against every trustworthy value supplied by the caller."""
    path = Path(file_path)
    if expected_size is None and expected_md5 is None:
        if require_metadata:
            raise DownloadValidationError(
                f"Cannot reuse {path.name} without trustworthy remote metadata."
            )
        return

    try:
        file_props = FileProps(path)
        if expected_size is not None and file_props.size != expected_size:
            raise DownloadValidationError(f"{path.name} has the wrong size.")
        if expected_md5 is not None and file_props.md5 != expected_md5:
            raise DownloadValidationError(f"{path.name} has the wrong MD5 sum.")
    except DownloadValidationError:
        raise
    except OSError as error:
        raise DownloadError(
            f"Could not read {path.name} for validation ({type(error).__name__})."
        ) from error

    if expected_md5 is not None:
        logging.debug("%s matched the available MD5 digest.", path.name)
    elif expected_size is not None:
        logging.debug("%s matched the available content length.", path.name)


def _copy_validated_file(
    source: Path,
    target: Path,
    *,
    expected_size: Optional[int],
    expected_md5: Optional[str],
) -> Path:
    try:
        if source.samefile(target) and not target.is_symlink():
            return target
    except FileNotFoundError:
        pass
    except OSError as error:
        raise DownloadError(
            f"Could not compare cached and target paths ({type(error).__name__})."
        ) from error

    staging_path: Optional[Path] = None
    try:
        with source.open("rb") as source_file:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{target.name}.",
                suffix=".part",
                dir=target.parent,
                delete=False,
            ) as staging_file:
                staging_path = Path(staging_file.name)
                shutil.copyfileobj(source_file, staging_file)
                staging_file.flush()
                os.fsync(staging_file.fileno())
        shutil.copymode(source, staging_path)
        _verify_downloaded_file(
            staging_path,
            expected_size=expected_size,
            expected_md5=expected_md5,
            require_metadata=True,
        )
        os.replace(staging_path, target)
        staging_path = None
        return target
    except DownloadError:
        raise
    except OSError as error:
        raise DownloadError(
            f"Could not safely copy {source.name} ({type(error).__name__})."
        ) from error
    finally:
        _remove_staging_file(staging_path)


def _download_file(url: str, target: Path, app: Optional[App] = None) -> Path:
    """Download a fresh artifact to staging, validate it, then publish it."""
    target = Path(target)
    safe_url = _safe_url_for_log(url)
    logging.debug("Download source: %s", safe_url)
    logging.debug("Download destination name: %s", target.name)
    if app:
        app.status(f"Downloading {target.name}…", 0)

    staging_path: Optional[Path] = None
    headers = {'Accept-Encoding': 'identity'}
    try:
        with requests.get(
            url,
            stream=True,
            headers=headers,
            allow_redirects=True,
            timeout=NETWORK_TIMEOUT,
        ) as response:
            _require_download_status(response, safe_url)
            expected_size, expected_md5 = _size_and_md5_from_headers(response.headers)
            chunk_size = 100 * 1024
            if expected_size is not None:
                chunk_size = max(1, min(expected_size // 50, 2 * 1024 * 1024))

            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{target.name}.",
                suffix=".part",
                dir=target.parent,
                delete=False,
            ) as staging_file:
                staging_path = Path(staging_file.name)
                local_size = 0
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if not chunk:
                        continue
                    staging_file.write(chunk)
                    local_size += len(chunk)
                    if app and expected_size:
                        app.status(
                            f"Downloading {target.name}…",
                            min(local_size / expected_size, 1),
                        )
                staging_file.flush()
                os.fsync(staging_file.fileno())

        if app:
            app.status(f"Verifying {target.name}…", 0)
        _verify_downloaded_file(
            staging_path,
            expected_size=expected_size,
            expected_md5=expected_md5,
            require_metadata=False,
        )
        if expected_size is None and expected_md5 is None:
            logging.info(
                "Transfer of %s completed without size or digest metadata.",
                target.name,
            )
        os.replace(staging_path, target)
        staging_path = None
        return target
    except DownloadError:
        raise
    except requests.exceptions.RequestException as error:
        raise DownloadError(
            f"GET for {safe_url} failed ({type(error).__name__})."
        ) from error
    except OSError as error:
        raise DownloadError(
            f"Could not stage or publish {target.name} ({type(error).__name__})."
        ) from error
    finally:
        _remove_staging_file(staging_path)


def _net_get(url: str) -> bytes:
    """Retrieve an in-memory response body from a final 200 response."""
    safe_url = _safe_url_for_log(url)
    logging.debug("Retrieving data from %s.", safe_url)
    headers = {'Accept-Encoding': 'identity'}
    try:
        with requests.get(
            url,
            headers=headers,
            allow_redirects=True,
            timeout=NETWORK_TIMEOUT,
        ) as response:
            _require_download_status(response, safe_url)
            return response.content
    except DownloadError:
        raise
    except requests.exceptions.RequestException as error:
        raise DownloadError(
            f"GET for {safe_url} failed ({type(error).__name__})."
        ) from error


def logos_reuse_download(
    sourceurl: str,
    file: str,
    targetdir: str,
    app: App,
    status_messages: bool = True,
    *,
    reuse_existing: bool = True,
) -> Path:
    """Reuse a verifiable cache entry or publish a fresh accepted download."""
    target_path = Path(targetdir) / file
    try:
        if reuse_existing:
            try:
                expected_size, expected_md5 = app.conf._network.url_size_and_hash(sourceurl)
            except requests.exceptions.RequestException as error:
                raise DownloadError(
                    f"Invalid download URL for {file} ({type(error).__name__})."
                ) from error
            except OSError as error:
                logging.warning(
                    "Metadata cache access for %s failed (%s); a fresh GET is required.",
                    file,
                    type(error).__name__,
                )
                expected_size, expected_md5 = None, None

            if expected_size is not None or expected_md5 is not None:
                seen_paths: set[Path] = set()
                directories: tuple[Optional[str], Optional[str], Optional[str]] = (
                    app.conf.user_download_dir,
                    app.conf.download_dir,
                    targetdir,
                )
                for directory in directories:
                    if directory is None:
                        continue
                    candidate = Path(directory) / file
                    candidate_key = candidate.absolute()
                    if candidate_key in seen_paths or not candidate.is_file():
                        continue
                    seen_paths.add(candidate_key)
                    logging.info("Found cached %s; checking available metadata.", file)
                    if status_messages:
                        app.status(f"Verifying {file}…", 0)
                    try:
                        _verify_downloaded_file(
                            candidate,
                            expected_size=expected_size,
                            expected_md5=expected_md5,
                            require_metadata=True,
                        )
                    except DownloadError as error:
                        logging.info("Cached %s is not reusable: %s", file, error)
                        continue
                    return _copy_validated_file(
                        candidate,
                        target_path,
                        expected_size=expected_size,
                        expected_md5=expected_md5,
                    )
            else:
                logging.info("No trustworthy metadata is available to reuse cached %s.", file)

        return _download_file(sourceurl, target_path, app=app)
    except DownloadError as error:
        logging.error("Failed to obtain %s: %s", file, error)
        app.exit(f"Failed to download {file}: {error}")


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
    try:
        data = _net_get(releases_url)
    except DownloadError:
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

def download_recommended_appimage(app: App) -> Path:
    wine64_appimage_full_filename = Path(app.conf.wine_appimage_recommended_file_name)
    return logos_reuse_download(
        app.conf.wine_appimage_recommended_url,
        wine64_appimage_full_filename.name,
        app.conf.installer_binary_dir,
        app=app,
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
    
    try:
        response_xml_bytes = _net_get(url)
    except DownloadError:
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
    temp_path = Path(app.conf.download_dir) / f"{constants.BINARY_NAME}.tmp"
    logging.debug(
        f"Updating {constants.APP_NAME} to latest version by overwriting: {lli_file_path}")

    lli_download_path = logos_reuse_download(
        app.conf.app_latest_version_url,
        constants.BINARY_NAME,
        app.conf.download_dir,
        app=app,
        reuse_existing=False,
    )
    lli_download_ver = utils.get_lli_release_version(lli_download_path)
    if not lli_download_ver or lli_download_ver != app.conf.app_latest_version:
        app.exit(
            f"Downloaded {constants.APP_NAME} version {lli_download_ver!r} does not match "
            f"expected version {app.conf.app_latest_version}."
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
