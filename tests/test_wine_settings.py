import tempfile
import unittest
from pathlib import Path

from ou_dedetai import wine, wine_settings
from ou_dedetai.wine_settings import SettingsContext, State

USER_REG = r'''WINE REGISTRY Version 2
;; All keys relative to \\User\\S-1-5-21-0-0-0-1000

#arch=win64

[Control Panel\\Desktop] 1731000000
#time=1db0000000000
"FontSmoothing"="2"
"FontSmoothingType"=dword:00000001

[Software\\Microsoft\\.NETFramework\\Windows Presentation Foundation\\Printing] 1731000000
"DisableXPSOMPrinting"=dword:00000001

[Software\\Wine\\DllOverrides] 1731000000
"icu"="native"
"icuin"="native"
"icuuc"="native"
"winemenubuilder.exe"=""
"xpsprint"=""

[Software\\Wine\\Fonts\\Replacements] 1731000000
''' + "\n".join(
    f'"{family}"=str(7):"{chr(92)}0".join(subs)' for family, subs in wine.FONT_REPLACEMENTS.items()
) + "\n"


class TestWineSettings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.prefix = Path(self.tmp.name)
        (self.prefix / "user.reg").write_text(USER_REG)
        (self.prefix / "system.reg").write_text("WINE REGISTRY Version 2\n")

    def tearDown(self):
        self.tmp.cleanup()

    def by_id(self, reports):
        return {r.setting.id: r for r in reports}

    def test_parse_reg_file_unescapes_keys(self):
        parsed = wine.parse_reg_file(self.prefix / "user.reg")
        self.assertEqual(parsed["software\\wine\\dlloverrides"]["icu"], '"native"')

    def test_applied_settings(self):
        reports = self.by_id(wine_settings.report(self.prefix, SettingsContext(oinos=False)))
        for setting_id in ("printing", "icu", "font-replacements", "no-wine-menus", "xpsprint-off"):
            self.assertEqual(reports[setting_id].state, State.APPLIED, setting_id)

    def test_different_value_is_reported(self):
        reports = self.by_id(wine_settings.report(self.prefix, SettingsContext(oinos=False)))
        smoothing = reports["font-smoothing"]
        self.assertEqual(smoothing.state, State.DIFFERENT)
        self.assertIn("dword:00000001", smoothing.details[0])

    def test_missing_setting(self):
        reports = self.by_id(wine_settings.report(self.prefix, SettingsContext(oinos=True)))
        self.assertEqual(reports["logos-self-update"].state, State.MISSING)
        self.assertTrue(reports["logos-self-update"].needed)

    def test_needed_depends_on_wine_build(self):
        stock = self.by_id(wine_settings.report(self.prefix, SettingsContext(oinos=False)))
        oinos = self.by_id(wine_settings.report(self.prefix, SettingsContext(oinos=True)))
        self.assertFalse(stock["logos-self-update"].needed)
        self.assertTrue(stock["xpsprint-off"].needed)
        self.assertFalse(oinos["xpsprint-off"].needed)

    def test_no_prefix_is_unknown(self):
        reports = wine_settings.report(self.prefix / "missing", SettingsContext(oinos=False))
        self.assertTrue(all(r.state == State.UNKNOWN for r in reports))

    def test_format_report_lists_every_setting(self):
        text = wine_settings.format_report(
            wine_settings.report(self.prefix, SettingsContext(oinos=False)), "dxvk"
        )
        for setting in wine_settings.SETTINGS:
            self.assertIn(setting.title, text)
        self.assertIn("Renderer: dxvk", text)


if __name__ == "__main__":
    unittest.main()
