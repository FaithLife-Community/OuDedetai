"""The window's translations (ou_dedetai/i18n/*.ts) must keep each string's placeholders:
a translation missing "{product}" (or adding one) makes .format() fail when it's shown."""
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

I18N = Path(__file__).resolve().parent.parent / "ou_dedetai" / "i18n"
PLACEHOLDER = re.compile(r"\{\w+\}")


class TestTranslations(unittest.TestCase):
    def test_every_language_keeps_the_placeholders_and_line_breaks(self):
        files = sorted(I18N.glob("oudedetai_*.ts"))
        self.assertTrue(files)
        for path in files:
            for message in ET.parse(path).getroot().iter("message"):
                source = message.findtext("source") or ""
                translation = message.find("translation")
                if translation is None or translation.get("type") == "unfinished" or not translation.text:
                    continue
                with self.subTest(language=path.stem, source=source[:40]):
                    self.assertEqual(sorted(PLACEHOLDER.findall(source)), sorted(PLACEHOLDER.findall(translation.text)))
                    self.assertEqual(source.count("\n"), translation.text.count("\n"))

    def test_each_translation_is_compiled(self):
        for path in I18N.glob("oudedetai_*.ts"):
            with self.subTest(language=path.stem):
                compiled = path.with_suffix(".qm")
                self.assertTrue(compiled.is_file(), f"run scripts/update-translations.py for {path.name}")
                self.assertGreaterEqual(compiled.stat().st_mtime, path.stat().st_mtime - 5)


if __name__ == "__main__":
    unittest.main()
