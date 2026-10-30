import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, PropertyMock, patch

from ou_dedetai import constants, runtime, utils, wine
from ou_dedetai.app import UserExitedFromAsk
from ou_dedetai.config import Config, EphemeralConfiguration, LegacyConfiguration, PersistentConfiguration
from ou_dedetai.logos import State


class TestRuntimeSelection(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.install = self.root / 'install'
        self.install.mkdir()
        self.config_path = self.root / 'config.json'
        self.app = Mock()
        self.app.choose_runtime.side_effect = lambda question, options, current: self.app.ask(question, options)
        self.app.choose_file.side_effect = lambda question, **kwargs: self.app.ask(
            question, [constants.PROMPT_OPTION_FILE])
        self.app._wine_selection_lock = threading.Lock()
        self.app.logos.existing_processes = {}
        self.app.logos.logos_state = State.STOPPED
        self.app.logos.indexing_state = State.STOPPED
        self.conf = object.__new__(Config)
        self.app.conf = self.conf
        self.conf.app = self.app
        self.conf._raw = PersistentConfiguration(install_dir=str(self.install), faithlife_product='Logos',
                                                faithlife_product_version='10', wine_binary='/old/wine')
        self.conf._overrides = EphemeralConfiguration.from_legacy(
            LegacyConfiguration(CONFIG_FILE=str(self.config_path)))
        self.conf._installed_faithlife_product_release = '40.0.0.0'
        self.conf._wine64_path = '/old/wine64'
        self.managed = Path(self.conf.installer_binary_dir)
        self.managed.mkdir(parents=True)
        recommended = patch.object(Config, 'wine_appimage_recommended_file_name',
                                   new_callable=PropertyMock, return_value='recommended.AppImage')
        recommended.start()
        self.addCleanup(recommended.stop)
        url = patch.object(Config, 'wine_appimage_recommended_url', new_callable=PropertyMock,
                           return_value='https://example.invalid/recommended.AppImage')
        url.start()
        self.addCleanup(url.stop)
        channel = patch('ou_dedetai.installer.default_wine_channel', return_value=constants.WINE_RECOMMENDED_SIGIL)
        channel.start()
        self.addCleanup(channel.stop)

    def executable(self, path, version='wine-10.0'):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'#!/bin/sh\nprintf "%s\\n" "{version}"\n')
        path.chmod(0o755)
        return path

    def image(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'\x7fELF' + bytes(4) + b'AI\x02' + bytes(20))
        path.chmod(0o644)
        return path

    def activate_image(self, path):
        with patch.object(runtime, '_check_version'):
            runtime.activate_runtime(self.app, path)

    def test_downloaded_image_is_executable_selected_and_persisted(self):
        source = self.image(self.root / 'Downloads/wine.AppImage')
        self.activate_image(source)
        installed = self.managed / source.name
        self.assertTrue(os.access(installed, os.X_OK))
        self.assertFalse(os.access(source, os.X_OK))
        self.assertEqual(self.conf.wine_binary, str(installed))
        self.assertEqual(Path(self.conf.wine64_binary).resolve(), installed)
        self.assertEqual(Path(self.conf.wineserver_binary).resolve(), installed)
        data = json.loads(self.config_path.read_text())
        self.assertEqual(self.install / data['wine_binary'], installed)
        self.conf._raw = PersistentConfiguration.load_from_path(str(self.config_path))
        self.assertEqual(self.conf.wine_binary, str(installed))
        self.assertEqual(self.conf.wineserver_binary, str(self.managed / 'wineserver'))

    def test_existing_image_switch_updates_all_links(self):
        first = self.image(self.managed / 'first.AppImage')
        second = self.image(self.managed / 'second.AppImage')
        self.activate_image(first)
        self.activate_image(second)
        for name in ('wine', 'wine64', 'wineserver', 'winetricks', self.conf.wine_appimage_link_file_name):
            self.assertEqual((self.managed / name).resolve(), second)
        self.assertTrue(first.exists())

    def test_system_wine_without_wine64(self):
        binary = self.executable(self.root / 'system/bin/wine')
        server = self.executable(binary.parent / 'wineserver')
        runtime.activate_runtime(self.app, binary)
        self.assertEqual(self.conf.wine64_binary, str(binary))
        self.assertEqual(self.conf.wineserver_binary, str(server))
        self.assertEqual(wine.get_wine_env(self.app)['WINE'], str(binary))
        self.assertEqual(wine.get_wine_env(self.app)['WINESERVER'], str(server))

    def test_custom_build_server_layout(self):
        binary = self.executable(self.root / 'build/loader/wine')
        server = self.executable(self.root / 'build/server/wineserver')
        runtime.activate_runtime(self.app, binary)
        self.assertEqual(self.conf.wineserver_binary, str(server))

    def test_explicit_server_and_path_with_spaces(self):
        binary = self.executable(self.root / 'my build/wine')
        server = self.executable(self.root / 'separate server/wineserver')
        runtime.activate_runtime(self.app, binary, server)
        self.assertEqual(self.conf.wineserver_binary, str(server))

    def test_external_prefix_similar_to_install_is_not_relativised(self):
        binary = self.executable(self.root / 'install-custom/wine')
        self.executable(binary.parent / 'wineserver')
        runtime.activate_runtime(self.app, binary)
        self.assertEqual(self.conf._raw.wine_binary, str(binary))

    def test_image_to_local_and_back(self):
        image = self.image(self.managed / 'wine.AppImage')
        self.activate_image(image)
        binary = self.executable(self.root / 'local/wine')
        server = self.executable(binary.parent / 'wineserver')
        runtime.activate_runtime(self.app, binary)
        self.assertEqual(self.conf.wine_binary, str(binary))
        self.assertEqual(self.conf.wineserver_binary, str(server))
        self.activate_image(image)
        self.assertEqual(self.conf.wine_binary, str(image))

    def test_validation_failure_preserves_previous_selection(self):
        source = self.image(self.root / 'Downloads/new.AppImage')
        with patch.object(runtime, '_check_version', side_effect=ValueError('bad runtime')):
            with self.assertRaises(ValueError):
                runtime.activate_runtime(self.app, source)
        self.assertEqual(self.conf.wine_binary, '/old/wine')
        self.assertFalse((self.managed / source.name).exists())

    def test_save_failure_restores_links_and_selection(self):
        old = self.image(self.managed / 'old.AppImage')
        self.activate_image(old)
        before = self.config_path.read_bytes()
        new = self.image(self.root / 'Downloads/new.AppImage')
        with patch.object(self.conf, 'select_wine_runtime', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.activate_image(new)
        self.assertEqual(self.conf.wine_binary, str(old))
        self.assertEqual((self.managed / 'wine').resolve(), old)
        self.assertEqual(self.config_path.read_bytes(), before)
        self.assertFalse((self.managed / new.name).exists())

    def test_second_config_write_failure_rolls_back_first(self):
        binary = self.executable(self.root / 'local/wine')
        self.executable(binary.parent / 'wineserver')
        original = b'{"wine_binary": "/old/wine"}'
        self.config_path.write_bytes(original)
        replace = os.replace
        portable = self.install / f'{constants.BINARY_NAME}.json'
        def fail_portable(source, target):
            if Path(target) == portable:
                raise OSError('read-only portable config')
            return replace(source, target)
        with patch('ou_dedetai.config.os.replace', side_effect=fail_portable):
            with self.assertRaises(OSError):
                runtime.activate_runtime(self.app, binary)
        self.assertEqual(self.config_path.read_bytes(), original)
        self.assertEqual(self.conf.wine_binary, '/old/wine')

    def test_cancel_menu_changes_nothing(self):
        self.app.ask.return_value = 'Cancel'
        runtime.select_runtime(self.app)
        self.assertEqual(self.conf.wine_binary, '/old/wine')
        self.assertFalse(self.config_path.exists())

    def test_cancel_file_dialog_changes_nothing(self):
        self.app.ask.side_effect = ['Add new…', UserExitedFromAsk(), 'Cancel']
        runtime.select_runtime(self.app)
        self.assertFalse(self.config_path.exists())

    def test_unknown_version_requires_confirmation(self):
        binary = self.executable(self.root / 'local/wine', 'wine-99.1 custom')
        self.executable(binary.parent / 'wineserver')
        self.app.approve.return_value = False
        with self.assertRaises(UserExitedFromAsk):
            runtime.activate_runtime(self.app, binary)
        self.assertEqual(self.conf.wine_binary, '/old/wine')
        self.app.approve.return_value = True
        runtime.activate_runtime(self.app, binary)
        self.assertEqual(self.conf.wine_binary, str(binary))

    def test_running_indexer_blocks_switch(self):
        self.app.logos.existing_processes = {'indexer': [Mock()]}
        with self.assertRaises(ValueError):
            runtime.activate_runtime(self.app, Path('/anything'))
        self.assertFalse(self.config_path.exists())

    def test_existing_non_symlink_is_not_overwritten(self):
        (self.managed / 'wine').write_text('preserve me')
        source = self.image(self.root / 'Downloads/new.AppImage')
        with self.assertRaises(ValueError):
            self.activate_image(source)
        self.assertEqual((self.managed / 'wine').read_text(), 'preserve me')
        self.assertEqual(self.conf.wine_binary, '/old/wine')

    def test_discovery_includes_wine_and_external_steam_library(self):
        local = self.executable(self.root / 'local/bin/wine')
        home = self.root / 'home'
        manifest = home / '.local/share/Steam/steamapps/libraryfolders.vdf'
        manifest.parent.mkdir(parents=True)
        library = self.root / 'extra library'
        manifest.write_text(f'"libraryfolders" {{ "1" {{ "path" "{library}" }} }}')
        proton = self.executable(library / 'steamapps/common/Proton 10/files/bin/wine')
        image = self.image(self.managed / 'installed.AppImage')
        with patch.object(Path, 'home', return_value=home), patch.dict(os.environ, {'PATH': str(local.parent)}):
            found = runtime.discover_runtimes(self.app)
        self.assertIn(local, found['System/local Wine'])
        self.assertIn(proton, found['Local Proton'])
        self.assertIn(image, found['Installed AppImages'])

    def test_recommended_update_uses_activation(self):
        self.conf._raw.wine_binary_code = 'AppImage'
        with patch.object(Config, 'wine_appimage_recommended_file_name', new_callable=PropertyMock,
                          return_value='recommended.AppImage'), \
                patch.object(utils, 'compare_recommended_appimage_version', return_value=(0, '')), \
                patch('ou_dedetai.network.download_recommended_appimage') as download, \
                patch.object(runtime, 'activate_runtime') as activate:
            utils.update_to_latest_recommended_appimage(self.app)
        download.assert_called_once_with(self.app)
        activate.assert_called_once_with(self.app, self.managed / 'recommended.AppImage')

    def test_installed_menu_marks_current_and_selects_another(self):
        old = self.image(self.managed / 'old.AppImage')
        new = self.image(self.managed / 'new.AppImage')
        self.activate_image(old)
        self.app.ask.side_effect = lambda question, options: next(label for label in options if str(new) in label)
        with patch.object(runtime, '_check_version'):
            runtime.select_runtime(self.app)
        options = self.app.ask.call_args_list[-1].args[1]
        self.assertTrue(any('(current)' in label and str(old) in label for label in options))
        self.assertEqual(self.conf.wine_binary, str(new))

    def test_custom_menu_can_select_separate_server(self):
        binary = self.executable(self.root / 'custom/loader')
        server = self.executable(self.root / 'elsewhere/server')
        self.app.ask.side_effect = ['Add new…', str(binary), str(server)]
        runtime.select_runtime(self.app)
        self.assertEqual(self.conf.wineserver_binary, str(server))

    def test_non_executable_local_wine_is_rejected(self):
        binary = self.executable(self.root / 'custom/wine')
        binary.chmod(0o644)
        with self.assertRaises(ValueError):
            runtime.activate_runtime(self.app, binary)
        self.assertEqual(self.conf.wine_binary, '/old/wine')

    def test_same_named_download_does_not_overwrite_installed_image(self):
        old = self.image(self.managed / 'same.AppImage')
        self.activate_image(old)
        before = old.read_bytes()
        new = self.image(self.root / 'Downloads/same.AppImage')
        new.write_bytes(before + b'different build')
        with self.assertRaises(ValueError):
            self.activate_image(new)
        self.assertEqual(old.read_bytes(), before)
        self.assertEqual(self.conf.wine_binary, str(old))

    def test_timeout_preserves_selection(self):
        import subprocess
        binary = self.executable(self.root / 'custom/wine')
        self.executable(binary.parent / 'wineserver')
        with patch.object(runtime.subprocess, 'run', side_effect=subprocess.TimeoutExpired('wine', 15)):
            with self.assertRaises(subprocess.TimeoutExpired):
                runtime.activate_runtime(self.app, binary)
        self.assertEqual(self.conf.wine_binary, '/old/wine')

    def test_combined_options_include_missing_and_custom_current(self):
        with patch.object(runtime, 'discover_runtimes', return_value={
            'Installed AppImages': [], 'System/local Wine': [], 'Local Proton': []
        }):
            options = runtime.runtime_options(self.app)
        self.assertEqual([o.label for o in options[1:]],
                         ['Local Wine (not found)', 'Local Proton (not found)'])
        self.assertTrue(options[0].current)
        self.assertEqual(options[0].path, Path('/old/wine'))

    def test_current_and_recommended_are_independent(self):
        option = runtime.RuntimeOption('wine.AppImage', Path('/wine.AppImage'), recommended=True)
        self.assertIn('(recommended)', option.label)
        self.assertNotIn('(current)', option.label)
        option.current = True
        self.assertIn('(current)', option.label)
        self.assertIn('(recommended)', option.label)

    def test_version_probe_timeout_is_unknown_not_missing(self):
        import subprocess
        with patch.object(runtime.subprocess, 'run', side_effect=subprocess.TimeoutExpired('wine', 3)) as run:
            self.assertEqual(runtime.runtime_version(Path('/wine')), 'version unknown')
        self.assertEqual(run.call_args.kwargs['timeout'], 3)

    def test_version_probe_reports_version(self):
        binary = self.executable(self.root / 'wine', 'wine-10.0 (Staging)')
        self.assertEqual(runtime.runtime_version(binary), 'wine-10.0 (Staging)')

    def test_add_activates_without_a_second_menu(self):
        source = self.image(self.root / 'Downloads/new.AppImage')
        self.app.ask.side_effect = ['Add new…', str(source)]
        with patch.object(runtime, '_check_version'):
            runtime.select_runtime(self.app)
        self.assertEqual(self.conf.wine_binary, str(self.managed / source.name))
        self.assertEqual(self.app.choose_runtime.call_count, 1)

    def test_current_choice_returns_without_writing(self):
        self.app.ask.side_effect = lambda question, options: next(x for x in options if '(current)' in x)
        with patch.object(runtime, 'activate_option') as activate:
            runtime.select_runtime(self.app)
        activate.assert_not_called()
        self.assertFalse(self.config_path.exists())

    def test_add_rejects_invalid_file_without_changing_selection(self):
        source = self.root / 'bad.AppImage'
        source.write_text('not an image')
        with self.assertRaises(ValueError):
            runtime.added_runtime(source)
        self.assertEqual(self.conf.wine_binary, '/old/wine')

    def test_proton_label_includes_build_name(self):
        binary = self.root / 'Proton 10/files/bin/wine'
        with patch.object(runtime, 'discover_runtimes', return_value={'Local Proton': [binary]}):
            options = runtime.runtime_options(self.app)
        self.assertTrue(any('Proton 10' in option.label for option in options))

    def test_failed_activation_returns_to_menu(self):
        image = self.image(self.managed / 'new.AppImage')
        self.app.ask.side_effect = [f'new.AppImage — {image}', 'Cancel']
        with patch.object(runtime, 'activate_runtime', side_effect=ValueError('bad runtime')):
            runtime.select_runtime(self.app)
        self.app.info.assert_called_once()
        self.assertEqual(self.app.ask.call_count, 2)
        self.assertEqual(self.conf.wine_binary, '/old/wine')

    def test_missing_recommendation_is_a_downloadable_choice(self):
        options = []
        release = ('recommended.AppImage', 'https://example.invalid/recommended.AppImage')
        runtime.include_recommended(self.app, options, release)
        runtime.include_recommended(self.app, options, release)
        self.assertEqual(len(options), 1)
        self.assertTrue(options[0].recommended)
        self.assertEqual(options[0].path, self.managed / release[0])
        self.assertEqual(options[0].download_url, release[1])
        self.assertIn('(recommended) (download required)', options[0].label)
        self.assertFalse(self.config_path.exists())

    def test_prerelease_is_offered_alongside_stable(self):
        self.conf._raw.wine_binary = constants.WINE_RECOMMENDED_SIGIL
        stable = runtime.AppImageRelease('wine-stable.AppImage', 'https://example.invalid/wine-stable.AppImage')
        pre = runtime.AppImageRelease('wine-pre.AppImage', 'https://example.invalid/wine-pre.AppImage', True)
        options = []
        runtime.include_releases(self.app, options, [stable, pre])
        runtime.include_releases(self.app, options, [stable, pre])
        runtime.include_recommended(self.app, options, (stable.name, stable.url))
        self.assertEqual([option.name for option in options], [stable.name, pre.name])
        self.assertTrue(options[0].recommended)
        self.assertFalse(options[0].prerelease)
        self.assertFalse(options[1].recommended)
        self.assertTrue(options[1].prerelease)
        self.assertEqual(options[1].download_url, pre.url)
        self.assertIn('(pre-release) (download required)', options[1].label)

    def test_prerelease_recommended_by_installer_is_one_option(self):
        pre = runtime.AppImageRelease('wine-pre.AppImage', 'https://example.invalid/wine-pre.AppImage', True)
        options = []
        runtime.include_releases(self.app, options, [pre])
        runtime.include_recommended(self.app, options, (pre.name, pre.url))
        self.assertEqual(len(options), 1)
        self.assertIn('(pre-release) (recommended) (download required)', options[0].label)

    def test_installed_prerelease_does_not_need_download(self):
        image = self.image(self.managed / 'wine-pre.AppImage')
        options = [runtime.RuntimeOption(image.name, image)]
        runtime.include_releases(self.app, options, [
            runtime.AppImageRelease(image.name, 'https://example.invalid/wine-pre.AppImage', True)])
        self.assertEqual(len(options), 1)
        self.assertTrue(options[0].prerelease)
        self.assertNotIn('download required', options[0].label)

    def test_available_appimages_reads_stable_and_prerelease(self):
        app = Mock()
        app.conf.wine_appimage_recommended_file_name = 'stable.AppImage'
        app.conf.wine_appimage_recommended_url = 'https://example.invalid/stable.AppImage'
        app.conf.wine_appimage_beta_file_name = 'pre.AppImage'
        app.conf.wine_appimage_beta_url = 'https://example.invalid/pre.AppImage'
        self.assertEqual(runtime.available_appimages(app), [
            runtime.AppImageRelease('stable.AppImage', 'https://example.invalid/stable.AppImage'),
            runtime.AppImageRelease('pre.AppImage', 'https://example.invalid/pre.AppImage', True)])
        app.conf.wine_appimage_beta_file_name = None
        app.conf.wine_appimage_beta_url = None
        self.assertEqual([release.name for release in runtime.available_appimages(app)], ['stable.AppImage'])

    def test_available_appimages_survives_network_failure(self):
        app = Mock()
        type(app.conf).wine_appimage_recommended_file_name = PropertyMock(side_effect=ValueError('offline'))
        type(app.conf).wine_appimage_beta_file_name = PropertyMock(side_effect=ValueError('offline'))
        self.assertEqual(runtime.available_appimages(app), [])

    def test_text_menu_lists_prerelease(self):
        pre = runtime.AppImageRelease('wine-pre.AppImage', 'https://example.invalid/wine-pre.AppImage', True)
        self.app.ask.side_effect = ['Cancel']
        with patch.object(runtime, 'discover_runtimes', return_value={
                    'Installed AppImages': [], 'System/local Wine': [], 'Local Proton': []}), \
                patch.object(runtime, 'recommended_appimage', return_value=None), \
                patch.object(runtime, 'available_appimages', return_value=[pre]):
            runtime.select_runtime(self.app)
        choices = self.app.ask.call_args.args[1]
        self.assertTrue(any(choice.startswith('wine-pre.AppImage (pre-release)') for choice in choices))

    def test_installed_recommendation_does_not_need_download(self):
        image = self.image(self.managed / 'recommended.AppImage')
        options = [runtime.RuntimeOption(image.name, image)]
        runtime.include_recommended(self.app, options, (image.name, 'https://example.invalid/image'))
        self.assertEqual(len(options), 1)
        self.assertTrue(options[0].recommended)
        self.assertNotIn('download required', options[0].label)

    def test_recommended_download_uses_installer_flow_then_activates(self):
        from ou_dedetai import installer, network
        self.conf._download_dir = str(self.root / 'cache')
        self.conf._user_download_dir = str(self.root / 'Downloads')
        Path(self.conf.download_dir).mkdir()
        name = 'recommended.AppImage'
        url = 'https://example.invalid/' + name
        option = runtime.RuntimeOption(name, self.managed / name, recommended=True, download_url=url)
        def download(source, target=None, app=None):
            self.assertEqual(source, url)
            self.assertEqual(self.conf.wine_binary, '/old/wine')
            self.image(target)
        with patch.object(network, '_net_get', side_effect=download), \
                patch.object(network, '_verify_downloaded_file', return_value=True) as verify, \
                patch.object(installer, 'download_appimage', wraps=installer.download_appimage) as shared, \
                patch.object(runtime, '_check_version'):
            runtime.activate_option(self.app, option)
        shared.assert_called_once()
        verify.assert_called_once()
        self.assertTrue(os.access(self.managed / name, os.X_OK))
        self.assertEqual(self.conf.wine_binary, str(self.managed / name))
        self.assertTrue(self.config_path.exists())

    def test_failed_download_is_recoverable_and_preserves_selection(self):
        from ou_dedetai import network
        self.conf._download_dir = str(self.root / 'cache')
        self.conf._user_download_dir = str(self.root / 'Downloads')
        Path(self.conf.download_dir).mkdir()
        option = runtime.RuntimeOption('recommended.AppImage', self.managed / 'recommended.AppImage',
                                       download_url='https://example.invalid/image')
        def download(source, target=None, app=None):
            target.write_bytes(b'bad download')
        with patch.object(network, '_net_get', side_effect=download), \
                patch.object(network, '_verify_downloaded_file', return_value=False), \
                patch.object(runtime, 'activate_runtime') as activate:
            with self.assertRaisesRegex(ValueError, 'Bad file size or checksum'):
                runtime.activate_option(self.app, option)
        activate.assert_not_called()
        self.app.exit.assert_not_called()
        self.assertEqual(self.conf.wine_binary, '/old/wine')
        self.assertFalse(self.config_path.exists())
        self.assertFalse(option.path.exists())

    def test_cancelling_downloadable_menu_does_not_download(self):
        self.app.ask.return_value = 'Cancel'
        with patch('ou_dedetai.installer.download_appimage') as download:
            runtime.select_runtime(self.app)
        download.assert_not_called()
        self.assertTrue(any('(download required)' in label for label in self.app.ask.call_args.args[1]))

    def test_running_logos_blocks_download(self):
        option = runtime.RuntimeOption('recommended.AppImage', self.managed / 'recommended.AppImage',
                                       download_url='https://example.invalid/image')
        self.app.logos.existing_processes = {'logos': [Mock()]}
        with patch('ou_dedetai.installer.download_appimage') as download:
            with self.assertRaises(ValueError):
                runtime.activate_option(self.app, option)
        download.assert_not_called()

    def preinstall(self):
        self.app.is_installed.return_value = False
        self.conf._raw.write_config = Mock()
        self.conf._raw.faithlife_product = None
        self.conf._raw.faithlife_product_version = None
        self.conf._raw.install_dir = None
        self.conf._raw.wine_binary = None
        self.conf._download_dir = str(self.root / 'cache')

    def test_fresh_runtime_list_does_not_prompt_or_set_install_dir(self):
        self.preinstall()
        with patch.object(runtime, 'discover_runtimes', return_value={'System/local Wine': [], 'Local Proton': []}):
            options = runtime.runtime_options(self.app)
            runtime.include_releases(self.app, options, [
                runtime.AppImageRelease('pre.AppImage', 'https://example.invalid/pre.AppImage', True)])
        self.assertFalse(any(option.current for option in options))
        self.assertEqual(options[-1].path, self.root / 'cache/pre.AppImage')
        self.app.ask.assert_not_called()
        self.assertIsNone(self.conf._raw.faithlife_product)
        self.assertIsNone(self.conf._raw.install_dir)
        self.assertEqual(list(self.managed.glob('*')) if self.managed.exists() else [], [])

    def test_preinstall_release_is_recorded_for_the_installer_not_downloaded(self):
        from ou_dedetai import installer
        self.preinstall()
        option = runtime.RuntimeOption('pre.AppImage', self.root / 'cache/pre.AppImage',
                                       download_url='https://example.invalid/pre.AppImage', prerelease=True)
        with patch.object(installer, 'download_appimage') as download:
            runtime.activate_option(self.app, option)
        download.assert_not_called()
        self.app.ask.assert_not_called()
        self.assertEqual(self.conf._raw.wine_binary, f'{constants.RELATIVE_BINARY_DIR}/pre.AppImage')
        self.assertIsNone(self.conf._raw.wine_server)
        self.assertIsNone(self.conf._raw.install_dir)
        # Reopening the picker shows it as the current choice, once.
        with patch.object(runtime, 'discover_runtimes', return_value={'System/local Wine': [], 'Local Proton': []}):
            options = runtime.runtime_options(self.app)
            runtime.include_releases(self.app, options, [
                runtime.AppImageRelease('pre.AppImage', 'https://example.invalid/pre.AppImage', True)])
        listed = [option for option in options if option.path is not None]
        self.assertEqual(len(listed), 1)
        self.assertTrue(listed[0].current and listed[0].prerelease)

    def test_finished_selection_stops_the_progress_spinner(self):
        # A status without a percentage means "still working" and spins forever.
        self.activate_image(self.image(self.root / 'Downloads/wine.AppImage'))
        self.assertEqual(self.app.status.call_args.args[1:], (100,))
        self.app.status.reset_mock()
        self.preinstall()
        option = runtime.RuntimeOption('pre.AppImage', self.root / 'cache/pre.AppImage',
                                       download_url='https://example.invalid/pre.AppImage')
        runtime.activate_option(self.app, option)
        self.assertEqual(self.app.status.call_args.args[1:], (100,))

    def test_preinstall_appimage_is_recorded_then_copied_by_installer(self):
        from ou_dedetai import installer
        self.preinstall()
        image = self.image(self.root / 'Downloads/personal.AppImage')
        runtime.activate_option(self.app, runtime.RuntimeOption(image.name, image))
        # Nothing copied, linked or created yet; the install dir isn't decided.
        self.assertEqual(list(self.managed.glob('*')) if self.managed.exists() else [], [])
        self.assertIsNone(self.conf._raw.install_dir)
        self.assertEqual(self.conf._raw.wine_binary, str(image))
        self.app.ask.assert_not_called()
        # The installer then uses that AppImage exactly as if picked in its own prompt.
        # The installer asks for the product before the install dir.
        self.conf.faithlife_product = 'Logos'
        self.conf.faithlife_product_version = '10'
        self.conf._raw.install_dir = str(self.install)
        self.app.installer_step = self.app.installer_step_count = 0
        with patch.object(installer, 'ensure_sys_deps'), \
                patch.object(installer, 'check_system_compatibility'), \
                patch.object(installer, 'download_appimage') as download, \
                patch.object(Config, 'wine_appimage_recommended_file_name', new_callable=PropertyMock,
                             return_value='stable.AppImage'), \
                patch.object(Config, 'wine_appimage_beta_file_name', new_callable=PropertyMock,
                             return_value='pre.AppImage'), \
                patch.dict(os.environ, {'PATH': os.environ.get('PATH', '')}):
            installer.ensure_wine_executables(self.app)
        download.assert_not_called()
        selected = self.managed / image.name
        self.assertTrue(os.access(selected, os.X_OK))
        self.assertEqual(self.conf.wine_binary, str(selected))
        self.assertEqual((self.managed / self.conf.wine_appimage_link_file_name).resolve(), selected)

    def test_preinstall_appimage_removed_before_install_is_reported(self):
        from ou_dedetai import installer
        self.preinstall()
        image = self.image(self.root / 'Downloads/personal.AppImage')
        runtime.activate_option(self.app, runtime.RuntimeOption(image.name, image))
        image.unlink()
        self.conf.faithlife_product = 'Logos'
        self.conf.faithlife_product_version = '10'
        self.conf._raw.install_dir = str(self.install)
        self.app.installer_step = self.app.installer_step_count = 0
        with patch.object(installer, 'ensure_sys_deps'), \
                patch.object(installer, 'check_system_compatibility'), \
                patch.object(installer, 'download_appimage') as download, \
                patch.object(Config, 'wine_appimage_recommended_file_name', new_callable=PropertyMock,
                             return_value='stable.AppImage'), \
                patch.object(Config, 'wine_appimage_beta_file_name', new_callable=PropertyMock,
                             return_value='pre.AppImage'), \
                self.assertRaisesRegex(ValueError, 'missing'):
            installer.ensure_appimage_download(self.app)
        download.assert_not_called()

    def test_preinstall_custom_wine_and_separate_server_are_recorded(self):
        from ou_dedetai import installer
        self.preinstall()
        binary = self.executable(self.root / 'my-build/loader/wine')
        server = self.executable(self.root / 'my-build/server/wineserver')
        runtime.activate_option(self.app, runtime.RuntimeOption('Custom Wine', binary), server)
        self.app.logos.get_logos_pids.assert_not_called()
        self.app.ask.assert_not_called()
        self.assertIsNone(self.conf._raw.install_dir)
        self.assertEqual(self.conf._raw.wine_binary, str(binary))
        self.assertEqual(self.conf._raw.wine_server, str(server))
        # The installer asks for the product before the install dir.
        self.conf.faithlife_product = 'Logos'
        self.conf.faithlife_product_version = '10'
        self.conf._raw.install_dir = str(self.install)
        self.app.installer_step = self.app.installer_step_count = 0
        with patch.object(installer, 'ensure_sys_deps'), \
                patch.object(installer, 'check_system_compatibility'), \
                patch.object(installer, 'download_appimage') as download, \
                patch.object(installer, 'create_wine_appimage_symlinks') as relink:
            installer.ensure_wine_executables(self.app)
        download.assert_not_called()
        relink.assert_not_called()
        self.assertEqual(self.conf.wine64_binary, str(binary))
        self.assertEqual(self.conf.wineserver_binary, str(server))
        self.assertEqual(wine.get_wine_env(self.app)['WINE'], str(binary))
        self.assertEqual(wine.get_wine_env(self.app)['WINESERVER'], str(server))

    def test_preinstall_adjacent_wineserver_is_not_stored(self):
        self.preinstall()
        binary = self.executable(self.root / 'build/bin/wine')
        self.executable(self.root / 'build/bin/wineserver')
        runtime.activate_option(self.app, runtime.RuntimeOption('Custom Wine', binary))
        self.assertEqual(self.conf._raw.wine_binary, str(binary))
        self.assertIsNone(self.conf._raw.wine_server)

    def test_preinstall_choice_still_warns_about_incompatible_wine(self):
        self.preinstall()
        binary = self.executable(self.root / 'old/bin/wine', version='wine-6.0')
        self.executable(self.root / 'old/bin/wineserver')
        self.app.approve.return_value = False
        with self.assertRaises(UserExitedFromAsk):
            runtime.activate_option(self.app, runtime.RuntimeOption('Custom Wine', binary))
        self.app.approve.assert_called_once()
        self.assertIsNone(self.conf._raw.wine_binary)

    def test_missing_preselected_runtime_fails_instead_of_using_default(self):
        from ou_dedetai import installer
        self.app.installer_step = self.app.installer_step_count = 0
        self.conf._raw.wine_server = '/missing/wineserver'
        with patch.object(installer, 'ensure_sys_deps'), patch.object(installer, 'check_system_compatibility'), \
                patch.object(installer, 'download_appimage') as download:
            with self.assertRaisesRegex(ValueError, 'Selected Wine runtime is missing'):
                installer.ensure_appimage_download(self.app)
        download.assert_not_called()
