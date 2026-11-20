#!/usr/bin/env python3
"""Refresh the GUI's Qt Linguist files and compile them.

Collects every tr("…") string in ou_dedetai/gui_main.py, gui_app.py and gui.py and the titles/reasons in
ou_dedetai/wine_settings.py, adds new ones to each ou_dedetai/i18n/oudedetai_<lang>.ts
(keeping existing translations, marking new ones unfinished), then runs
pyside6-lrelease to make the .qm files the app loads.

    python scripts/update-translations.py          # all languages
    python scripts/update-translations.py es fr    # add/refresh these
"""
import ast
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "ou_dedetai"
I18N = PKG / "i18n"
CONTEXT = "OuDedetai"


def gui_strings() -> list[str]:
    found: list[str] = []

    def add(text):
        if isinstance(text, str) and text and text not in found:
            found.append(text)

    calls = [node for name in ("gui_main.py", "gui_app.py", "gui.py")
             for node in ast.walk(ast.parse((PKG / name).read_text()))]
    for node in calls:
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "tr" and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Constant):
                add(arg.value)
        # INSTALL_STEPS titles and details are passed to tr() at run time
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, ast.AnnAssign) else [])
        if any(getattr(t, "id", "") == "INSTALL_STEPS" for t in targets):
            for step in node.value.elts:
                for item in step.elts[1:]:
                    if isinstance(item, ast.Constant):
                        add(item.value)
    settings = ast.parse((PKG / "wine_settings.py").read_text())
    for node in ast.walk(settings):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "WineSetting":
            for kw in node.keywords:
                if kw.arg in ("title", "reason") and isinstance(kw.value, ast.Constant):
                    add(kw.value.value)
    return found


def update(lang: str, strings: list[str]) -> Path:
    path = I18N / f"oudedetai_{lang}.ts"
    existing: dict[str, str] = {}
    if path.exists():
        for msg in ET.parse(path).getroot().iter("message"):
            source = msg.findtext("source")
            translation = msg.find("translation")
            if source and translation is not None and translation.text and translation.get("type") != "unfinished":
                existing[source] = translation.text
    ts = ET.Element("TS", version="2.1", language=lang)
    ctx = ET.SubElement(ts, "context")
    ET.SubElement(ctx, "name").text = CONTEXT
    for text in strings:
        msg = ET.SubElement(ctx, "message")
        ET.SubElement(msg, "source").text = text
        tr = ET.SubElement(msg, "translation")
        if text in existing:
            tr.text = existing[text]
        else:
            tr.set("type", "unfinished")
    ET.indent(ts)
    path.write_text('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n'
                    + ET.tostring(ts, encoding="unicode") + "\n")
    return path


def main(argv: list[str]) -> int:
    I18N.mkdir(exist_ok=True)
    langs = argv or sorted(p.stem.split("_", 1)[1] for p in I18N.glob("oudedetai_*.ts"))
    strings = gui_strings()
    for lang in langs:
        path = update(lang, strings)
        subprocess.run(["pyside6-lrelease", str(path), "-qm", str(path.with_suffix(".qm"))], check=True)
        missing = sum(1 for m in ET.parse(path).getroot().iter("translation") if m.get("type") == "unfinished")
        print(f"{lang}: {len(strings)} strings, {missing} untranslated")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
