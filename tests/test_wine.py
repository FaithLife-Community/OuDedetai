import unittest
from unittest import mock

from ou_dedetai import wine


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
        args = run.call_args.kwargs["exe_args"]
        self.assertEqual(run.call_args.kwargs["exe"], "reg")
        self.assertEqual(args[1], "HKCU\\Software\\Wine\\MSI")
        self.assertEqual(args[args.index("/v") + 1], "IgnoreFailedActions")
        self.assertEqual(args[args.index("/t") + 1], "REG_MULTI_SZ")
        self.assertEqual(args[args.index("/d") + 1], "RegisterStubMsixPackage")


if __name__ == "__main__":
    unittest.main()
