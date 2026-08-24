import hashlib
import logging
import os
import socket
import stat
import tempfile
import threading
import unittest
from base64 import b64encode
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from requests.exceptions import MissingSchema

import ou_dedetai.installer as installer
import ou_dedetai.network as network
import ou_dedetai.system as system
import ou_dedetai.utils as utils
import ou_dedetai.wine as wine
from ou_dedetai import constants


def _md5(data: bytes) -> str:
    return b64encode(hashlib.md5(data, usedforsecurity=False).digest()).decode()


class _Response:
    def __init__(
        self,
        status_code=200,
        *,
        headers=None,
        content=b"",
        chunks=None,
        stream_error=None,
    ):
        self.status_code = status_code
        self.headers = requests.structures.CaseInsensitiveDict(headers or {})
        self._content = content
        self.chunks = list(chunks if chunks is not None else [content])
        self.stream_error = stream_error
        self.iterated = False
        self.content_read = False

    @property
    def content(self):
        self.content_read = True
        return self._content

    def iter_content(self, chunk_size):
        self.iterated = True
        for chunk in self.chunks:
            yield chunk
        if self.stream_error is not None:
            raise self.stream_error

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class _FailingFile:
    def __init__(self, wrapped, failing_method):
        self._wrapped = wrapped
        self._failing_method = failing_method
        self.name = wrapped.name

    def __enter__(self):
        self._wrapped.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        result = self._wrapped.__exit__(exc_type, exc_value, traceback)
        if self._failing_method == "close" and exc_type is None:
            raise OSError("close failed")
        return result

    def write(self, data):
        if self._failing_method == "write":
            raise OSError("write failed")
        return self._wrapped.write(data)

    def flush(self):
        if self._failing_method == "flush":
            raise OSError("flush failed")
        return self._wrapped.flush()

    def fileno(self):
        return self._wrapped.fileno()


class _LocalArtifactHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        return

    def _route(self):
        self.server.observed_requests.append(
            (self.command, self.path, dict(self.headers.items()))
        )
        return self.server.routes[self.path]

    def _send_headers(self, status, headers, body, omit_content_length=False):
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        if not omit_content_length and "Content-Length" not in headers:
            self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

    def do_HEAD(self):
        route = self._route()
        status = route.get("head_status", 200)
        headers = route.get("head_headers", {})
        self._send_headers(status, headers, b"")

    def do_GET(self):
        route = self._route()
        status = route.get("status", 200)
        body = route.get("body", b"")
        headers = route.get("headers", {})
        self._send_headers(
            status,
            headers,
            body,
            omit_content_length=route.get("omit_content_length", False),
        )
        interrupt_after = route.get("interrupt_after")
        if interrupt_after is None:
            self.wfile.write(body)
            return
        self.wfile.write(body[:interrupt_after])
        self.wfile.flush()
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.connection.close()


class _LocalArtifactServer:
    def __init__(self, routes):
        self.routes = routes
        self.observed_requests = []
        self.httpd = None
        self.thread = None

    def __enter__(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _LocalArtifactHandler)
        self.httpd.routes = self.routes
        self.httpd.observed_requests = self.observed_requests
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            raise RuntimeError("Local artifact server did not stop.")

    def url(self, path):
        host, port = self.httpd.server_address
        return f"http://{host}:{port}{path}"


class _LiveMetadata:
    def url_size_and_hash(self, url):
        props = network.UrlProps(url)
        return props.size, props.md5


def _app(download_dir: Path, user_download_dir: Path | None = None):
    app = Mock()
    app.conf.download_dir = str(download_dir)
    app.conf.user_download_dir = str(user_download_dir or download_dir)
    app.conf._network = Mock()
    app.exit.side_effect = SystemExit
    return app


def _write_file(directory: str | Path, name: str, content: bytes) -> Path:
    path = Path(directory) / name
    path.write_bytes(content)
    return path


def _appimage_installer_app() -> Mock:
    app = Mock()
    app.installer_step_count = 0
    app.installer_step = 0
    app.conf.faithlife_product_version = "10"
    app.conf.wine_binary = constants.WINE_RECOMMENDED_SIGIL
    app.conf.wine_appimage_recommended_file_name = "wine.AppImage"
    app.conf.wine_appimage_recommended_url = "https://example.test/wine.AppImage"
    app.conf.installer_binary_dir = "/install/bin"
    return app


def _icu_app() -> Mock:
    app = Mock()
    app.conf.icu_latest_version_url = "https://example.test/icu.tar.gz"
    app.conf.icu_latest_version = "1"
    app.conf.download_dir = "/cache"
    app.conf.wine_prefix = "/wine"
    return app


def _winetricks_app(directory: str) -> Mock:
    app = Mock()
    app.conf.installer_binary_dir = directory
    app.conf.wine_binary_code = "System"
    app.conf.wine_appimage_path = None
    app.conf.download_dir = directory
    return app


def _self_update_app() -> Mock:
    app = Mock()
    app.conf.download_dir = "/cache"
    app.conf.app_latest_version_url = "https://example.test/oudedetai"
    app.conf.app_latest_version = "9.9.9"
    return app


class TestFileProps(unittest.TestCase):
    def test_get_size_and_md5(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = _write_file(directory, "file.json", b"{\n}\n")
            props = network.FileProps(file_path)
            self.assertEqual(props.size, 4)
            self.assertEqual(props.md5, "W3aw7vmviiMAZz4FU/YJ+Q==")

    def test_md5_uses_nonsecurity_mode_on_fips_systems(self):
        real_md5 = hashlib.md5

        def fips_md5(*args, **kwargs):
            if kwargs.get("usedforsecurity", True):
                raise ValueError("FIPS MD5 disabled")
            return real_md5(*args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            file_path = _write_file(directory, "file.json", b"{\n}\n")
            with patch("ou_dedetai.network.hashlib.md5", side_effect=fips_md5) as mock_md5:
                self.assertEqual(network.FileProps(file_path).md5, "W3aw7vmviiMAZz4FU/YJ+Q==")

        mock_md5.assert_called_once_with(usedforsecurity=False)

    def test_unavailable_md5_raises_typed_download_error(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = _write_file(directory, "file.json", b"{\n}\n")
            with patch(
                "ou_dedetai.network.hashlib.md5",
                side_effect=ValueError("MD5 unavailable"),
            ):
                with self.assertRaisesRegex(network.DownloadError, "Could not calculate the MD5 checksum"):
                    network.FileProps(file_path).md5


class TestUrlProps(unittest.TestCase):
    @patch("ou_dedetai.network.requests.head")
    def test_success_uses_finite_timeout_and_final_headers(self, mock_head):
        mock_head.return_value = _Response(
            headers={"Content-Length": "4", "Content-MD5": _md5(b"data")}
        )

        props = network.UrlProps("https://example.test/artifact?token=secret")

        self.assertEqual(props.size, 4)
        self.assertEqual(props.md5, _md5(b"data"))
        mock_head.assert_called_once_with(
            "https://example.test/artifact?token=secret",
            allow_redirects=True,
            headers={"Accept-Encoding": "identity"},
            timeout=network.NETWORK_TIMEOUT,
        )

    @patch("ou_dedetai.network.requests.head")
    def test_non_200_statuses_supply_no_metadata(self, mock_head):
        for status in (201, 301, 204, 304, 404, 405, 416, 500, 501):
            with self.subTest(status=status):
                mock_head.return_value = _Response(
                    status,
                    headers={"Content-Length": "4", "Content-MD5": _md5(b"data")},
                )
                props = network.UrlProps("https://example.test/artifact")
                self.assertIsNone(props.size)
                self.assertIsNone(props.md5)

    def test_transport_failures_supply_no_metadata(self):
        for failure in (
            requests.ConnectTimeout,
            requests.ReadTimeout,
            requests.ConnectionError,
        ):
            with self.subTest(failure=failure.__name__):
                with patch(
                    "ou_dedetai.network.requests.head", side_effect=failure
                ) as mock_head:
                    props = network.UrlProps("https://example.test/artifact")

                    self.assertEqual(props.headers, {})
                    self.assertEqual(
                        mock_head.call_args.kwargs["timeout"], network.NETWORK_TIMEOUT
                    )

    @patch("ou_dedetai.network.requests.head", side_effect=MissingSchema)
    def test_invalid_url_remains_visible(self, mock_head):
        with self.assertRaises(MissingSchema):
            network.UrlProps("").headers


class TestHeaderMetadata(unittest.TestCase):
    def test_content_length_and_content_md5(self):
        self.assertEqual(
            network._size_and_md5_from_headers(
                {"Content-Length": "4", "Content-MD5": _md5(b"data")}
            ),
            (4, _md5(b"data")),
        )

    def test_content_md5_parsing_does_not_instantiate_md5(self):
        digest = _md5(b"data")
        with patch(
            "ou_dedetai.network.hashlib.md5",
            side_effect=ValueError("MD5 unavailable"),
        ) as mock_md5:
            self.assertEqual(
                network._size_and_md5_from_headers({"Content-MD5": digest}),
                (None, digest),
            )
        mock_md5.assert_not_called()

    def test_malformed_metadata_is_ignored(self):
        for length, digest in (
            ("bad", "not-base64"),
            ("-1", _md5(b"too short")[:-4]),
            ("+1", "not-base64"),
            (" 1", "not-base64"),
            ("²", "not-base64"),
        ):
            with self.subTest(length=length, digest=digest):
                self.assertEqual(
                    network._size_and_md5_from_headers(
                        {"Content-Length": length, "Content-MD5": digest}
                    ),
                    (None, None),
                )

    def test_content_encoding_makes_metadata_incompatible(self):
        self.assertEqual(
            network._size_and_md5_from_headers(
                {
                    "Content-Encoding": "gzip",
                    "Content-Length": "4",
                    "Content-MD5": _md5(b"data"),
                }
            ),
            (None, None),
        )

    def test_only_strong_single_part_s3_etag_is_md5(self):
        valid_hex = hashlib.md5(b"data", usedforsecurity=False).hexdigest()
        self.assertEqual(
            network._size_and_md5_from_headers(
                {"Server": "AmazonS3", "ETag": f'"{valid_hex}"'}
            ),
            (None, _md5(b"data")),
        )
        for etag in (
            f'W/"{valid_hex}"',
            f'"{valid_hex}-2"',
            f'"{valid_hex[:-1]}"',
            f'"{"z" * 32}"',
            valid_hex,
            f"'{valid_hex}'",
        ):
            with self.subTest(etag=etag):
                self.assertEqual(
                    network._size_and_md5_from_headers(
                        {"Server": "AmazonS3", "ETag": etag}
                    ),
                    (None, None),
                )
        self.assertEqual(
            network._size_and_md5_from_headers({"Server": "nginx", "ETag": f'"{valid_hex}"'}),
            (None, None),
        )


class TestMetadataCache(unittest.TestCase):
    def setUp(self):
        self.requests = network.NetworkRequests.__new__(network.NetworkRequests)
        self.requests._cache = network.CachedRequests()

    @patch("ou_dedetai.network.UrlProps")
    def test_successful_metadata_is_cached(self, mock_props):
        mock_props.return_value.size = 4
        mock_props.return_value.md5 = _md5(b"data")
        with patch.object(self.requests._cache, "_write") as mock_write:
            first = self.requests.url_size_and_hash("https://example.test/artifact")
            second = self.requests.url_size_and_hash("https://example.test/artifact")

        self.assertEqual(first, (4, _md5(b"data")))
        self.assertEqual(second, first)
        mock_props.assert_called_once()
        mock_write.assert_called_once()

    @patch("ou_dedetai.network.UrlProps")
    def test_metadata_absence_is_not_cached(self, mock_props):
        mock_props.return_value.size = None
        mock_props.return_value.md5 = None
        with patch.object(self.requests._cache, "_write") as mock_write:
            self.assertEqual(self.requests.url_size_and_hash("https://example.test/artifact"), (None, None))
            self.assertEqual(self.requests.url_size_and_hash("https://example.test/artifact"), (None, None))

        self.assertEqual(mock_props.call_count, 2)
        mock_write.assert_not_called()

    @patch("ou_dedetai.network.UrlProps")
    def test_legacy_null_entry_is_pruned_and_reprobed(self, mock_props):
        url = "https://example.test/artifact"
        self.requests._cache.url_size_and_hash[url] = [None, None]
        mock_props.return_value.size = None
        mock_props.return_value.md5 = None
        with patch.object(self.requests._cache, "_write") as mock_write:
            self.assertEqual(self.requests.url_size_and_hash(url), (None, None))

        self.assertNotIn(url, self.requests._cache.url_size_and_hash)
        mock_props.assert_called_once_with(url)
        mock_write.assert_called_once()


class TestMemoryGet(unittest.TestCase):
    @patch("ou_dedetai.network.requests.get")
    def test_final_200_returns_bytes_with_timeout(self, mock_get):
        mock_get.return_value = _Response(content=b"payload")

        self.assertEqual(network._net_get("https://example.test/data"), b"payload")
        mock_get.assert_called_once_with(
            "https://example.test/data",
            headers={"Accept-Encoding": "identity"},
            allow_redirects=True,
            timeout=network.NETWORK_TIMEOUT,
        )

    @patch("ou_dedetai.network.requests.get")
    def test_unsupported_status_body_is_not_returned(self, mock_get):
        for status in (201, 301, 204, 206, 304, 404, 416, 500):
            with self.subTest(status=status):
                response = _Response(status, content=b"error body")
                mock_get.return_value = response
                with self.assertRaises(network.DownloadHTTPError):
                    network._net_get("https://example.test/data")
                self.assertFalse(response.content_read)

    def test_transport_failures_raise_download_error(self):
        for failure in (
            requests.ConnectTimeout,
            requests.ReadTimeout,
            requests.ConnectionError,
        ):
            with self.subTest(failure=failure.__name__):
                with patch("ou_dedetai.network.requests.get", side_effect=failure):
                    with self.assertRaises(network.DownloadError):
                        network._net_get("https://example.test/data")

    @patch("ou_dedetai.network.requests.get", side_effect=requests.ConnectTimeout)
    def test_error_diagnostics_redact_url_secrets(self, mock_get):
        with self.assertRaises(network.DownloadError) as caught:
            network._net_get(
                "https://user:password@example.test/data?token=secret#private"
            )

        message = str(caught.exception)
        self.assertIn("https://example.test/data", message)
        for secret in ("user", "password", "token", "secret", "private"):
            self.assertNotIn(secret, message)

    @patch("ou_dedetai.network._net_get", side_effect=network.DownloadError("offline"))
    def test_release_callers_keep_empty_offline_fallbacks(self, mock_get):
        releases = network._get_release_data("owner/repository")
        faithlife = network._get_faithlife_product_releases("Logos", "10", "stable")

        self.assertIsNone(releases.latest)
        self.assertIsNone(releases.pre_release)
        self.assertEqual(faithlife, [])


class TestFileDownload(unittest.TestCase):
    def _stages(self, target):
        return list(target.parent.glob(f".{target.name}.*.part"))

    @patch("ou_dedetai.network.requests.get")
    def test_valid_200_publishes_once_and_returns_target(self, mock_get):
        payload = b"complete artifact"
        mock_get.return_value = _Response(
            headers={"Content-Length": str(len(payload)), "Content-MD5": _md5(payload)},
            chunks=[payload[:5], b"", payload[5:]],
        )
        with tempfile.TemporaryDirectory() as directory:
            target = _write_file(directory, "artifact", b"old valid content")

            real_replace = os.replace
            with patch("ou_dedetai.network.os.replace", side_effect=real_replace) as mock_replace:
                with patch("ou_dedetai.network.requests.head") as mock_head:
                    result = network._download_file("https://example.test/artifact", target)

            self.assertEqual(result, target)
            self.assertEqual(target.read_bytes(), payload)
            self.assertEqual(self._stages(target), [])
            mock_replace.assert_called_once()
            staging_arg, target_arg = mock_replace.call_args.args
            self.assertEqual(Path(staging_arg).parent, target.parent)
            self.assertEqual(target_arg, target)
            mock_head.assert_not_called()
        call_headers = mock_get.call_args.kwargs["headers"]
        self.assertNotIn("Range", call_headers)
        self.assertTrue(mock_get.call_args.kwargs["stream"])
        self.assertTrue(mock_get.call_args.kwargs["allow_redirects"])
        self.assertEqual(mock_get.call_args.kwargs["timeout"], network.NETWORK_TIMEOUT)

    @patch("ou_dedetai.network.requests.get")
    def test_fresh_200_without_metadata_is_transport_complete(self, mock_get):
        mock_get.return_value = _Response(chunks=[b"fresh", b" data"])
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "artifact"

            with patch("ou_dedetai.network.logging.info") as mock_info:
                self.assertEqual(
                    network._download_file("https://example.test/artifact", target),
                    target,
                )
            self.assertEqual(target.read_bytes(), b"fresh data")
            mock_info.assert_called_once_with(
                "Transfer of %s completed without size or digest metadata.",
                target.name,
            )

    @patch("ou_dedetai.network.requests.get")
    def test_fresh_200_accepts_each_available_validator(self, mock_get):
        payload = b"fresh data"
        for headers in (
            {"Content-Length": str(len(payload))},
            {"Content-MD5": _md5(payload)},
        ):
            with self.subTest(headers=headers):
                mock_get.return_value = _Response(headers=headers, content=payload)
                with tempfile.TemporaryDirectory() as directory:
                    target = Path(directory) / "artifact"

                    self.assertEqual(
                        network._download_file("https://example.test/artifact", target),
                        target,
                    )
                    self.assertEqual(target.read_bytes(), payload)

    @patch("ou_dedetai.network.requests.get")
    def test_unsupported_status_never_writes_body_or_target(self, mock_get):
        with tempfile.TemporaryDirectory() as directory:
            target = _write_file(directory, "artifact", b"sentinel")
            for status in (201, 301, 204, 206, 304, 404, 416, 500):
                with self.subTest(status=status):
                    response = _Response(status, content=b"error body")
                    mock_get.return_value = response
                    with self.assertRaises(network.DownloadHTTPError):
                        network._download_file("https://example.test/artifact", target)
                    self.assertEqual(target.read_bytes(), b"sentinel")
                    self.assertFalse(response.iterated)
                    self.assertEqual(self._stages(target), [])

    def test_connect_and_read_timeout_preserve_target(self):
        for failure in (requests.ConnectTimeout, requests.ReadTimeout):
            with self.subTest(failure=failure.__name__):
                with patch("ou_dedetai.network.requests.get", side_effect=failure):
                    with tempfile.TemporaryDirectory() as directory:
                        target = _write_file(directory, "artifact", b"sentinel")

                        with self.assertRaises(network.DownloadError):
                            network._download_file(
                                "https://example.test/artifact", target
                            )

                        self.assertEqual(target.read_bytes(), b"sentinel")

    @patch("ou_dedetai.network.requests.get")
    def test_retry_after_interruption_restarts_from_byte_zero(self, mock_get):
        payload = b"complete"
        mock_get.side_effect = (
            _Response(
                chunks=[b"partial"],
                stream_error=requests.exceptions.ChunkedEncodingError("interrupted"),
            ),
            _Response(headers={"Content-Length": str(len(payload))}, content=payload),
        )
        with tempfile.TemporaryDirectory() as directory:
            target = _write_file(directory, "artifact", b"sentinel")

            with self.assertRaises(network.DownloadError):
                network._download_file("https://example.test/artifact", target)
            self.assertEqual(target.read_bytes(), b"sentinel")
            self.assertEqual(self._stages(target), [])

            network._download_file("https://example.test/artifact", target)

            self.assertEqual(target.read_bytes(), payload)
            self.assertEqual(mock_get.call_count, 2)
            for call in mock_get.call_args_list:
                self.assertNotIn("Range", call.kwargs["headers"])

    @patch("ou_dedetai.network.requests.get")
    def test_success_replaces_target_symlink_instead_of_following_it(self, mock_get):
        payload = b"fresh"
        mock_get.return_value = _Response(
            headers={"Content-Length": str(len(payload))}, content=payload
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            linked_file = _write_file(root, "linked", b"linked sentinel")
            target = root / "artifact"
            target.symlink_to(linked_file)

            network._download_file("https://example.test/artifact", target)

            self.assertFalse(target.is_symlink())
            self.assertEqual(target.read_bytes(), payload)
            self.assertEqual(linked_file.read_bytes(), b"linked sentinel")

    @patch("ou_dedetai.network.requests.get")
    def test_size_and_digest_mismatch_preserve_target(self, mock_get):
        cases = (
            ({"Content-Length": "99"}, b"short"),
            ({"Content-MD5": _md5(b"expected")}, b"different"),
        )
        with tempfile.TemporaryDirectory() as directory:
            target = _write_file(directory, "artifact", b"sentinel")
            for headers, payload in cases:
                with self.subTest(headers=headers):
                    mock_get.return_value = _Response(headers=headers, content=payload)
                    with self.assertRaises(network.DownloadValidationError):
                        network._download_file("https://example.test/artifact", target)
                    self.assertEqual(target.read_bytes(), b"sentinel")
                    self.assertEqual(self._stages(target), [])

    @patch("ou_dedetai.network.requests.get")
    def test_write_flush_and_close_failures_preserve_target(self, mock_get):
        payload = b"payload"
        mock_get.return_value = _Response(
            headers={"Content-Length": str(len(payload))},
            content=payload,
        )
        real_named_temporary_file = tempfile.NamedTemporaryFile
        with tempfile.TemporaryDirectory() as directory:
            target = _write_file(directory, "artifact", b"sentinel")
            for failing_method in ("write", "flush", "close"):
                with self.subTest(failing_method=failing_method):
                    def failing_file(*args, **kwargs):
                        return _FailingFile(real_named_temporary_file(*args, **kwargs), failing_method)

                    with patch("ou_dedetai.network.tempfile.NamedTemporaryFile", side_effect=failing_file):
                        with self.assertRaises(network.DownloadError):
                            network._download_file("https://example.test/artifact", target)
                    self.assertEqual(target.read_bytes(), b"sentinel")
                    self.assertEqual(self._stages(target), [])

    @patch("ou_dedetai.network.requests.get")
    def test_validation_read_and_publication_failures_preserve_target(self, mock_get):
        payload = b"payload"
        mock_get.return_value = _Response(headers={"Content-MD5": _md5(payload)}, content=payload)
        with tempfile.TemporaryDirectory() as directory:
            target = _write_file(directory, "artifact", b"sentinel")

            with patch("ou_dedetai.network.FileProps._get_md5", side_effect=OSError("read failed")):
                with self.assertRaises(network.DownloadError):
                    network._download_file("https://example.test/artifact", target)
            self.assertEqual(target.read_bytes(), b"sentinel")

            with patch("ou_dedetai.network.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaises(network.DownloadError):
                    network._download_file("https://example.test/artifact", target)
            self.assertEqual(target.read_bytes(), b"sentinel")
            self.assertEqual(self._stages(target), [])

    def test_cleanup_failure_is_best_effort(self):
        staging_path = Mock()
        staging_path.unlink.side_effect = OSError("cleanup failed")

        network._remove_staging_file(staging_path)

        staging_path.unlink.assert_called_once_with(missing_ok=True)


class TestLocalHTTPIntegration(unittest.TestCase):
    @staticmethod
    def _stages(target):
        return list(target.parent.glob(f".{target.name}.*.part"))

    def test_error_bodies_never_replace_an_existing_target(self):
        routes = {
            "/not-found": {"status": 404, "body": b"not found"},
            "/server-error": {"status": 500, "body": b"server error"},
        }
        with _LocalArtifactServer(routes) as server:
            with tempfile.TemporaryDirectory() as directory:
                for path in routes:
                    with self.subTest(path=path):
                        target = _write_file(directory, "artifact", b"sentinel")

                        with self.assertRaises(network.DownloadHTTPError):
                            network._download_file(server.url(path), target)

                        self.assertEqual(target.read_bytes(), b"sentinel")
                        self.assertEqual(self._stages(target), [])

        self.assertTrue(server.observed_requests)
        self.assertTrue(all("Range" not in headers for _, _, headers in server.observed_requests))

    def test_actual_request_logs_redact_url_secrets(self):
        routes = {
            "/artifact?token=secret": {"body": b"payload"},
        }
        with _LocalArtifactServer(routes) as server:
            with tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "artifact"
                url = server.url("/artifact?token=secret#private").replace(
                    "http://", "http://user:password@", 1
                )

                previous_disable_level = logging.root.manager.disable
                logging.disable(logging.NOTSET)
                try:
                    with self.assertLogs(level=logging.DEBUG) as captured:
                        network._download_file(url, target)
                finally:
                    logging.disable(previous_disable_level)

                messages = "\n".join(captured.output)
                self.assertIn(server.url("/artifact"), messages)
                for secret in ("user", "password", "token", "secret", "private"):
                    self.assertNotIn(secret, messages)

                self.assertEqual(target.read_bytes(), b"payload")

        self.assertEqual(server.observed_requests[0][1], "/artifact?token=secret")

    def test_abrupt_short_stream_never_replaces_an_existing_target(self):
        payload = b"complete payload"
        routes = {
            "/interrupted": {
                "body": payload,
                "headers": {"Content-Length": str(len(payload))},
                "interrupt_after": 5,
            }
        }
        with _LocalArtifactServer(routes) as server:
            with tempfile.TemporaryDirectory() as directory:
                target = _write_file(directory, "artifact", b"sentinel")

                with self.assertRaises(network.DownloadError):
                    network._download_file(server.url("/interrupted"), target)

                self.assertEqual(target.read_bytes(), b"sentinel")
                self.assertEqual(self._stages(target), [])

        self.assertEqual(server.observed_requests[0][0], "GET")
        self.assertNotIn("Range", server.observed_requests[0][2])

    def test_unsupported_head_forces_a_complete_metadata_free_get(self):
        payload = b"fresh payload"
        routes = {
            "/artifact": {
                "head_status": 405,
                "body": payload,
                "omit_content_length": True,
            }
        }
        with _LocalArtifactServer(routes) as server:
            with tempfile.TemporaryDirectory() as directory:
                target = _write_file(directory, "artifact", b"sentinel")
                app = _app(target.parent)
                app.conf._network = _LiveMetadata()

                result = network.logos_reuse_download(
                    server.url("/artifact"), target.name, str(target.parent), app
                )

                self.assertEqual(result, target)
                self.assertEqual(target.read_bytes(), payload)
                self.assertEqual(self._stages(target), [])

        self.assertEqual(
            [method for method, _, _ in server.observed_requests],
            ["HEAD", "GET"],
        )
        self.assertNotIn("Range", server.observed_requests[1][2])

    def test_recommended_appimage_failure_and_success_preserve_link_contract(self):
        payload = b"fresh appimage"
        routes = {
            "/failed.AppImage": {"head_status": 405, "status": 500, "body": b"error"},
            "/wine.AppImage": {
                "head_status": 405,
                "body": payload,
                "omit_content_length": True,
            },
        }
        with _LocalArtifactServer(routes) as server:
            with tempfile.TemporaryDirectory() as directory:
                target_dir = Path(directory)
                target = _write_file(target_dir, "wine.AppImage", b"sentinel")
                old_target = _write_file(target_dir, "old.AppImage", b"old target")
                link = target_dir / "selected_wine.AppImage"
                link.symlink_to(old_target)

                app = _app(target_dir)
                app.conf._network = _LiveMetadata()
                app.conf.wine_binary_code = "Recommended"
                app.conf.wine_appimage_path = Path(target.name)
                app.conf.wine_appimage_recommended_file_name = target.name
                app.conf.installer_binary_dir = str(target_dir)
                app.conf.wine_appimage_link_file_name = link.name
                app.conf.wine_appimage_recommended_url = server.url("/failed.AppImage")

                with self.assertRaises(SystemExit):
                    utils.set_appimage_symlink(app)

                self.assertEqual(target.read_bytes(), b"sentinel")
                self.assertEqual(link.resolve(), old_target)
                self.assertEqual(old_target.read_bytes(), b"old target")

                app.conf.wine_appimage_recommended_url = server.url("/wine.AppImage")
                utils.set_appimage_symlink(app)

                self.assertEqual(target.read_bytes(), payload)
                self.assertTrue(target.stat().st_mode & stat.S_IXUSR)
                self.assertEqual(link.resolve(), target)
                self.assertEqual(old_target.read_bytes(), b"old target")
                self.assertEqual(self._stages(target), [])

        get_requests = [request for request in server.observed_requests if request[0] == "GET"]
        self.assertEqual(len(get_requests), 2)
        self.assertTrue(all("Range" not in headers for _, _, headers in get_requests))


class TestReuseDownload(unittest.TestCase):
    @staticmethod
    def _real_network(app):
        requests_cache = network.CachedRequests()
        app.conf._network = network.NetworkRequests.__new__(network.NetworkRequests)
        app.conf._network._cache = requests_cache
        return requests_cache

    @patch("ou_dedetai.network.requests.get", side_effect=requests.ReadTimeout)
    @patch("ou_dedetai.network.requests.head", side_effect=requests.ConnectionError)
    def test_failed_probe_and_get_cannot_accept_existing_target(
        self, mock_head, mock_get
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = _write_file(root, "artifact", b"sentinel")
            app = _app(root)
            requests_cache = self._real_network(app)
            with patch.object(requests_cache, "_write") as mock_write:
                with self.assertRaises(SystemExit):
                    network.logos_reuse_download(
                        "https://example.test/artifact", "artifact", str(root), app
                    )

            self.assertEqual(target.read_bytes(), b"sentinel")
            self.assertNotIn(
                "https://example.test/artifact", requests_cache.url_size_and_hash
            )
            mock_write.assert_not_called()
            mock_head.assert_called_once()
            mock_get.assert_called_once()

    def test_cached_file_requires_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cached = _write_file(root, "artifact", b"cached")
            app = _app(root)
            app.conf._network.url_size_and_hash.return_value = (None, None)
            with patch("ou_dedetai.network._download_file", return_value=cached) as mock_download:
                result = network.logos_reuse_download(
                    "https://example.test/artifact", "artifact", str(root), app
                )

            self.assertEqual(result, cached)
            mock_download.assert_called_once_with(
                "https://example.test/artifact", cached, app=app
            )

    def test_matching_cache_is_safely_copied_and_returned(self):
        for metadata in ((6, None), (None, _md5(b"cached")), (6, _md5(b"cached"))):
            with self.subTest(metadata=metadata):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    user_dir = root / "user"
                    target_dir = root / "target"
                    user_dir.mkdir()
                    target_dir.mkdir()
                    _write_file(user_dir, "artifact", b"cached")
                    target = _write_file(target_dir, "artifact", b"sentinel")
                    app = _app(target_dir, user_dir)
                    app.conf._network.url_size_and_hash.return_value = metadata

                    with patch("ou_dedetai.network._download_file") as mock_download:
                        result = network.logos_reuse_download(
                            "https://example.test/artifact", "artifact", str(target_dir), app
                        )

                    self.assertEqual(result, target)
                    self.assertEqual(target.read_bytes(), b"cached")
                    mock_download.assert_not_called()
                    app.conf._network.url_size_and_hash.assert_called_once()

    def test_matching_target_symlink_is_atomically_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            linked_file = _write_file(root, "linked", b"cached")
            target = root / "artifact"
            target.symlink_to(linked_file)
            app = _app(root)
            app.conf._network.url_size_and_hash.return_value = (6, None)

            result = network.logos_reuse_download(
                "https://example.test/artifact", "artifact", str(root), app
            )

            self.assertEqual(result, target)
            self.assertFalse(target.is_symlink())
            self.assertEqual(target.read_bytes(), b"cached")
            self.assertEqual(linked_file.read_bytes(), b"cached")

    def test_mismatched_cache_falls_back_to_fresh_download(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cached = _write_file(root, "artifact", b"stale")
            app = _app(root)
            app.conf._network.url_size_and_hash.return_value = (8, None)
            with patch("ou_dedetai.network._download_file", return_value=cached) as mock_download:
                result = network.logos_reuse_download(
                    "https://example.test/artifact", "artifact", str(root), app
                )

            self.assertEqual(result, cached)
            mock_download.assert_called_once()

    def test_failure_exits_and_does_not_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = _write_file(root, "artifact", b"sentinel")
            app = _app(root)
            app.conf._network.url_size_and_hash.return_value = (None, None)
            with patch(
                "ou_dedetai.network._download_file",
                side_effect=network.DownloadError("failed"),
            ):
                with patch("ou_dedetai.network.shutil.copyfileobj") as mock_copy:
                    with self.assertRaises(SystemExit):
                        network.logos_reuse_download(
                            "https://example.test/artifact", "artifact", str(root), app
                        )

            self.assertEqual(target.read_bytes(), b"sentinel")
            mock_copy.assert_not_called()
            app.exit.assert_called_once()

    def test_metadata_cache_io_failure_requires_fresh_get(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = _write_file(root, "artifact", b"sentinel")
            app = _app(root)
            app.conf._network.url_size_and_hash.side_effect = OSError("cache unavailable")
            with patch("ou_dedetai.network._download_file", return_value=target) as mock_download:
                result = network.logos_reuse_download(
                    "https://example.test/artifact", "artifact", str(root), app
                )

            self.assertEqual(result, target)
            mock_download.assert_called_once_with(
                "https://example.test/artifact", target, app=app
            )

    def test_cached_copy_failure_preserves_existing_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            user_dir = root / "user"
            target_dir = root / "target"
            user_dir.mkdir()
            target_dir.mkdir()
            _write_file(user_dir, "artifact", b"cached")
            target = _write_file(target_dir, "artifact", b"sentinel")
            app = _app(target_dir, user_dir)
            app.conf._network.url_size_and_hash.return_value = (6, None)

            with patch("ou_dedetai.network.shutil.copyfileobj", side_effect=OSError("copy failed")):
                with self.assertRaises(SystemExit):
                    network.logos_reuse_download(
                        "https://example.test/artifact", "artifact", str(target_dir), app
                    )

            self.assertEqual(target.read_bytes(), b"sentinel")

    def test_reuse_can_be_disabled_without_metadata_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "artifact"
            app = _app(root)
            with patch("ou_dedetai.network._download_file", return_value=target):
                result = network.logos_reuse_download(
                    "https://example.test/artifact",
                    "artifact",
                    str(root),
                    app,
                    reuse_existing=False,
                )

            self.assertEqual(result, target)
            app.conf._network.url_size_and_hash.assert_not_called()

    @patch("ou_dedetai.network.requests.get")
    def test_unavailable_md5_exits_and_preserves_existing_target(self, mock_get):
        payload = b"fresh"
        digest = _md5(payload)
        mock_get.return_value = _Response(
            headers={"Content-MD5": digest},
            chunks=[payload],
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = _write_file(root, "artifact", b"sentinel")
            app = _app(root)

            with patch(
                "ou_dedetai.network.hashlib.md5",
                side_effect=ValueError("MD5 unavailable"),
            ):
                with self.assertRaises(SystemExit):
                    network.logos_reuse_download(
                        "https://example.test/artifact",
                        target.name,
                        str(root),
                        app,
                        reuse_existing=False,
                    )

            self.assertEqual(target.read_bytes(), b"sentinel")
            self.assertEqual(list(root.glob(f".{target.name}.*.part")), [])
            app.exit.assert_called_once()


class TestCallerPropagation(unittest.TestCase):
    @patch("ou_dedetai.installer.check_system_compatibility")
    @patch("ou_dedetai.installer.ensure_sys_deps")
    def test_appimage_download_uses_accepted_path(self, mock_deps, mock_compatibility):
        app = _appimage_installer_app()
        app.conf.download_dir = "/cache"
        accepted = Path("/install/bin/wine.AppImage")

        with patch(
            "ou_dedetai.installer.network.logos_reuse_download", return_value=accepted
        ) as mock_download:
            installer.ensure_appimage_download(app)

        self.assertEqual(app.conf.wine_binary, str(accepted))
        mock_download.assert_called_once_with(
            "https://example.test/wine.AppImage",
            "wine.AppImage",
            "/install/bin",
            app=app,
        )

    @patch("ou_dedetai.installer.check_system_compatibility")
    @patch("ou_dedetai.installer.ensure_sys_deps")
    def test_appimage_failure_does_not_assign_binary(self, mock_deps, mock_compatibility):
        app = _appimage_installer_app()

        with patch(
            "ou_dedetai.installer.network.logos_reuse_download", side_effect=SystemExit
        ):
            with self.assertRaises(SystemExit):
                installer.ensure_appimage_download(app)

        self.assertEqual(app.conf.wine_binary, constants.WINE_RECOMMENDED_SIGIL)

    @patch("ou_dedetai.installer.ensure_winetricks_executable")
    def test_installer_is_published_directly_to_final_path(self, mock_ensure):
        app = Mock()
        app.installer_step_count = 0
        app.installer_step = 0
        app.conf.faithlife_product = "Logos"
        app.conf.faithlife_installer_name = "installer.msi"
        app.conf.faithlife_installer_download_url = "https://example.test/installer.msi"
        app.conf.install_dir = "/install"
        accepted = Path("/install/data/installer.msi")

        with patch(
            "ou_dedetai.installer.network.logos_reuse_download", return_value=accepted
        ) as mock_download:
            installer.ensure_product_installer_download(app)

        mock_download.assert_called_once_with(
            "https://example.test/installer.msi",
            "installer.msi",
            "/install/data",
            app=app,
        )

    def test_icu_extract_does_not_run_after_download_failure(self):
        app = _icu_app()
        with patch("ou_dedetai.wine.network.logos_reuse_download", side_effect=SystemExit):
            with patch("ou_dedetai.wine.utils.untar_file") as mock_untar:
                with self.assertRaises(SystemExit):
                    wine.enforce_icu_data_files(app)
        mock_untar.assert_not_called()

    def test_icu_extracts_only_the_accepted_path(self):
        app = _icu_app()
        accepted = Path("/accepted/icu-1.tar.gz")
        with patch(
            "ou_dedetai.wine.network.logos_reuse_download", return_value=accepted
        ):
            with patch("ou_dedetai.wine.utils.untar_file") as mock_untar:
                with patch("ou_dedetai.wine.os.path.exists", return_value=True):
                    with patch("ou_dedetai.wine.shutil.copytree"):
                        wine.enforce_icu_data_files(app)

        mock_untar.assert_called_once_with(accepted, "/wine/drive_c")

    def test_winetricks_extract_and_chmod_do_not_run_after_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            app = _winetricks_app(directory)
            with patch("ou_dedetai.system.network.logos_reuse_download", side_effect=SystemExit):
                with patch("ou_dedetai.system.zipfile.ZipFile") as mock_zip:
                    with patch("ou_dedetai.system.os.chmod") as mock_chmod:
                        with self.assertRaises(SystemExit):
                            system.ensure_winetricks(app)
            mock_zip.assert_not_called()
            mock_chmod.assert_not_called()

    def test_winetricks_opens_only_the_accepted_path(self):
        with tempfile.TemporaryDirectory() as directory:
            app = _winetricks_app(directory)
            accepted = Path(directory) / "accepted.zip"
            zip_context = Mock()
            zip_context.__enter__ = Mock(return_value=Mock(infolist=Mock(return_value=[])))
            zip_context.__exit__ = Mock(return_value=False)
            with patch(
                "ou_dedetai.system.network.logos_reuse_download", return_value=accepted
            ):
                with patch(
                    "ou_dedetai.system.zipfile.ZipFile", return_value=zip_context
                ) as mock_zip:
                    with patch("ou_dedetai.system.os.chmod"):
                        system.ensure_winetricks(app)

            mock_zip.assert_called_once_with(accepted)

    def test_self_update_does_nothing_after_download_failure(self):
        app = _self_update_app()
        with patch("ou_dedetai.network.logos_reuse_download", side_effect=SystemExit):
            with patch("ou_dedetai.network.utils.get_lli_release_version") as mock_version:
                with patch("ou_dedetai.network.shutil.copy") as mock_copy:
                    with patch("ou_dedetai.network.shutil.move") as mock_move:
                        with patch("ou_dedetai.network.os.chmod") as mock_chmod:
                            with patch("ou_dedetai.network.utils.restart_lli") as mock_restart:
                                with self.assertRaises(SystemExit):
                                    network.update_lli_binary(app)
        mock_version.assert_not_called()
        mock_copy.assert_not_called()
        mock_move.assert_not_called()
        mock_chmod.assert_not_called()
        mock_restart.assert_not_called()

    def test_self_update_checks_version_only_after_fresh_acceptance(self):
        app = _self_update_app()
        accepted = Path("/cache/oudedetai")
        with patch("ou_dedetai.network.logos_reuse_download", return_value=accepted) as mock_download:
            with patch("ou_dedetai.network.utils.get_lli_release_version", return_value="9.9.9") as mock_version:
                with patch("ou_dedetai.network.shutil.copy") as mock_copy:
                    with patch("ou_dedetai.network.shutil.move"):
                        with patch("ou_dedetai.network.os.stat", return_value=Mock(st_mode=0o600)):
                            with patch("ou_dedetai.network.os.chmod"):
                                with patch("ou_dedetai.network.utils.restart_lli"):
                                    network.update_lli_binary(app)

        mock_download.assert_called_once_with(
            "https://example.test/oudedetai",
            constants.BINARY_NAME,
            "/cache",
            app=app,
            reuse_existing=False,
        )
        mock_version.assert_called_once_with(accepted)
        mock_copy.assert_called_once_with(accepted, Path("/cache/oudedetai.tmp"))

    def test_existing_recommended_appimage_still_uses_reuse_helper(self):
        app = Mock()
        app.conf.wine_appimage_recommended_file_name = "wine.AppImage"
        app.conf.wine_appimage_recommended_url = "https://example.test/wine.AppImage"
        app.conf.installer_binary_dir = "/install/bin"
        accepted = Path("/install/bin/wine.AppImage")
        with patch("ou_dedetai.network.logos_reuse_download", return_value=accepted) as mock_reuse:
            self.assertEqual(network.download_recommended_appimage(app), accepted)
        mock_reuse.assert_called_once()

    def test_appimage_symlink_copy_does_not_rediscover_stale_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "cache"
            target_dir = root / "bin"
            source_dir.mkdir()
            target_dir.mkdir()
            accepted = _write_file(source_dir, "wine.AppImage", b"accepted")
            app = Mock()
            app.conf.installer_binary_dir = str(target_dir)
            app.conf.wine_binary_code = "Recommended"
            app.conf.wine_appimage_path = accepted
            app.conf.wine_appimage_link_file_name = "selected_wine.AppImage"
            app.conf.wine_appimage_recommended_file_name = accepted.name

            with patch("ou_dedetai.installer.utils.get_downloaded_file_path") as mock_find:
                installer.create_wine_appimage_symlinks(app)

            mock_find.assert_not_called()
            self.assertEqual((target_dir / accepted.name).read_bytes(), b"accepted")

    def test_set_appimage_symlink_uses_download_return_value(self):
        with tempfile.TemporaryDirectory() as directory:
            target_dir = Path(directory)
            accepted = _write_file(target_dir, "wine.AppImage", b"accepted")
            accepted.chmod(0o600)
            app = Mock()
            app.conf.wine_binary_code = "Recommended"
            app.conf.wine_appimage_path = Path("wine.AppImage")
            app.conf.wine_appimage_recommended_file_name = "wine.AppImage"
            app.conf.installer_binary_dir = str(target_dir)
            app.conf.wine_appimage_link_file_name = "selected_wine.AppImage"

            def assert_executable_before_link(source: Path, _destination: Path):
                self.assertTrue(source.stat().st_mode & stat.S_IXUSR)

            with patch("ou_dedetai.utils.network.download_recommended_appimage", return_value=accepted):
                with patch("ou_dedetai.utils.delete_symlink"):
                    with patch(
                        "ou_dedetai.utils.os.symlink",
                        side_effect=assert_executable_before_link,
                    ) as mock_symlink:
                        utils.set_appimage_symlink(app)

            mock_symlink.assert_called_once_with(accepted, target_dir / "selected_wine.AppImage")
            self.assertTrue(accepted.stat().st_mode & stat.S_IXUSR)


if __name__ == "__main__":
    unittest.main()
