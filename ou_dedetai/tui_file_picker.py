"""Filesystem browsing using the TUI's existing dialog styles and widgets."""
from pathlib import Path

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, OptionList
from textual.widgets.option_list import Option


class FilePicker(ModalScreen[str | None]):
    BINDINGS = [
        Binding('escape', 'cancel', 'Cancel', priority=True),
        Binding('ctrl+c', 'exit', show=False, priority=True),
    ]
    DEFAULT_CSS = """
    FilePicker #dialog { height: 100%; }
    FilePicker #dialog-title, FilePicker #file-directory, FilePicker #file-error { height: 1; }
    FilePicker #file-list { height: 1fr; min-height: 1; }
    FilePicker #file-path { height: 3; }
    FilePicker #dialog-buttons { height: 3; }
    FilePicker Button { margin: 0 1; }
    """

    def __init__(self, title: str, directory: Path, appimages: bool = False):
        super().__init__()
        self.dialog_title = title
        self.directory = directory
        self.appimages = appimages
        self.paths: list[Path] = []

    def compose(self) -> ComposeResult:
        with Container(id='dialog'):
            yield Label(self.dialog_title, id='dialog-title', markup=False)
            yield Label('', id='file-directory', markup=False)
            yield OptionList(id='file-list')
            yield Label('', id='file-error', markup=False)
            yield Input(placeholder='Paste a path (optional)', id='file-path')
            with Horizontal(id='dialog-buttons'):
                yield Button(self.filter_label, id='file-filter')
                yield Button('Select', variant='primary', id='file-select')
                yield Button('Cancel', id='file-cancel')

    @property
    def filter_label(self) -> str:
        return 'AppImages only' if self.appimages else 'All files'

    def on_mount(self):
        self.show_directory(self.directory)
        self.query_one('#file-list', OptionList).focus()

    def show_directory(self, directory: Path):
        try:
            directory = directory.expanduser().absolute()
            entries = list(directory.iterdir())
            entries = sorted((p for p in entries if p.is_dir()), key=lambda p: p.name.casefold()) + sorted(
                (p for p in entries if p.is_file() and (not self.appimages or p.suffix.lower() == '.appimage')),
                key=lambda p: p.name.casefold())
        except OSError as error:
            self.query_one('#file-error', Label).update(str(error))
            return
        self.directory = directory
        self.paths = ([directory.parent] if directory.parent != directory else []) + entries
        menu = self.query_one('#file-list', OptionList)
        menu.clear_options()
        for index, path in enumerate(self.paths):
            name = '.. /' if path == directory.parent else path.name + ('/' if path.is_dir() else '')
            menu.add_option(Option(Text(name), id=f'file-{index}'))
        menu.highlighted = 0 if self.paths else None
        self.query_one('#file-directory', Label).update(str(directory))
        self.query_one('#file-error', Label).update('')
        self.query_one('#file-path', Input).value = ''

    def open_path(self, path: Path):
        path = path.expanduser()
        if not path.is_absolute():
            path = self.directory / path
        if path.is_dir():
            self.show_directory(path)
        elif not path.is_file():
            self.query_one('#file-error', Label).update('File not found. Choose a file or directory.')
        elif self.appimages and path.suffix.lower() != '.appimage':
            self.query_one('#file-error', Label).update('Switch to All files to choose a Wine executable.')
        else:
            self.dismiss(str(path.absolute()))

    @on(OptionList.OptionSelected, '#file-list')
    def selected(self, event: OptionList.OptionSelected):
        event.stop()
        self.open_path(self.paths[event.option_index])

    @on(Button.Pressed, '#file-select')
    def select(self):
        value = self.query_one('#file-path', Input).value.strip()
        index = self.query_one('#file-list', OptionList).highlighted
        if value:
            self.open_path(Path(value))
        elif index is not None:
            self.open_path(self.paths[index])

    @on(Input.Submitted, '#file-path')
    def submitted(self):
        self.select()

    @on(Button.Pressed, '#file-filter')
    def toggle_filter(self):
        self.appimages = not self.appimages
        self.query_one('#file-filter', Button).label = self.filter_label
        self.show_directory(self.directory)
        self.query_one('#file-list', OptionList).focus()

    def action_exit(self):
        # Same as every other TUI dialog: Ctrl+C quits the app.
        self.app.exit()

    @on(Button.Pressed, '#file-cancel')
    def action_cancel(self):
        self.dismiss(None)
