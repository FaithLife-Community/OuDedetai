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


if __name__ == "__main__":
    unittest.main()
