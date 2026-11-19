import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ou_dedetai import constants, wine


class TestPrintingSetup(unittest.TestCase):
    def test_set_font_replacements_writes_multi_sz_per_family(self):
        app = mock.Mock()
        with mock.patch.object(wine, "run_wine_during_install") as run, \
                mock.patch.object(wine, "wineserver_wait"):
            wine.set_font_replacements(app, "/fake/wine64")

        self.assertEqual(run.call_count, len(wine.FONT_REPLACEMENTS))
        for call, (family, replacements) in zip(run.call_args_list, wine.FONT_REPLACEMENTS.items()):
            args = call.kwargs["exe_args"]
            self.assertEqual(call.kwargs["exe"], "reg")
            self.assertEqual(args[1], "HKCU\\Software\\Wine\\Fonts\\Replacements")
            self.assertEqual(args[args.index("/v") + 1], family)
            self.assertEqual(args[args.index("/t") + 1], "REG_MULTI_SZ")
            self.assertEqual(args[args.index("/d") + 1], "\\0".join(replacements))

    def test_configure_printing_disables_xps_om_and_xpsprint(self):
        app = mock.Mock()
        with mock.patch.object(wine, "wine_reg_install") as install:
            wine.configure_printing(app, "/fake/wine64")

        reg_text = install.call_args.args[2]
        self.assertTrue(reg_text.startswith("REGEDIT4"))
        self.assertIn(
            "[HKEY_CURRENT_USER\\Software\\Microsoft\\.NETFramework\\Windows Presentation Foundation\\Printing]",
            reg_text,
        )
        self.assertIn('"DisableXPSOMPrinting"=dword:00000001', reg_text)
        self.assertIn('"xpsprint"=""', reg_text)


class TestLogosUpdates(unittest.TestCase):
    def release_of(self, version_output):
        with mock.patch.object(wine.subprocess, "check_output", return_value=version_output + "\n"):
            release, _ = wine.get_wine_release("/fake/wine")
        return release

    def test_oinos_build_supports_updates(self):
        release = self.release_of("wine-11.21 (oinos)")
        self.assertEqual((release.major, release.minor, release.release), (11, 21, "oinos"))
        self.assertTrue(wine.wine_supports_logos_updates(release))

    def test_oinos_git_build_supports_updates(self):
        self.assertTrue(wine.wine_supports_logos_updates(self.release_of("wine-11.21-212-gc66925d1e (oinos)")))

    def test_other_builds_keep_updates_suppressed(self):
        for output in ("wine-11.21", "wine-11.0", "wine-10.15 (Staging)", "wine-11.21-212-gc66925d1e"):
            with self.subTest(output=output):
                self.assertFalse(wine.wine_supports_logos_updates(self.release_of(output)))
        self.assertFalse(wine.wine_supports_logos_updates(None))

    def test_allow_logos_updates_lists_msix_registration(self):
        app = mock.Mock()
        with mock.patch.object(wine, "run_wine_during_install") as run:
            wine.allow_logos_updates(app, "/fake/wine")
        args = run.call_args_list[0].kwargs["exe_args"]
        self.assertEqual(run.call_args.kwargs["exe"], "reg")
        self.assertEqual(args[1], "HKCU\\Software\\Wine\\MSI")
        self.assertEqual(args[args.index("/v") + 1], "IgnoreFailedActions")
        self.assertEqual(args[args.index("/t") + 1], "REG_MULTI_SZ")
        self.assertEqual(args[args.index("/d") + 1], "RegisterStubMsixPackage")
        media = run.call_args_list[1].kwargs["exe_args"]
        self.assertEqual(media[1], "HKCU\\Software\\Wine\\MediaFoundation")
        self.assertEqual(media[media.index("/v") + 1], "DisableGstByteStreamHandler")


USER_REG_DXVK = """WINE REGISTRY Version 2

[Software\\\\Wine\\\\Direct3D] 1793546779
"renderer"="gdi"

[Software\\\\Wine\\\\DllOverrides] 1793546780
"d3d11"="native"
"d3d9"="native"
"dxgi"="native"
"""


class TestRenderer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = mock.Mock()
        self.app.conf.wine_prefix = self.tmp.name
        self.app.conf.wine_appimage_path = None
        self.app.conf.wine_binary = str(Path(self.tmp.name) / "bin" / "wine")

    def write_user_reg(self, text):
        (Path(self.tmp.name) / "user.reg").write_text(text)

    def test_dxvk_enabled_reads_dll_overrides(self):
        self.assertFalse(wine.dxvk_enabled(self.app))
        self.write_user_reg(USER_REG_DXVK)
        self.assertTrue(wine.dxvk_enabled(self.app))
        self.assertEqual(wine.get_effective_renderer(self.app), "dxvk")
        self.write_user_reg(USER_REG_DXVK.replace('"d3d9"="native"', '"d3d9"="builtin"'))
        self.assertFalse(wine.dxvk_enabled(self.app))
        self.assertEqual(wine.get_effective_renderer(self.app), "gdi")

    def test_dxvk_tool_command_appimage_and_tarball(self):
        self.assertIsNone(wine.dxvk_tool_command(self.app, "dxvk-install"))
        bindir = Path(self.tmp.name) / "bin"
        bindir.mkdir()
        (bindir / "dxvk-install").write_text("#!/bin/sh\n")
        self.assertEqual(wine.dxvk_tool_command(self.app, "dxvk-install"), [str(bindir / "dxvk-install")])
        self.app.conf.wine_appimage_path = Path("/x/wine.AppImage")
        self.assertEqual(wine.dxvk_tool_command(self.app, "dxvk-install"), ["/x/wine.AppImage", "dxvk-install"])

    def test_run_dxvk_tool_maps_exit_codes(self):
        self.app.conf.wine_appimage_path = Path("/x/wine.AppImage")
        for code, expected in ((0, 0), (3, 3), (53, None), (1, None)):
            with self.subTest(code=code), \
                    mock.patch.object(wine, "get_wine_env", return_value={}), \
                    mock.patch.object(wine.subprocess, "run",
                                      return_value=subprocess.CompletedProcess([], code, "", "")):
                self.assertEqual(wine.run_dxvk_tool(self.app, "dxvk-install"), expected)

    def test_default_renderer_oinos_uses_dxvk_or_gl(self):
        oinos = wine.WineRelease(11, 21, "oinos")
        for code, expected in ((0, "dxvk"), (3, "gl")):
            with self.subTest(code=code), \
                    mock.patch.object(wine, "get_wine_release", return_value=(oinos, "yes")), \
                    mock.patch.object(wine, "run_dxvk_tool", return_value=code), \
                    mock.patch.object(wine, "wineserver_wait"), \
                    mock.patch.object(wine, "set_renderer") as set_renderer:
                wine.set_default_renderer(self.app)
                set_renderer.assert_not_called()
                self.assertEqual(wine.set_dxvk_or_gl(self.app), expected)

    def test_default_renderer_oinos_without_dxvk_tool_uses_gl(self):
        with mock.patch.object(wine, "get_wine_release", return_value=(wine.WineRelease(11, 21, "oinos"), "yes")), \
                mock.patch.object(wine, "run_dxvk_tool", return_value=None), \
                mock.patch.object(wine, "set_renderer") as set_renderer:
            wine.set_default_renderer(self.app)
        self.assertEqual(set_renderer.call_args.args[2], "gl")

    def test_default_renderer_other_wine_keeps_gdi(self):
        for release in (wine.WineRelease(11, 21, "devel"), wine.WineRelease(10, 15, "staging"), None):
            with self.subTest(release=release), \
                    mock.patch.object(wine, "get_wine_release", return_value=(release, "")), \
                    mock.patch.object(wine, "run_dxvk_tool") as tool, \
                    mock.patch.object(wine, "set_renderer") as set_renderer:
                wine.set_default_renderer(self.app)
                tool.assert_not_called()
                self.assertEqual(set_renderer.call_args.args[2], "gdi")

    def test_select_renderer_dxvk_reports_fallback(self):
        with mock.patch.object(wine, "wineserver_wait"):
            for code, words in ((0, "DXVK"), (3, "OpenGL"), (None, "doesn't include DXVK")):
                with self.subTest(code=code), mock.patch.object(wine, "run_dxvk_tool", return_value=code):
                    self.assertIn(words, wine.select_renderer(self.app, "dxvk"))

    def test_select_other_renderer_removes_dxvk_first(self):
        self.write_user_reg(USER_REG_DXVK)
        with mock.patch.object(wine, "run_dxvk_tool", return_value=0) as tool, \
                mock.patch.object(wine, "wineserver_wait"), \
                mock.patch.object(wine, "set_renderer") as set_renderer:
            wine.select_renderer(self.app, "gl")
        tool.assert_called_once_with(self.app, "dxvk-uninstall")
        self.assertEqual(set_renderer.call_args.args[2], "gl")



class TestMonoGeckoOnlyForWineboot(unittest.TestCase):
    def test_normal_runs_keep_mscoree(self):
        # Wine's loader needs mscoree.dll for Logos's .NET assemblies.
        from unittest import mock
        from ou_dedetai import wine
        app = mock.Mock()
        app.conf.wine_binary = "/w/bin/wine"
        app.conf.wine_dll_overrides = ""
        app.conf.wine64_binary = "/w/bin/wine"
        app.conf.wine_debug = "err+all"
        app.conf.wine_prefix = "/p"
        app.conf.wineserver_binary = "/w/bin/wineserver"
        env = wine.get_wine_env(app)
        self.assertNotIn("mscoree", env["WINEDLLOVERRIDES"])
        self.assertIn("mscoree=", wine.get_wine_env(app, wine.NO_MONO_GECKO)["WINEDLLOVERRIDES"])


class TestLicenceBeforeInstall(unittest.TestCase):
    def test_refusing_the_licence_stops_the_install(self):
        from ou_dedetai import wine
        app = mock.Mock()
        app.conf._overrides.agreed_to_faithlife_terms = False
        app.conf.faithlife_product = "Logos"
        app.agree_to_licence.return_value = False
        app.exit.side_effect = SystemExit
        with mock.patch.object(wine, "msi_licence_text", return_value="EULA text"), \
                mock.patch.object(wine, "run_wine_during_install") as run:
            with self.assertRaises(SystemExit):
                wine.install_msi(app)
        app.agree_to_licence.assert_called_once_with("Logos", "EULA text")
        run.assert_not_called()


class TestRegistryRetry(unittest.TestCase):
    def test_reg_is_retried_once(self):
        from ou_dedetai import wine
        fail = subprocess.CalledProcessError(5, "reg add")
        with mock.patch.object(wine, "_run_wine_during_install_once", side_effect=[fail, "ok"]) as run:
            self.assertEqual(wine.run_wine_during_install(mock.Mock(), "/w", exe="reg", exe_args=["add"]), "ok")
        self.assertEqual(run.call_count, 2)

    def test_other_programs_are_not_retried(self):
        from ou_dedetai import wine
        fail = subprocess.CalledProcessError(1, "msiexec")
        with mock.patch.object(wine, "_run_wine_during_install_once", side_effect=fail) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                wine.run_wine_during_install(mock.Mock(), "/w", exe="msiexec", exe_args=["/i"])
        self.assertEqual(run.call_count, 1)


class TestReuseUnpackedWine(unittest.TestCase):
    """#579: choosing (or updating to) a build that's already unpacked doesn't download it again."""
    def _app(self, root: str):
        app = mock.Mock()
        app.conf.wine_binary = constants.WINE_RECOMMENDED_TARBALL_SIGIL
        app.conf.wine_download_file_name = "wine-11.22-oinos-pre-b1e3dff-x86_64.tar.xz"
        app.conf.wine_distribution_dir = root
        app.conf.wine_prefix = root  # no system.reg: nothing to update
        return app

    def test_unpacked_build_is_used_without_downloading(self):
        with tempfile.TemporaryDirectory() as root:
            bindir = Path(root) / "wine-11.22-oinos-pre-b1e3dff-x86_64" / "bin"
            bindir.mkdir(parents=True)
            for name in ("wine", "wineserver"):
                (bindir / name).touch()
            app = self._app(root)
            with mock.patch("ou_dedetai.installer.download_wine") as download, \
                    mock.patch("ou_dedetai.installer.create_wine_symlinks"):
                wine.setup_wine(app)
            download.assert_not_called()
            self.assertEqual(app.conf.wine_binary, str((bindir / "wine").absolute()))

    def test_missing_build_is_downloaded(self):
        with tempfile.TemporaryDirectory() as root:
            app = self._app(root)
            with mock.patch("ou_dedetai.installer.download_wine", return_value=None) as download, \
                    mock.patch("ou_dedetai.installer.create_wine_symlinks"):
                wine.setup_wine(app)
            download.assert_called_once()
