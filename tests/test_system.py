import os
import io
import json
import tarfile
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ou_dedetai import system, network


class TestAkousousinInstall(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.app = Mock()
        self.app.conf.download_dir = str(self.root / 'downloads')
        Path(self.app.conf.download_dir).mkdir()
        self.app.conf.wine_prefix = str(self.root / 'prefix with spaces')
        self.app.conf.wine_binary = '/path with spaces/Wine.AppImage'
        self.app.exit.side_effect = RuntimeError
        self.app.conf._network._repo_version.return_value = network.SoftwareReleaseInfo('beta-123', 'https://example/package')
        self.launcher = self.root / '.local/bin/akousousin'
        for target, kwargs in (
            ('pathlib.Path.home', {'return_value': self.root}),
            ('ou_dedetai.system.network.logos_reuse_download', {'side_effect': self.download}),
            ('ou_dedetai.system.run_command', {'side_effect': self.run_command_stub}),
        ):
            mock = patch(target, **kwargs)
            setattr(self, target.split('.')[-1], mock.start())
            self.addCleanup(mock.stop)

    def download(self, url, filename, directory, app):
        target = Path(directory) / filename
        self.assertTrue(filename.endswith('Akousousin-Linux-x86_64.tar.gz'))
        with tarfile.open(target, 'w:gz') as archive:
            script = b'#!/bin/sh\nexit 0\n'
            member = tarfile.TarInfo('Akousousin/install.sh')
            member.size = len(script)
            archive.addfile(member, io.BytesIO(script))

    def run_command_stub(self, command, **kwargs):
        if command[0] == 'sh':
            self.assertTrue(Path(command[1]).is_file())
            self.assertEqual(command[2:], ['--quiet'])
            self.launcher.parent.mkdir(parents=True)
            self.launcher.touch()
        return subprocess.CompletedProcess(command, 0, '', '')

    def assert_registration(self, executable):
        self.assertEqual(self.run_command.call_args.args[0],
                         [str(executable), '--wine-prefix', self.app.conf.wine_prefix,
                          '--wine', self.app.conf.wine_binary, '--install-only'])
        self.app.exit.assert_not_called()

    def test_default_bundle_is_installed_quietly_before_registration(self):
        with patch.object(network, '_get_release_data', return_value=network.SoftwareReleaseInfo(
                'beta-123', 'https://example/package')) as lookup:
            system.ensure_akousousin(self.app)
        self.assertTrue(self.logos_reuse_download.call_args.args[1].endswith('Akousousin-Linux-x86_64.tar.gz'))
        lookup.assert_called_once_with(
            "jg00dman/akousousin", tag="latest", asset_name=r"Akousousin\-Linux\-x86_64\.tar\.gz",
        )
        self.assertEqual(self.run_command.call_count, 2)
        self.assert_registration(self.launcher)
        self.app.ask.assert_not_called()

    def test_existing_shared_installation_is_reused_without_download(self):
        self.launcher.parent.mkdir(parents=True)
        self.launcher.touch()
        system.ensure_akousousin(self.app)
        self.assert_registration(self.launcher)
        self.app.conf._network._repo_version.assert_not_called()
        self.app.ask.assert_not_called()

    def test_bundle_install_failure_prevents_registration(self):
        self.run_command.side_effect = subprocess.CalledProcessError(1, ['sh'], stderr='install failed')
        self.assertFalse(system.ensure_akousousin(self.app))
        self.assertEqual(self.run_command.call_count, 1)
        self.app.exit.assert_not_called()  # reported, never fatal

    def test_registration_failure_is_reported(self):
        self.launcher.parent.mkdir(parents=True)
        self.launcher.touch()
        self.run_command.side_effect = subprocess.CalledProcessError(1, ['akousousin'], stderr='registration failed')
        self.assertFalse(system.ensure_akousousin(self.app))
        self.app.exit.assert_not_called()

    def test_no_stable_release_is_reported_not_fatal(self):
        with patch.object(network, '_get_release_data', side_effect=RuntimeError(
                "Could not retrieve releases from GitHub: jg00dman/akousousin")):
            self.assertFalse(system.ensure_akousousin(self.app))
        self.app.exit.assert_not_called()
        self.run_command.assert_not_called()
        self.assertIn("stable Akousousin release", self.app.status.call_args.args[0])


class TestStableAkousousinRelease(unittest.TestCase):
    def test_uses_github_latest_stable_endpoint_and_exact_tar_asset(self):
        release = {"tag_name": "v1.0", "assets": [
            {"name": "Akousousin-x86_64.AppImage", "browser_download_url": "https://x/appimage"},
            {"name": "Akousousin-Linux-x86_64.tar.gz", "browser_download_url": "https://x/tar"},
        ]}
        with patch.object(network, "_net_get", return_value=json.dumps(release).encode()) as get:
            result = network._get_release_data("jg00dman/akousousin", tag="latest",
                                               asset_name=r"Akousousin-Linux-x86_64\.tar\.gz")
        self.assertEqual(result.version, "1.0")
        self.assertEqual(result.download_url, "https://x/tar")
        get.assert_called_once_with("https://api.github.com/repos/jg00dman/akousousin/releases/latest")


class TestAkousousinUpdate(unittest.TestCase):
    setUp = TestAkousousinInstall.setUp
    download = TestAkousousinInstall.download
    run_command_stub = TestAkousousinInstall.run_command_stub
    assert_registration = TestAkousousinInstall.assert_registration

    def test_update_reinstalls_existing_bundle_using_fresh_stable_lookup(self):
        self.launcher.parent.mkdir(parents=True)
        self.launcher.touch()
        self.run_command.side_effect = lambda command, **kwargs: subprocess.CompletedProcess(command, 0, '', '')
        with patch.object(network, '_get_release_data', return_value=network.SoftwareReleaseInfo(
            'v1', 'https://example/stable.tar.gz',
        )) as lookup:
            system.ensure_akousousin(self.app, update=True)
        lookup.assert_called_once_with('jg00dman/akousousin', tag='latest',
                                       asset_name=r'Akousousin\-Linux\-x86_64\.tar\.gz')
        self.app.conf._network._repo_version.assert_not_called()
        self.assertEqual(self.run_command.call_count, 2)
        self.assert_registration(self.launcher)

    def test_update_skipped_when_up_to_date(self):
        self.app.is_installed.return_value = True
        self.launcher.parent.mkdir(parents=True, exist_ok=True)
        self.launcher.touch()
        with patch.object(system, 'akousousin_update', return_value=None), \
                patch.object(system, 'ensure_akousousin') as install:
            system.update_akousousin(self.app)
        install.assert_not_called()

    def test_update_asks_akousousin_to_quit_not_logos(self):
        from ou_dedetai.logos import State
        self.app.is_installed.return_value = True
        self.app.logos.logos_state = State.RUNNING
        self.launcher.parent.mkdir(parents=True, exist_ok=True)
        self.launcher.touch()
        with patch.object(system, 'akousousin_update', return_value='9.9'), \
                patch.object(system.subprocess, 'run') as run, \
                patch.object(system, 'ensure_akousousin') as install:
            system.update_akousousin(self.app)
        self.assertEqual(run.call_args[0][0], [str(self.launcher), '--quit'])
        install.assert_called_once_with(self.app, update=True)

    def test_newer_release_detected(self):
        self.launcher.parent.mkdir(parents=True, exist_ok=True)
        self.launcher.touch()
        latest = network.SoftwareReleaseInfo('v0.9.0', 'u')
        with patch.object(system, 'akousousin_version', return_value='0.8.2'), \
                patch.object(network, 'is_offline', return_value=False), \
                patch.object(network, '_get_release_data', return_value=latest) as fresh:
            self.assertEqual(system.akousousin_update(self.app), '0.9.0')
        fresh.assert_called_once()  # not the 12-hour cache
        self.app.conf._network._repo_version.assert_not_called()
        with patch.object(system, 'akousousin_version', return_value='0.9.0'), \
                patch.object(network, 'is_offline', return_value=False), \
                patch.object(network, '_get_release_data', return_value=latest):
            self.assertIsNone(system.akousousin_update(self.app))

    def test_update_refreshes_registration_after_install(self):
        from ou_dedetai.logos import State
        self.app.is_installed.return_value = True
        self.app.logos.logos_state = State.STOPPED
        with patch.object(system, 'ensure_akousousin') as install:
            system.update_akousousin(self.app)
        install.assert_called_once_with(self.app, update=True)


class TestAkousousinActions(unittest.TestCase):
    def test_cli_flag_dispatches_update(self):
        from ou_dedetai import cli, cli_parser
        parser = cli_parser.get_parser()
        args = parser.parse_args(['--update-akousousin'])
        with (patch.object(cli_parser.EphemeralConfiguration, 'load', return_value=Mock()),
              patch.object(cli, 'CLI') as command):
            config, action = cli_parser.od_parse_args(args, parser)
            action(config)
        command.return_value.update_akousousin.assert_called_once_with()
        with patch.object(system, 'update_akousousin') as update:
            cli.CLI.update_akousousin(config)
        update.assert_called_once_with(config)

    def test_gui_and_tui_dispatch_update_in_worker(self):
        from ou_dedetai import gui_main, tui_app
        gui = Mock()
        gui_main.MainWindow.update_akousousin(gui)
        gui.start_thread.assert_called_once()
        tui = Mock()
        tui_app.TUI.utilities_menu_select(tui, 'Update Akousousin')
        tui.start_thread.assert_called_once_with(system.update_akousousin, tui)
        self.assertIn('Update Akousousin', tui_app.TUI.set_utilities_menu_options(tui))


class TestAkousousinInstalled(unittest.TestCase):
    def test_reports_whether_the_launcher_exists(self):
        import tempfile
        with tempfile.TemporaryDirectory() as home, patch.object(system.Path, "home", return_value=Path(home)):
            self.assertFalse(system.akousousin_installed())
            (Path(home) / ".local/bin").mkdir(parents=True)
            (Path(home) / ".local/bin/akousousin").write_text("#!/bin/sh\n")
            self.assertTrue(system.akousousin_installed())


class TestImageBasedOS(unittest.TestCase):
    def test_ostree_is_image_based(self):
        from unittest.mock import patch
        from ou_dedetai import system
        with patch("ou_dedetai.system.Path.exists", return_value=True):
            self.assertTrue(system.is_image_based_os())

    def test_skips_packages_on_image_based_os(self):
        from unittest.mock import Mock, patch
        from ou_dedetai import system
        app = Mock()
        app.conf.skip_install_system_dependencies = False
        with patch("ou_dedetai.system.is_image_based_os", return_value=True), \
                patch("ou_dedetai.system.get_package_manager") as get_pm:
            system.install_dependencies(app)
        get_pm.assert_not_called()
        app.status.assert_called()


class TestGetOsWithoutUname(unittest.TestCase):
    def test_failing_uname_doesnt_stop_os_detection(self):
        import distro as distro_module
        fresh = distro_module.LinuxDistribution(include_uname=False, include_lsb=False)
        with patch.object(system, '_distro', fresh), \
                patch('subprocess.check_output', side_effect=subprocess.CalledProcessError(1, ['uname', '-rs'])):
            name, _ = system.get_os()
        self.assertTrue(name)


class TestWinetricksTools(unittest.TestCase):
    def setUp(self):
        self.app = Mock()
        self.app.superuser_command = "pkexec"
        apt = system.PackageManager(install=["apt", "install", "-y"], download=[], remove=[], query=[],
                                    query_prefix="", packages="", incompatible_packages="")
        for target, value in (("is_image_based_os", False), ("get_package_manager", apt)):
            p = patch.object(system, target, return_value=value)
            p.start()
            self.addCleanup(p.stop)

    def test_nothing_asked_when_tools_present(self):
        with patch.object(system, "missing_winetricks_tools", return_value=[]):
            system.offer_winetricks_tools(self.app)
        self.app.approve.assert_not_called()

    def test_offers_only_the_missing_packages(self):
        self.app.approve.return_value = True
        with patch.object(system, "missing_winetricks_tools", return_value=["cabextract", "7z"]), \
                patch.object(system, "run_command") as run:
            system.offer_winetricks_tools(self.app)
        run.assert_called_once_with(["pkexec", "apt", "install", "-y", "cabextract", "7zip"])

    def test_declining_installs_nothing(self):
        self.app.approve.return_value = False
        with patch.object(system, "missing_winetricks_tools", return_value=["unzip"]), \
                patch.object(system, "run_command") as run:
            system.offer_winetricks_tools(self.app)
        run.assert_not_called()


class TestStartupEnvironment(unittest.TestCase):
    def test_main_keeps_the_environment_but_restores_library_path(self):
        from ou_dedetai import constants, main
        env = {"HOME": "/home/x", "DISPLAY": ":0", "LD_LIBRARY_PATH": "/tmp/_MEI1", "LD_LIBRARY_PATH_ORIG": "/usr/lib"}
        with patch.dict(os.environ, env, clear=True), patch.object(constants, "RUNMODE", "binary"), \
                patch.object(main.msg, "initialize_logging", side_effect=RuntimeError("stop")):
            with self.assertRaises(RuntimeError):
                main.main()
            self.assertEqual(os.environ.get("DISPLAY"), ":0")
            self.assertEqual(os.environ.get("LD_LIBRARY_PATH"), "/usr/lib")


class TestAppImageRuntime(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.appimage = Path(directory.name) / "wine.AppImage"
        self.appimage.touch()
        self.app = Mock()
        self.app.superuser_command = "pkexec"
        system.appimage_runs.cache_clear()
        self.addCleanup(system.appimage_runs.cache_clear)
        self.apt = system.PackageManager(install=["apt", "install", "-y"], download=[], remove=[], query=[],
                                         query_prefix="", packages="", incompatible_packages="")

    def runs(self, mounted, extracted):
        return lambda path, extract=False: extracted if extract else mounted

    def test_nothing_happens_when_it_runs(self):
        with patch.object(system, "appimage_runs", side_effect=self.runs(True, True)), \
                patch.object(system, "run_command") as run:
            system.ensure_appimage_runtime(self.app, str(self.appimage))
        self.app.approve.assert_not_called()
        run.assert_not_called()

    def test_offers_only_fuse_on_a_normal_distro(self):
        self.app.approve.return_value = True
        with patch.object(system, "appimage_runs", side_effect=self.runs(False, True)) as runs, \
                patch.object(system, "is_image_based_os", return_value=False), \
                patch.object(system, "get_package_manager", return_value=self.apt), \
                patch.object(system, "_fuse_package", return_value="libfuse2t64"), \
                patch.object(system, "run_command") as run:
            runs.cache_clear = Mock()
            system.ensure_appimage_runtime(self.app, str(self.appimage))
        run.assert_called_once_with(["pkexec", "apt", "install", "-y", "libfuse2t64"])

    def test_image_based_system_unpacks_instead(self):
        with patch.object(system, "appimage_runs", side_effect=self.runs(False, True)), \
                patch.object(system, "is_image_based_os", return_value=True), \
                patch.object(system, "run_command") as run:
            system.ensure_appimage_runtime(self.app, str(self.appimage))
        self.app.approve.assert_not_called()
        run.assert_not_called()
        self.assertIn("unpack", self.app.status.call_args[0][0])

    def test_needs_extract(self):
        with patch.object(system, "appimage_runs", side_effect=self.runs(False, True)):
            self.assertTrue(system.appimage_needs_extract(str(self.appimage)))
        with patch.object(system, "appimage_runs", side_effect=self.runs(True, True)):
            self.assertFalse(system.appimage_needs_extract(str(self.appimage)))


class TestWineReleaseOfUnpackingAppImage(unittest.TestCase):
    def test_version_read_with_extract_and_run(self):
        from ou_dedetai import wine
        with patch.object(system, "appimage_needs_extract", return_value=True), \
                patch("subprocess.check_output", return_value="wine-11.22 (oinos)") as run:
            release, _ = wine.get_wine_release("/x/wine.AppImage")
        self.assertEqual(run.call_args.kwargs["env"]["APPIMAGE_EXTRACT_AND_RUN"], "1")
        self.assertEqual(release.release, "oinos")


class TestWlClipboardOffer(unittest.TestCase):
    def setUp(self):
        self.app = Mock()
        self.app.superuser_command = "pkexec"
        apt = system.PackageManager(install=["apt", "install", "-y"], download=[], remove=[], query=[],
                                    query_prefix="", packages="", incompatible_packages="")
        p = patch.object(system, "get_package_manager", return_value=apt)
        p.start()
        self.addCleanup(p.stop)

    def test_not_offered_when_wl_paste_exists(self):
        with patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}), \
                patch.object(system, "wl_paste_available", return_value=True):
            system.offer_wl_clipboard(self.app)
        self.app.approve.assert_not_called()

    def test_offered_on_wayland_without_it(self):
        self.app.approve.return_value = True
        with patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}), \
                patch.object(system, "wl_paste_available", return_value=False), \
                patch.object(system, "is_image_based_os", return_value=False), \
                patch.object(system, "run_command") as run:
            system.offer_wl_clipboard(self.app)
        run.assert_called_once_with(["pkexec", "apt", "install", "-y", "wl-clipboard"])
