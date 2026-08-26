import hashlib
import inspect
import os
import stat
import tempfile
import unittest
from base64 import b64encode
from pathlib import Path
from unittest import mock

import requests
from requests.exceptions import MissingSchema

import ou_dedetai.network as network


URL = 'https://downloads.example.test/artifact'
FILENAME = 'artifact.bin'


def _response(status=200, headers=None, chunks=None):
    response = mock.MagicMock()
    response.status_code = status
    response.headers = headers or {}
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    response.iter_content.return_value = iter(chunks or [])
    return response


def _md5(data: bytes) -> str:
    return b64encode(hashlib.md5(data).digest()).decode('ascii')


# Keep these unit tests deterministic; network behavior is mocked below.
class TestProperties(unittest.TestCase):
    def setUp(self):
        self.empty_json_data = '{\n}\n'

    def test_fileprops_get_size(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / 'file.json'
            file_path.write_text(self.empty_json_data)
            file_properties = network.FileProps(file_path)
            self.assertEqual(file_properties.size, 4)

    def test_fileprops_get_md5(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / 'file.json'
            file_path.write_text(self.empty_json_data)
            file_properties = network.FileProps(file_path)
            self.assertEqual(file_properties._get_md5(), 'W3aw7vmviiMAZz4FU/YJ+Q==')

    @mock.patch('ou_dedetai.network.requests.head')
    def test_urlprops_get_headers(self, head):
        head.return_value = _response(headers={'Content-Length': '4'})
        self.assertEqual(network.UrlProps(URL).headers['Content-Length'], '4')

    @mock.patch('ou_dedetai.network.requests.head')
    def test_urlprops_get_headers_none(self, head):
        head.side_effect = MissingSchema()
        with self.assertRaises(MissingSchema):
            network.UrlProps('').headers

    @mock.patch('ou_dedetai.network.requests.head')
    def test_urlprops_get_size(self, head):
        head.return_value = _response(headers={'Content-Length': '4'})
        self.assertEqual(network.UrlProps(URL).size, 4)

    @mock.patch('ou_dedetai.network.requests.head')
    def test_urlprops_get_md5(self, head):
        head.return_value = _response(headers={'Content-Length': '4'})
        self.assertIsNone(network.UrlProps(URL).md5)


class TestLogosReuseDownload(unittest.TestCase):
    def _app(self, root: Path):
        app = mock.Mock()
        app.conf.user_download_dir = str(root / 'user-downloads')
        app.conf.download_dir = str(root / 'downloads')
        Path(app.conf.user_download_dir).mkdir()
        Path(app.conf.download_dir).mkdir()
        app.exit.side_effect = SystemExit(1)
        return app

    def _owned_temporary_files(self, root: Path):
        return [
            path
            for path in root.rglob(f'.{FILENAME}.*')
            if path.suffix in {'.part', '.rollback', '.mode'}
        ]

    @mock.patch('ou_dedetai.network.requests.get')
    @mock.patch('ou_dedetai.network.requests.head')
    def test_non_200_responses_preserve_existing_files_without_reading_body(self, head, get):
        for status_code in (206, 404, 500):
            with self.subTest(status_code=status_code), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                app = self._app(root)
                target_dir = root / 'target'
                target_dir.mkdir()
                download_path = Path(app.conf.download_dir) / FILENAME
                target_path = target_dir / FILENAME
                download_path.write_bytes(b'old-cache')
                target_path.write_bytes(b'old-target')
                head.return_value = _response(status=405)
                get_response = _response(status=status_code, chunks=[b'error body'])
                get.return_value = get_response

                with self.assertRaises(SystemExit):
                    network.logos_reuse_download(URL, FILENAME, str(target_dir), app)

                self.assertEqual(download_path.read_bytes(), b'old-cache')
                self.assertEqual(target_path.read_bytes(), b'old-target')
                get_response.iter_content.assert_not_called()
                self.assertEqual(self._owned_temporary_files(root), [])

    @mock.patch('ou_dedetai.network.requests.get')
    @mock.patch('ou_dedetai.network.requests.head')
    def test_interrupted_stream_preserves_files_and_cleans_staging(self, head, get):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = self._app(root)
            target_dir = root / 'target'
            target_dir.mkdir()
            download_path = Path(app.conf.download_dir) / FILENAME
            target_path = target_dir / FILENAME
            download_path.write_bytes(b'old-cache')
            target_path.write_bytes(b'old-target')
            head.return_value = _response(status=405)
            get_response = _response(headers={})

            def interrupted(_chunk_size):
                yield b'partial'
                raise requests.exceptions.ConnectionError('connection dropped')

            get_response.iter_content.side_effect = interrupted
            get.return_value = get_response

            with self.assertRaises(SystemExit):
                network.logos_reuse_download(URL, FILENAME, str(target_dir), app)

            self.assertEqual(download_path.read_bytes(), b'old-cache')
            self.assertEqual(target_path.read_bytes(), b'old-target')
            self.assertEqual(self._owned_temporary_files(root), [])

    def test_unusable_head_always_forces_a_fresh_get(self):
        head_cases = [
            _response(status=405),
            requests.exceptions.ConnectionError('offline'),
            requests.exceptions.Timeout('timed out'),
            _response(status=200, headers={}),
            _response(status=200, headers={'Content-Length': 'not-a-number', 'Content-MD5': 'invalid'}),
        ]
        for head_result in head_cases:
            with self.subTest(head_result=type(head_result).__name__), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                app = self._app(root)
                download_path = Path(app.conf.download_dir) / FILENAME
                download_path.write_bytes(b'stale')
                get_response = _response(status=200, headers={}, chunks=[b'fresh'])
                with (
                    mock.patch('ou_dedetai.network.requests.head') as head,
                    mock.patch('ou_dedetai.network.requests.get', return_value=get_response) as get,
                ):
                    if isinstance(head_result, Exception):
                        head.side_effect = head_result
                    else:
                        head.return_value = head_result
                    network.logos_reuse_download(URL, FILENAME, app.conf.download_dir, app)

                get.assert_called_once()
                self.assertEqual(download_path.read_bytes(), b'fresh')

    @mock.patch('ou_dedetai.network.requests.get')
    @mock.patch('ou_dedetai.network.requests.head')
    def test_length_matching_cache_is_reused(self, head, get):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = self._app(root)
            target_dir = root / 'target'
            target_dir.mkdir()
            content = b'valid cache'
            (Path(app.conf.user_download_dir) / FILENAME).write_bytes(content)
            head.return_value = _response(headers={'Content-Length': str(len(content))})

            result = network.logos_reuse_download(URL, FILENAME, str(target_dir), app)

            self.assertIsNone(result)
            self.assertEqual((target_dir / FILENAME).read_bytes(), content)
            get.assert_not_called()

    def test_md5_cache_reuse_supports_content_md5_and_single_part_s3_etag(self):
        content = b'valid cache'
        digest_hex = hashlib.md5(content).hexdigest()
        validators = [
            {'Content-MD5': _md5(content)},
            {'Server': 'AmazonS3', 'ETag': f'"{digest_hex}"'},
        ]
        for headers in validators:
            with self.subTest(headers=headers), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                app = self._app(root)
                target_dir = root / 'target'
                target_dir.mkdir()
                (Path(app.conf.download_dir) / FILENAME).write_bytes(content)
                with (
                    mock.patch('ou_dedetai.network.requests.head', return_value=_response(headers=headers)),
                    mock.patch('ou_dedetai.network.requests.get') as get,
                ):
                    network.logos_reuse_download(URL, FILENAME, str(target_dir), app)
                get.assert_not_called()
                self.assertEqual((target_dir / FILENAME).read_bytes(), content)

    @mock.patch('ou_dedetai.network.requests.get')
    @mock.patch('ou_dedetai.network.requests.head')
    def test_every_available_validator_must_match(self, head, get):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = self._app(root)
            download_path = Path(app.conf.download_dir) / FILENAME
            download_path.write_bytes(b'bad!')
            fresh = b'good'
            headers = {'Content-Length': str(len(fresh)), 'Content-MD5': _md5(fresh)}
            head.return_value = _response(headers=headers)
            get.return_value = _response(headers=headers, chunks=[fresh])

            network.logos_reuse_download(URL, FILENAME, app.conf.download_dir, app)

            get.assert_called_once()
            self.assertEqual(download_path.read_bytes(), fresh)

    @mock.patch('ou_dedetai.network.requests.get')
    @mock.patch('ou_dedetai.network.requests.head')
    def test_partial_cache_forces_full_get(self, head, get):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = self._app(root)
            download_path = Path(app.conf.download_dir) / FILENAME
            download_path.write_bytes(b'part')
            fresh = b'complete'
            headers = {'Content-Length': str(len(fresh))}
            head.return_value = _response(headers=headers)
            get.return_value = _response(headers=headers, chunks=[fresh])

            network.logos_reuse_download(URL, FILENAME, app.conf.download_dir, app)

            self.assertEqual(download_path.read_bytes(), fresh)
            get.assert_called_once()

    @mock.patch('ou_dedetai.network.requests.get')
    @mock.patch('ou_dedetai.network.requests.head')
    def test_target_directory_candidate_is_reused(self, head, get):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = self._app(root)
            target_dir = root / 'installer-bin'
            target_dir.mkdir()
            content = b'existing appimage'
            target_path = target_dir / FILENAME
            target_path.write_bytes(content)
            head.return_value = _response(headers={'Content-Length': str(len(content))})

            network.logos_reuse_download(URL, FILENAME, str(target_dir), app)

            self.assertEqual(target_path.read_bytes(), content)
            self.assertFalse((Path(app.conf.download_dir) / FILENAME).exists())
            get.assert_not_called()

    @mock.patch('ou_dedetai.network.requests.get')
    @mock.patch('ou_dedetai.network.requests.head')
    def test_retry_restarts_from_byte_zero_without_range(self, head, get):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = self._app(root)
            download_path = Path(app.conf.download_dir) / FILENAME
            download_path.write_bytes(b'old')
            head.side_effect = [_response(status=405), _response(status=405)]
            interrupted_response = _response(headers={})

            def interrupted(_chunk_size):
                yield b'partial'
                raise requests.exceptions.ConnectionError('connection dropped')

            interrupted_response.iter_content.side_effect = interrupted
            successful_response = _response(headers={}, chunks=[b'complete'])
            get.side_effect = [interrupted_response, successful_response]

            with self.assertRaises(SystemExit):
                network.logos_reuse_download(URL, FILENAME, app.conf.download_dir, app)
            app.exit.reset_mock(side_effect=True)
            app.exit.side_effect = SystemExit(1)
            network.logos_reuse_download(URL, FILENAME, app.conf.download_dir, app)

            self.assertEqual(download_path.read_bytes(), b'complete')
            for call in get.call_args_list:
                self.assertEqual(call.kwargs['headers'], {'Accept-Encoding': 'identity'})
                self.assertNotIn('Range', call.kwargs['headers'])

    @mock.patch('ou_dedetai.network.os.replace', wraps=os.replace)
    @mock.patch('ou_dedetai.network.requests.get')
    @mock.patch('ou_dedetai.network.requests.head')
    def test_validated_get_is_atomically_published(self, head, get, replace):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = self._app(root)
            content = b'validated download'
            headers = {'Content-Length': str(len(content)), 'Content-MD5': _md5(content)}
            head.return_value = _response(status=405)
            get.return_value = _response(headers=headers, chunks=[content])

            network.logos_reuse_download(URL, FILENAME, app.conf.download_dir, app)

            download_path = Path(app.conf.download_dir) / FILENAME
            self.assertEqual(download_path.read_bytes(), content)
            self.assertTrue(any(Path(call.args[1]) == download_path for call in replace.call_args_list))

    @mock.patch('ou_dedetai.network.requests.get')
    @mock.patch('ou_dedetai.network.requests.head')
    def test_completed_metadata_free_get_is_accepted(self, head, get):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = self._app(root)
            head.return_value = _response(status=200, headers={})
            get.return_value = _response(status=200, headers={}, chunks=[b'transport complete'])

            result = network.logos_reuse_download(URL, FILENAME, app.conf.download_dir, app)

            self.assertIsNone(result)
            self.assertEqual((Path(app.conf.download_dir) / FILENAME).read_bytes(), b'transport complete')

    @mock.patch('ou_dedetai.network.shutil.copyfileobj', side_effect=OSError('copy failed'))
    @mock.patch('ou_dedetai.network.requests.get')
    @mock.patch('ou_dedetai.network.requests.head')
    def test_staged_copy_failure_preserves_existing_files(self, head, get, _copyfileobj):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = self._app(root)
            target_dir = root / 'target'
            target_dir.mkdir()
            download_path = Path(app.conf.download_dir) / FILENAME
            target_path = target_dir / FILENAME
            download_path.write_bytes(b'old-cache')
            target_path.write_bytes(b'old-target')
            head.return_value = _response(status=405)
            get.return_value = _response(headers={}, chunks=[b'new'])

            with self.assertRaises(SystemExit):
                network.logos_reuse_download(URL, FILENAME, str(target_dir), app)

            self.assertEqual(download_path.read_bytes(), b'old-cache')
            self.assertEqual(target_path.read_bytes(), b'old-target')
            self.assertEqual(self._owned_temporary_files(root), [])

    @mock.patch('ou_dedetai.network.shutil.copy2', side_effect=OSError('rollback copy failed'))
    @mock.patch('ou_dedetai.network.requests.get')
    @mock.patch('ou_dedetai.network.requests.head')
    def test_rollback_copy_failure_preserves_existing_files(self, head, get, _copy2):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = self._app(root)
            target_dir = root / 'target'
            target_dir.mkdir()
            download_path = Path(app.conf.download_dir) / FILENAME
            target_path = target_dir / FILENAME
            download_path.write_bytes(b'old-cache')
            target_path.write_bytes(b'old-target')
            head.return_value = _response(status=405)
            get.return_value = _response(headers={}, chunks=[b'new'])

            with self.assertRaises(SystemExit):
                network.logos_reuse_download(URL, FILENAME, str(target_dir), app)

            self.assertEqual(download_path.read_bytes(), b'old-cache')
            self.assertEqual(target_path.read_bytes(), b'old-target')
            self.assertEqual(self._owned_temporary_files(root), [])

    @mock.patch('ou_dedetai.network.requests.get')
    @mock.patch('ou_dedetai.network.requests.head')
    def test_cache_publication_failure_does_not_replace_the_existing_cache(self, head, get):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = self._app(root)
            target_dir = root / 'target'
            target_dir.mkdir()
            download_path = Path(app.conf.download_dir) / FILENAME
            target_path = target_dir / FILENAME
            download_path.write_bytes(b'old-cache')
            target_path.write_bytes(b'old-target')
            hard_link = root / 'cache-link'
            os.link(download_path, hard_link)
            head.return_value = _response(status=405)
            get.return_value = _response(headers={}, chunks=[b'new'])
            real_replace = os.replace

            def fail_cache_publication(source, destination):
                if Path(destination) == download_path and Path(source).suffix == '.part':
                    raise OSError('publication failed')
                return real_replace(source, destination)

            with mock.patch('ou_dedetai.network.os.replace', side_effect=fail_cache_publication):
                with self.assertRaises(SystemExit):
                    network.logos_reuse_download(URL, FILENAME, str(target_dir), app)

            self.assertEqual(download_path.read_bytes(), b'old-cache')
            self.assertEqual(download_path.stat().st_ino, hard_link.stat().st_ino)
            self.assertEqual(target_path.read_bytes(), b'old-target')
            self.assertEqual(self._owned_temporary_files(root), [])

    @mock.patch('ou_dedetai.network.requests.get')
    @mock.patch('ou_dedetai.network.requests.head')
    def test_target_publication_failure_rolls_back_cache_and_target(self, head, get):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = self._app(root)
            target_dir = root / 'target'
            target_dir.mkdir()
            download_path = Path(app.conf.download_dir) / FILENAME
            target_path = target_dir / FILENAME
            download_path.write_bytes(b'old-cache')
            target_path.write_bytes(b'old-target')
            head.return_value = _response(status=405)
            get.return_value = _response(headers={}, chunks=[b'new'])
            real_replace = os.replace

            def fail_target_publication(source, destination):
                if Path(destination) == target_path and Path(source).suffix == '.part':
                    raise OSError('publication failed')
                return real_replace(source, destination)

            with mock.patch('ou_dedetai.network.os.replace', side_effect=fail_target_publication):
                with self.assertRaises(SystemExit):
                    network.logos_reuse_download(URL, FILENAME, str(target_dir), app)

            self.assertEqual(download_path.read_bytes(), b'old-cache')
            self.assertEqual(target_path.read_bytes(), b'old-target')
            self.assertEqual(self._owned_temporary_files(root), [])

    @mock.patch('ou_dedetai.network.requests.get')
    @mock.patch('ou_dedetai.network.requests.head')
    def test_distinct_paths_and_existing_permissions_are_preserved(self, head, get):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = self._app(root)
            target_dir = root / 'installer-bin'
            target_dir.mkdir()
            download_path = Path(app.conf.download_dir) / FILENAME
            target_path = target_dir / FILENAME
            download_path.write_bytes(b'old-cache')
            target_path.write_bytes(b'old-target')
            download_path.chmod(0o600)
            target_path.chmod(0o755)
            content = b'new executable'
            headers = {'Content-Length': str(len(content))}
            head.return_value = _response(status=405)
            get.return_value = _response(headers=headers, chunks=[content])

            network.logos_reuse_download(URL, FILENAME, str(target_dir), app)

            self.assertEqual(download_path.read_bytes(), content)
            self.assertEqual(target_path.read_bytes(), content)
            self.assertEqual(stat.S_IMODE(download_path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(target_path.stat().st_mode), 0o755)

    @mock.patch('ou_dedetai.network.requests.get')
    @mock.patch('ou_dedetai.network.requests.head')
    def test_new_destinations_respect_the_process_umask(self, head, get):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = self._app(root)
            target_dir = root / 'target'
            target_dir.mkdir()
            head.return_value = _response(status=405)
            get.return_value = _response(headers={}, chunks=[b'private'])

            previous_umask = os.umask(0o077)
            try:
                network.logos_reuse_download(URL, FILENAME, str(target_dir), app)
            finally:
                os.umask(previous_umask)

            download_path = Path(app.conf.download_dir) / FILENAME
            target_path = target_dir / FILENAME
            self.assertEqual(stat.S_IMODE(download_path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(target_path.stat().st_mode), 0o600)
            self.assertEqual(self._owned_temporary_files(root), [])

    @mock.patch('ou_dedetai.network.requests.get')
    @mock.patch('ou_dedetai.network.requests.head')
    def test_request_contract_uses_timeouts_redirects_streaming_and_no_range(self, head, get):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = self._app(root)
            head.return_value = _response(status=405)
            get.return_value = _response(headers={}, chunks=[b'complete'])

            network.logos_reuse_download(URL, FILENAME, app.conf.download_dir, app)

            request_headers = {'Accept-Encoding': 'identity'}
            head.assert_called_once_with(
                URL,
                allow_redirects=True,
                headers=request_headers,
                timeout=(10, 30),
            )
            get.assert_called_once_with(
                URL,
                stream=True,
                allow_redirects=True,
                headers=request_headers,
                timeout=(10, 30),
            )
            self.assertNotIn('Range', get.call_args.kwargs['headers'])

    def test_signature_and_implicit_none_contract_are_unchanged(self):
        parameters = inspect.signature(network.logos_reuse_download).parameters
        self.assertEqual(
            list(parameters),
            ['sourceurl', 'file', 'targetdir', 'app', 'status_messages'],
        )
        self.assertEqual(parameters['status_messages'].default, True)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = self._app(root)
            target_path = Path(app.conf.download_dir) / FILENAME
            target_path.write_bytes(b'valid')
            with (
                mock.patch(
                    'ou_dedetai.network.requests.head',
                    return_value=_response(headers={'Content-Length': '5'}),
                ),
                mock.patch('ou_dedetai.network.requests.get') as get,
            ):
                result = network.logos_reuse_download(URL, FILENAME, app.conf.download_dir, app)
            self.assertIsNone(result)
            get.assert_not_called()


class TestDownloadCallers(unittest.TestCase):
    @mock.patch('ou_dedetai.network.logos_reuse_download')
    def test_recommended_appimage_is_checked_even_when_destination_exists(self, reuse_download):
        with tempfile.TemporaryDirectory() as directory:
            installer_dir = Path(directory)
            app = mock.Mock()
            app.conf.wine_appimage_recommended_file_name = 'recommended.AppImage'
            app.conf.wine_appimage_recommended_url = URL
            app.conf.installer_binary_dir = str(installer_dir)
            (installer_dir / 'recommended.AppImage').write_bytes(b'existing')

            result = network.download_recommended_appimage(app)

            self.assertIsNone(result)
            reuse_download.assert_called_once_with(
                URL,
                'recommended.AppImage',
                str(installer_dir),
                app=app,
            )

    def _updater_app(self, download_dir: Path):
        app = mock.Mock()
        app.conf.download_dir = str(download_dir)
        app.conf.app_latest_version = '1.2.3'
        app.conf.app_latest_version_url = URL
        app.exit.side_effect = SystemExit(1)
        return app

    def test_self_update_validates_before_version_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            running_binary = root / 'running'
            running_binary.write_bytes(b'running')
            app = self._updater_app(root)
            events = []
            with (
                mock.patch('ou_dedetai.network.sys.argv', [str(running_binary)]),
                mock.patch(
                    'ou_dedetai.network.logos_reuse_download',
                    side_effect=lambda *args, **kwargs: events.append('download'),
                ),
                mock.patch(
                    'ou_dedetai.network.utils.get_lli_release_version',
                    side_effect=lambda _path: events.append('version') or '1.2.3',
                ),
                mock.patch('ou_dedetai.network.shutil.copy'),
                mock.patch('ou_dedetai.network.shutil.move'),
                mock.patch('ou_dedetai.network.os.chmod'),
                mock.patch('ou_dedetai.network.utils.restart_lli'),
            ):
                network.update_lli_binary(app)

            self.assertEqual(events, ['download', 'version'])

    def test_failed_self_update_download_stops_all_follow_on_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = self._updater_app(root)
            with (
                mock.patch('ou_dedetai.network.logos_reuse_download', side_effect=SystemExit(1)),
                mock.patch('ou_dedetai.network.utils.get_lli_release_version') as get_version,
                mock.patch('ou_dedetai.network.shutil.copy') as copy,
                mock.patch('ou_dedetai.network.shutil.move') as move,
                mock.patch('ou_dedetai.network.os.chmod') as chmod,
                mock.patch('ou_dedetai.network.utils.restart_lli') as restart,
            ):
                with self.assertRaises(SystemExit):
                    network.update_lli_binary(app)

            get_version.assert_not_called()
            copy.assert_not_called()
            move.assert_not_called()
            chmod.assert_not_called()
            restart.assert_not_called()

    def test_version_mismatch_removes_only_cached_updater_and_exits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            running_binary = root / 'running'
            running_binary.write_bytes(b'running')
            cached_updater = root / network.constants.BINARY_NAME
            cached_updater.write_bytes(b'wrong version')
            unrelated = root / 'keep-me'
            unrelated.write_bytes(b'keep')
            app = self._updater_app(root)
            with (
                mock.patch('ou_dedetai.network.sys.argv', [str(running_binary)]),
                mock.patch('ou_dedetai.network.logos_reuse_download'),
                mock.patch('ou_dedetai.network.utils.get_lli_release_version', return_value='0.0.1'),
                mock.patch('ou_dedetai.network.shutil.copy') as copy,
                mock.patch('ou_dedetai.network.shutil.move') as move,
                mock.patch('ou_dedetai.network.os.chmod') as chmod,
                mock.patch('ou_dedetai.network.utils.restart_lli') as restart,
            ):
                with self.assertRaises(SystemExit):
                    network.update_lli_binary(app)

            self.assertFalse(cached_updater.exists())
            self.assertTrue(running_binary.exists())
            self.assertTrue(unrelated.exists())
            copy.assert_not_called()
            move.assert_not_called()
            chmod.assert_not_called()
            restart.assert_not_called()

    def test_version_probe_failure_removes_cached_updater_and_exits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cached_updater = root / network.constants.BINARY_NAME
            cached_updater.write_bytes(b'cannot execute')
            app = self._updater_app(root)
            with (
                mock.patch('ou_dedetai.network.logos_reuse_download'),
                mock.patch(
                    'ou_dedetai.network.utils.get_lli_release_version',
                    side_effect=OSError('not executable'),
                ),
                mock.patch('ou_dedetai.network.shutil.copy') as copy,
                mock.patch('ou_dedetai.network.shutil.move') as move,
                mock.patch('ou_dedetai.network.os.chmod') as chmod,
                mock.patch('ou_dedetai.network.utils.restart_lli') as restart,
            ):
                with self.assertRaises(SystemExit):
                    network.update_lli_binary(app)

            self.assertFalse(cached_updater.exists())
            app.exit.assert_called_once()
            copy.assert_not_called()
            move.assert_not_called()
            chmod.assert_not_called()
            restart.assert_not_called()


if __name__ == '__main__':
    unittest.main()
