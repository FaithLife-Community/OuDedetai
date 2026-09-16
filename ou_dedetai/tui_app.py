from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Optional

from textual import on
from textual.app import App as TextualApp, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.widgets import (Button, Footer, Input, Label, Log, OptionList, Static)
from textual.widgets.option_list import Option

from ou_dedetai.app import App as DomainApp, UserExitedFromAsk
from ou_dedetai.config import EphemeralConfiguration

from . import control
from . import constants
from . import installer
from . import logos
from . import system
from . import utils
from . import wine


WINDOWS_VERSIONS = ["vista", "win7", "win8", "win10", "win11", "Return to Main Menu"]


class MenuModal(ModalScreen[str]):
    BINDINGS = [Binding("escape", "cancel", "Cancel", show=True)]

    def __init__(self, title: str, options: list[str]) -> None:
        super().__init__()
        self._title = title
        self._options = options

    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Label(self._title, id="dialog-title")
            yield OptionList(
                *[Option(opt, id=f"opt-{i}") for i, opt in enumerate(self._options)],
                id="menu-list",
            )
            with Horizontal(id="dialog-buttons"):
                yield Button("Cancel", variant="default", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#menu-list", OptionList).focus()

    @on(OptionList.OptionSelected)
    def on_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(str(event.option.prompt))

    @on(Button.Pressed, "#cancel")
    def action_cancel(self) -> None:
        self.dismiss("Return to Main Menu")


class InfoModal(ModalScreen[None]):
    def __init__(self, message: str, title: str = "Information") -> None:
        super().__init__()
        self.message = message
        self.dialog_title = title

    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Label(self.dialog_title, id="dialog-title")
            yield Static(self.message, id="dialog-body")
            yield Button("OK", variant="primary", id="ok")

    @on(Button.Pressed, "#ok")
    def ok(self) -> None:
        self.dismiss()


class InputModal(ModalScreen[str]):
    def __init__(self, question: str, default: str = "") -> None:
        super().__init__()
        self.question = question
        self.default = default

    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Label(self.question, id="dialog-title")
            yield Input(value=self.default, id="input-field")
            with Horizontal(id="dialog-buttons"):
                yield Button("OK", variant="primary", id="ok")
                yield Button("Cancel", variant="default", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#input-field", Input).focus()

    @on(Button.Pressed, "#ok")
    def ok(self) -> None:
        self.dismiss(self.query_one("#input-field", Input).value)

    @on(Button.Pressed, "#cancel")
    def cancel(self) -> None:
        self.dismiss("")

    @on(Input.Submitted)
    def on_submit(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)


class TextualUI(TextualApp[None]):
    THEMES = {
        "logos": Theme(
            name="logos",
            primary="#00AEEF",
            secondary="#666666",
            accent="#FFFFFF",
            background="#101010",
            surface="#181818",
            panel="#202020",
            foreground="#F0F0F0",
            dark=True,
        ),
        #TODO: Needs tweaking
        "system-dark": Theme(
            name="system-dark",
            primary="#5FA8D3",
            secondary="#7F8C8D",
            accent="#FFFFFF",
            warning="#F2C14E",
            error="#E06C75",
            success="#98C379",
            foreground="#E6E6E6",
            background="#121212",
            surface="#1E1E1E",
            panel="#252525",
            dark=True,
        ),
        #TODO: Needs tweaking
        "system-light": Theme(
            name="system-light",
            primary="#005A9C",
            secondary="#5F6368",
            accent="#000000",
            warning="#8A5700",
            error="#B3261E",
            success="#137333",
            foreground="#202124",
            background="#FFFFFF",
            surface="#F5F5F5",
            panel="#E8E8E8",
            dark=False,
        )
    }
    #TODO: Needs tweaking
    CSS = """
    Screen {
        layout: vertical;
        background: $background;
        color: $text;
    }

    #header-area {
        dock: top;
        height: auto;
        background: $surface;
        border-bottom: solid $primary;
        padding: 0 1;
    }

    #title { text-style: bold; }
    #subtitle { color: $text-muted; }

    #console-area {
        height: 9;
        border: solid $primary;
        background: $surface;
        padding: 0 1;
    }

    #main-area { height: 1fr; }

    #menu-title {
        text-style: bold;
        padding: 1 2;
        background: $primary;
        color: $text;
    }

    #main-menu {
        height: 1fr;
        padding: 0 1;
    }

    #dialog {
        width: 70;
        max-width: 90%;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    #dialog-title {
        text-style: bold;
        margin-bottom: 1;
    }

    #dialog-body { margin-bottom: 1; }

    #dialog-buttons {
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    #dialog-buttons Button {
        margin: 0 1;
        min-width: 12;
    }

    #status-bar {
        dock: bottom;
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]

    title_text: reactive[str] = reactive("")
    subtitle_text: reactive[str] = reactive("")

    def __init__(self, domain: "TUI") -> None:
        super().__init__()
        self.domain = domain
        self.register_theme(self.THEMES["logos"])
        self.register_theme(self.THEMES["system-dark"])
        self.register_theme(self.THEMES["system-light"])
        self.theme = "logos"

    def compose(self) -> ComposeResult:
        with Vertical(id="header-area"):
            yield Static(id="title")
            yield Static(id="subtitle")
        with Vertical(id="main-area"):
            yield Static("Main Menu", id="menu-title")
            yield OptionList(id="main-menu")
        yield Log(id="console-area", max_lines=300, highlight=True)
        yield Footer()
        yield Static("FaithLife Community", id="status-bar")

    def on_mount(self) -> None:
        self.title = constants.APP_NAME
        self.sub_title = getattr(constants, "LLI_CURRENT_VERSION", "")
        self.domain.set_title()
        self._populate_main_menu()
        self.query_one("#main-menu", OptionList).focus()
        self.set_interval(2.5, self._monitor_tick)
        self.domain.status("TUI ready")

    def _monitor_tick(self) -> None:
        try:
            if self.domain.logos:
                self.domain.logos.monitor()
                self._populate_main_menu()
        except Exception as exc:
            logging.debug("monitor tick failed: %s", exc)

    def _refresh_header(self) -> None:
        try:
            self.query_one("#title", Static).update(self.title_text)
            self.query_one("#subtitle", Static).update(self.subtitle_text)
        except Exception:
            pass

    def watch_title_text(self, value: str) -> None:
        self._refresh_header()

    def watch_subtitle_text(self, value: str) -> None:
        self._refresh_header()

    def _populate_main_menu(self) -> None:
        menu = self.query_one("#main-menu", OptionList)
        options = [str(label) for label in self.domain.set_tui_menu_options()]
        current_options = [str(option.prompt) for option in menu.options]
        if options == current_options:
            return
        current = menu.highlighted
        menu.clear_options()
        for i, label in enumerate(options):
            menu.add_option(Option(label, id=f"main-{i}"))
        if current is not None and options:
            menu.highlighted = min(current, len(options) - 1)

    @on(OptionList.OptionSelected, "#main-menu")
    def on_main_menu(self, event: OptionList.OptionSelected) -> None:
        self.domain.main_menu_select(str(event.option.prompt))

    def action_refresh(self) -> None:
        self._populate_main_menu()
        self.domain.set_title()

    def action_quit(self) -> None:
        self.domain.is_running = False
        self.exit()

    def write_status(self, message: str) -> None:
        try:
            self.query_one("#console-area", Log).write_line(message)
        except Exception:
            pass

    def go_to_main_menu(self) -> None:
        while len(self.screen_stack) > 1:
            self.pop_screen()
        self._populate_main_menu()
        self.domain.set_title()
        try:
            self.query_one("#main-menu", OptionList).focus()
        except Exception:
            pass

    def _system_theme(self) -> str:
        colorfgbg = os.environ.get("COLORFGBG", "")
        try:
            background = int(colorfgbg.rsplit(";", 1)[-1])
        except ValueError:
            return "system-dark"
        return "system-light" if background >= 7 else "system-dark"

    def toggle_color_scheme(self) -> str:
        if self.theme == "logos":
            self.theme = self._system_theme()
        else:
            self.theme = "logos"
        return self.theme


class TUI(DomainApp):
    def __init__(self, ephemeral_config: EphemeralConfiguration) -> None:
        super().__init__(ephemeral_config)
        self.is_running = True
        self._installer_thread: Optional[threading.Thread] = None
        self.console_log: list[str] = []
        self.tmp = ""
        self.ui = TextualUI(self)
        self.config_updated_hooks.append(self._config_update_hook)

    def _ask(self, question: str, options: list[str] | str) -> Optional[str]:
        result: list[Optional[str]] = [None]
        event = threading.Event()

        def _done(choice: str | None) -> None:
            result[0] = choice
            event.set()

        if isinstance(options, str):
            self.ui.call_from_thread(self.ui.push_screen, InputModal(question, default=str(Path.home())), _done)
        else:
            self.ui.call_from_thread(self.ui.push_screen, MenuModal(question, list(options)
                                                                    + ["Return to Main Menu"]), _done)

        event.wait()

        answer = result[0]
        if answer == "Return to Main Menu":
            self.ui.call_from_thread(self.ui.go_to_main_menu)
            return None
        return answer

    def _info(self, message: str) -> None:
        event = threading.Event()

        def _done(_: None) -> None:
            event.set()

        self.ui.call_from_thread(self.ui.push_screen, InfoModal(message), _done)
        event.wait()

    def _ui_call(self, callback, *args) -> None:
        if threading.get_ident() == self.ui._thread_id:
            callback(*args)
        else:
            self.ui.call_from_thread(callback, *args)

    def _status(self, message: str, percent: Optional[int] = None) -> None:
        message = message.strip()
        if self.console_log and self.console_log[-1] == message:
            return
        self.console_log.append(message)
        try:
            self._ui_call(self.ui.write_status, message)
        except Exception:
            pass

    def _pop_up(self, title: str, message: str) -> None:
        self.console_log.append(message)
        try:
            self.ui.call_from_thread(self.ui.push_screen, InfoModal(message, title=title))
        except Exception:
            pass

    def _exit(self, reason: str, intended: bool = False) -> None:
        msg = f"Exiting {constants.APP_NAME} due to {reason}…"
        if not intended and hasattr(constants, "SUPPORT_MESSAGE"):
            msg += "\n" + constants.SUPPORT_MESSAGE
        self._status(msg)
        try:
            self.ui.exit()
        except Exception:
            pass

    def set_title(self) -> None:
        version = getattr(constants, "LLI_CURRENT_VERSION", "")
        channel = getattr(self.conf, "app_release_channel", "")
        self.ui.title_text = f"Welcome to {constants.APP_NAME} {version} ({channel})"

        product = (getattr(self.conf._raw, "faithlife_product", None) or constants.FAITHLIFE_PRODUCTS[0])
        if self.is_installed():
            rel = getattr(self.conf, "installed_faithlife_product_release", "?")
            ch = getattr(self.conf, "faithlife_product_release_channel", "")
            self.ui.subtitle_text = f"{product} Version: {rel} ({ch})"
        else:
            self.ui.subtitle_text = f"{product} not installed"

    def go_to_main_menu(self) -> None:
        self.ui.go_to_main_menu()

    def _config_update_hook(self) -> None:
        try:
            self._ui_call(self.ui.action_refresh)
        except Exception:
            pass

    def set_tui_menu_options(self) -> list[str]:
        labels: list[str] = []

        if getattr(constants, "RUNMODE", "") == "binary":
            try:
                status = utils.compare_logos_linux_installer_version(self)
                if status == utils.VersionComparison.OUT_OF_DATE:
                    labels.append(f"Update {constants.APP_NAME}")
            except Exception:
                pass

        if self.is_installed():
            product = self.conf.faithlife_product
            if self.logos.logos_state in (logos.State.STARTING, logos.State.RUNNING):
                labels.append(f"Stop {product}")
            else:
                labels.append(f"Run {product}")

            if self.logos.indexing_state == logos.State.RUNNING:
                labels.append("Stop Indexing")
            else:
                labels.append("Run Indexing")

            if not getattr(self.conf, "is_installed_faithlife_product_release_latest", True):
                labels.append(f"Update {product}")
        else:
            labels.extend(["Install", "Advanced Install"])

        labels.extend(["Utilities →", "Wine Config →", "Change Color Scheme", "Get Support", "Exit"])
        return labels

    def _get_support(self) -> None:
        try:
            control.get_support(self)
        except Exception as exc:
            self._pop_up(str(exc), "Error")
        finally:
            self._ui_call(self.ui.go_to_main_menu)

    def main_menu_select(self, choice: str) -> None:
        original_assume_yes = getattr(self.conf._overrides, "assume_yes", False)

        def _install() -> None:
            try:
                installer.install(app=self)
            except UserExitedFromAsk:
                pass
            finally:
                self.conf._overrides.assume_yes = original_assume_yes
                self.go_to_main_menu()

        if choice in (None, "Exit"):
            self.is_running = False
            self.ui.exit()
            return

        if choice in ("Install", "Advanced Install"):
            if self._installer_thread and self._installer_thread.is_alive():
                self.status("A previous install is still running")
                return
            if choice == "Install":
                self.conf._overrides.assume_yes = True
            self._installer_thread = threading.Thread(target=_install, daemon=True)
            self._installer_thread.start()
            self.status("Starting installation…")

        elif choice.startswith(f"Update {constants.APP_NAME}"):
            utils.update_to_latest_lli_release(self)

        elif self.conf._raw.faithlife_product and choice == f"Update {self.conf.faithlife_product}":
            def _update() -> None:
                utils.update_faithlife_product(self)
                self.go_to_main_menu()
            threading.Thread(target=_update, daemon=True).start()

        elif self.conf._raw.faithlife_product and choice == f"Run {self.conf._raw.faithlife_product}":
            self.logos.start()
            self.ui._populate_main_menu()

        elif self.conf._raw.faithlife_product and choice == f"Stop {self.conf.faithlife_product}":
            self.logos.stop()
            self.ui._populate_main_menu()

        elif choice == "Run Indexing":
            self.logos.index()

        elif choice == "Remove Library Catalog":
            control.remove_library_catalog(self)

        elif choice.startswith("Wine Config"):
            self.ui.push_screen(
                MenuModal("Wine Config Menu", self.set_wineconfig_menu_options()),
                callback=self.wineconfig_menu_select)

        elif choice.startswith("Utilities"):
            self.ui.push_screen(
                MenuModal("Utilities Menu", self.set_utilities_menu_options()),
                callback=self.utilities_menu_select)

        elif choice == "Change Color Scheme":
            theme = self.ui.toggle_color_scheme()
            scheme = "Logos Colors" if theme == "logos" else "System Colors"
            self.status(f"Color scheme: {scheme}")

        elif choice == "Get Support":
            self.start_thread(self._get_support)

    def wineconfig_menu_select(self, choice: str | None) -> None:
        if not choice or choice == "Return to Main Menu":
            self.go_to_main_menu()
            return
        if choice == "Set Renderer":
            self.ui.push_screen(
                MenuModal("Choose Renderer", ["gdi", "gl", "dxvk", "vulkan", "Return to Main Menu"]),
                callback=self.renderer_select)
        elif choice == "Set Windows Version for Logos":
            self.ui.push_screen(MenuModal("Windows Version for Logos", WINDOWS_VERSIONS),
                                callback=self.win_ver_logos_select)
        elif choice == "Set Windows Version for Indexer":
            self.ui.push_screen(MenuModal("Windows Version for Indexer", WINDOWS_VERSIONS),
                                callback=self.win_ver_index_select)

    def utilities_menu_select(self, choice: str | None) -> None:
        if not choice or choice == "Return to Main Menu":
            self.go_to_main_menu()
            return
        try:
            if choice == "Remove Library Catalog":
                control.remove_library_catalog(self)
            elif choice == "Remove All Index Files":
                control.remove_all_index_files(self)
            elif choice == "Edit Config":
                control.edit_file(self.conf.config_file_path)
            elif choice == "Reload Config":
                self.conf.reload()
            elif choice == "Change Logos Release Channel":
                self.conf.toggle_faithlife_product_release_channel()
            elif choice == f"Change {constants.APP_NAME} Release Channel":
                self.conf.toggle_installer_release_channel()
            elif choice == "Install Dependencies":
                utils.install_dependencies(self)
            elif choice == "Install ICU":
                wine.enforce_icu_data_files(self)
            elif choice.endswith("Logging"):
                self.logos.switch_logging()
            elif choice == "Check OpenGL":
                _, reason = system.check_opengl_version(self)
                self.status(reason)
            elif choice == "Uninstall":
                control.uninstall(self)
            elif choice == "Update to Latest AppImage":
                utils.update_to_latest_recommended_appimage(self)
        except UserExitedFromAsk:
            pass
        self.go_to_main_menu()

    def renderer_select(self, choice: str | None) -> None:
        if choice in ("gdi", "gl", "dxvk", "vulkan"):
            self.status(f"Changing renderer to {choice}…")
            wine.set_renderer(self, self.conf.wine64_binary, choice)
            self.status(f"Renderer set to {choice}")
        self.go_to_main_menu()

    def win_ver_logos_select(self, choice: str | None) -> None:
        if choice in ("vista", "win7", "win8", "win10", "win11"):
            self.status(f"Setting Logos Windows version to {choice}…")
            wine.set_win_version(self, "logos", choice)
            self.status(f"Logos Windows version set to {choice}")
        self.go_to_main_menu()

    def win_ver_index_select(self, choice: str | None) -> None:
        if choice in ("vista", "win7", "win8", "win10", "win11"):
            self.status(f"Setting Indexer Windows version to {choice}…")
            wine.set_win_version(self, "indexer", choice)
            self.status(f"Indexer Windows version set to {choice}")
        self.go_to_main_menu()

    def set_wineconfig_menu_options(self) -> list[str]:
        return [
            "Set Renderer",
            "Set Windows Version for Logos",
            "Set Windows Version for Indexer",
            "Return to Main Menu",
        ]

    def set_utilities_menu_options(self) -> list[str]:
        labels: list[str] = []
        if self.is_installed():
            labels.extend(["Remove Library Catalog", "Remove All Index Files", "Install ICU"])
        if (
            self.is_installed()
            or Path(self.conf.config_file_path).exists()
            or (getattr(self.conf._raw, "install_dir", None) and Path(self.conf._raw.install_dir).exists())
        ):
            labels.append("Uninstall")
        labels.extend(["Install Dependencies", "Edit Config", "Reload Config"])
        if self.is_installed():
            labels.extend([
                "Change Logos Release Channel",
                f"Change {constants.APP_NAME} Release Channel",
            ])
        labels.append(
            "Enable Logging" if getattr(self.conf, "faithlife_product_logging", False)
            else "Disable Logging"
        )
        labels.append("Check OpenGL")
        labels.append("Return to Main Menu")
        return labels


def control_panel_app(ephemeral_config: EphemeralConfiguration) -> None:
    tui = TUI(ephemeral_config)
    try:
        tui.ui.run()
    finally:
        print()
