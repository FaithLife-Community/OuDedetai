#!/usr/bin/env python3
import logging
import logging.handlers
import os
import sys
import threading
from pathlib import Path
from typing import Callable, Tuple

from . import cli, database_faithlife_notes, database_faithlife_catalog
from . import database
from . import constants
from . import gui_app
from . import markdown
from . import msg
from . import system
from . import tui_app
from . import utils
from .app import UserExitedFromAsk
from .cli_parser import get_parser, od_parse_args
from .config import EphemeralConfiguration, PersistentConfiguration, get_wine_prefix_path
from .repair import detect_and_recover


# Begin Program Actions
def run_control_panel(ephemeral_config: EphemeralConfiguration):
    dialog = ephemeral_config.dialog or system.get_dialog()
    logging.info(f"Using DIALOG: {dialog}")
    if dialog == 'tk':
        gui_app.start_gui_app(ephemeral_config)
    else:
        try:
            tui_app.control_panel_app(ephemeral_config)
        except KeyboardInterrupt:
            raise
        except SystemExit:
            logging.info("Caught SystemExit, exiting gracefully…")
            raise
        except Exception as e:
            logging.error(f"An error occurred in run_control_panel(): {e}")
            raise e


def install_app(ephemeral_config: EphemeralConfiguration):
    dialog = ephemeral_config.dialog or system.get_dialog()
    logging.info(f"Using DIALOG: {dialog}")
    if dialog == 'tk':
        gui_app.start_gui_app(ephemeral_config, install_only=True)
    else:
        cli.CLI(ephemeral_config).install_app()


def database_list_operation(ephemeral_config: EphemeralConfiguration):
    for database in utils.get_logos_databases(ephemeral_config):
        print(database)


def database_notes_dump_operation(ephemeral_config: EphemeralConfiguration, limit: int):
    paths = utils.get_logos_paths(ephemeral_config)
    with database_faithlife_notes.NotesDatabase(paths.appdata, paths.user_id) as db:
        for note in db.sample("Notes", limit):
            print(dict(note))
            print()


def database_notes_get_operation(ephemeral_config: EphemeralConfiguration, note_id):
    paths = utils.get_logos_paths(ephemeral_config)
    with database_faithlife_notes.NotesDatabase(paths.appdata, paths.user_id) as db:
        note = db.get_note(note_id)
    print(note)


def database_notes_render_operation(ephemeral_config: EphemeralConfiguration, note_id):
    paths = utils.get_logos_paths(ephemeral_config)
    with (
        database_faithlife_notes.NotesDatabase(paths.appdata, paths.user_id) as notes_db,
        database_faithlife_catalog.LibraryCatalogDatabase(paths.appdata, paths.user_id) as catalog_db
    ):
        note = notes_db.get_note(note_id)
        resolver = database_faithlife_notes.NoteResourceResolver(notes_db, catalog_db)
        exporter = markdown.MarkdownNoteExporter(resolver)
        print(exporter.export_note(note))


def database_notes_search_operation(
    ephemeral_config: EphemeralConfiguration,
    query: str,
    limit: int
):
    paths = utils.get_logos_paths(ephemeral_config)
    with database_faithlife_notes.NotesDatabase(paths.appdata, paths.user_id) as db:
        notes = db.search_notes(
            query,
            limit,
        )
        if not notes:
            print("No notes found.")
            return
        for note in notes:
            notebook = (
                note.Notebook.Title
                if note.Notebook is not None
                else ""
            )

            content = (
                    note.FoldedContent
                    or note.ContentRichText
                    or ""
            ).strip()
            if notebook:
                print(f"{note.NoteId}: [{notebook}] {content}")
            else:
                print(f"{note.NoteId}: {content}")


def _print_calculating() -> Callable[[], None]:
    stop_event = threading.Event()
    def update() -> None:
        dots = 0
        print("\033[?25l", end="", flush=True)
        try:
            while not stop_event.is_set():
                dots = (dots % 5) + 1
                message = f"\rCalculating{"." * dots}"
                print(f"\r{message:<20}", end="", flush=True)
                stop_event.wait(0.4)
        finally:
            print("\r\033[K\033[?25h", end="", flush=True)

    thread = threading.Thread(
        target=update,
        daemon=True
    )
    thread.start()
    def stop() -> None:
        if stop_event.is_set():
            return
        stop_event.set()
        thread.join()
        print("\033[?25h", end="", flush=True)
    return stop


def _print_export_progress(current: int, total: int) -> None:
    width = 40
    completed = int(width * current / total) if total else width
    remaining = width - completed
    bar = "#" * completed + "-" * remaining
    percent = current / total * 100 if total else 100
    print(
        f"\rExporting notes: [{bar}] {current}/{total} "
        f"({percent:5.1f}%)",
        end="",
        flush=True,
    )

    if current >= total:
        print()


def database_notes_export_operation(ephemeral_config: EphemeralConfiguration, export_dir):
    persistent_config = PersistentConfiguration.load_from_path(ephemeral_config.config_path)
    if export_dir is not None:
        output_directory = Path(export_dir)
    else:
        if persistent_config.install_dir is None:
            raise RuntimeError("No Logos installation found")
        output_directory = Path(persistent_config.install_dir) / "export"
    output_directory = output_directory.absolute()
    paths = utils.get_logos_paths(ephemeral_config)
    with (
        database_faithlife_notes.NotesDatabase(paths.appdata, paths.user_id) as notes_db,
        database_faithlife_catalog.LibraryCatalogDatabase(
            paths.appdata,
            paths.user_id,
        ) as catalog_db,
    ):
        notes = notes_db.notes()
        resolver = database_faithlife_notes.NoteResourceResolver(
            notes_db,
            catalog_db,
        )
        exporter = markdown.MarkdownNoteExporter(resolver)
        calculating_stop = _print_calculating()
        def export_status(status: str) -> None:
            if status == "ready":
                calculating_stop()
        try:
            exported_paths = exporter.export_all(
                notes,
                output_directory,
                progress_callback=_print_export_progress,
                status_callback=export_status
            )
        finally:
            calculating_stop()
    print(f"Exported {len(exported_paths)} files to:")
    print(output_directory)
# End Program Actions

def parse_database_command(args):
    if args.database_command == "list":
        return database_list_operation

    if args.database_command == "notes":
        if args.notes_command == "dump":
            def database_notes_dump_action(config):
                return database_notes_dump_operation(config, args.limit)
            database_notes_dump_action.__name__ = "database_notes_dump_operation"
            return database_notes_dump_action
        if args.notes_command == "get":
            def database_notes_get_action(config):
                return database_notes_get_operation(config, args.note_id)
            database_notes_get_action.__name__ = "database_notes_get_operation"
            return database_notes_get_action
        if args.notes_command == "export":
            def database_notes_export_action(config):
                return database_notes_export_operation(config, args.export_dir)
            database_notes_export_action.__name__ = "database_notes_export_operation"
            return database_notes_export_action
        if args.notes_command == "search":
            def database_notes_search_action(config):
                return database_notes_search_operation(config, args.query, args.limit)
            return database_notes_search_action

    raise RuntimeError(
        f"Unknown database command: {args.database_command}"
    )


def setup_config() -> Tuple[EphemeralConfiguration, Callable[[EphemeralConfiguration], None]]:
    parser = get_parser()
    args = parser.parse_args()

    # Get config based on env and configuration file temporarily just to load a couple
    # values out. We'll load this fully later.
    temp = EphemeralConfiguration.load()
    log_level = temp.log_level or constants.DEFAULT_LOG_LEVEL
    app_log_path = temp.app_log_path or constants.DEFAULT_APP_LOG_PATH
    del temp

    # Set runtime config.
    # Update log configuration.
    msg.update_log_level(log_level)
    msg.update_log_path(app_log_path)
    # test = logging.getLogger().handlers

    # Parse CLI args and update affected config vars.
    return od_parse_args(args, parser)


def is_app_installed(ephemeral_config: EphemeralConfiguration):
    persistent_config = PersistentConfiguration.load_from_path(ephemeral_config.config_path)
    if persistent_config.faithlife_product is None or persistent_config.install_dir is None:
        # Not enough information stored to find the product
        return False
    wine_prefix = ephemeral_config.wine_prefix or get_wine_prefix_path(str(persistent_config.install_dir))
    return utils.find_installed_product(persistent_config.faithlife_product, wine_prefix)


def run(ephemeral_config: EphemeralConfiguration, action: Callable[[EphemeralConfiguration], None]):
    # Attempt to repair installation if it is broken.
    # Must be done before calling the action to avoid errosly thinking the app isn't
    # installed when it's broken
    detect_and_recover(ephemeral_config)
    # Run desired action (requested function, defaults to control_panel)
    if action == "disabled":
        print("That option is disabled.", file=sys.stderr)
        sys.exit(1)
    if action.__name__ == "database_operation":
        action(ephemeral_config)
        return
    if action.__name__ == 'run_control_panel':
        # if utils.app_is_installed():
        #     wine.set_logos_paths()
        action(ephemeral_config)  # run control_panel right away
        return

    # Proceeding with the CLI interface

    install_required = [
        'backup',
        'create_shortcuts',
        'install_icu',
        'remove_index_files',
        'remove_library_catalog',
        'restore',
        'run_indexing',
        'run_installed_app',
        'update_installed_app',
        'stop_installed_app',
        'set_appimage',
        'toggle_app_logging',
        'toggle_media_support',
    ]
    if action.__name__ not in install_required:
        logging.info(f"Running function: {action.__name__}")
        action(ephemeral_config)
    elif is_app_installed(ephemeral_config):  # install_required; checking for app
        # wine.set_logos_paths()
        # Run the desired Logos action.
        logging.info(f"Running function: {action.__name__}")
        action(ephemeral_config)
    else:  # install_required, but app not installed
        print("App is not installed, but required for this operation. Consider installing first.", file=sys.stderr)
        sys.exit(1)


def main():
    msg.initialize_logging()
    ephemeral_config, action = setup_config()
    system.check_architecture()

    # NOTE: DELETE_LOG is an outlier here. It's an action, but it's one that
    # can be run in conjunction with other actions, so it gets special
    # treatment here once config is set.
    app_log_path = ephemeral_config.app_log_path or constants.DEFAULT_APP_LOG_PATH
    if ephemeral_config.delete_log and os.path.isfile(app_log_path):
        # Write empty file.
        with open(app_log_path, 'w') as f:
            f.write('')

    # Run safety checks.
    # FIXME: Fix utils.die_if_running() for GUI; as it is, it breaks GUI
    # self-update when updating LLI as it asks for a confirmation in the CLI.
    # Disabled until it can be fixed. Avoid running multiple instances of the
    # program.
    # utils.die_if_running()
    if os.getuid() == 0 and not ephemeral_config.app_run_as_root_permitted:
        print("Running Wine/winetricks as root is highly discouraged. Use -f|--force-root if you must run as root. "
              "See https://wiki.winehq.org/FAQ#Should_I_run_Wine_as_root.3F", file=sys.stderr)
        sys.exit(1)

    # Print terminal banner
    logging.info(f"{constants.APP_NAME}, {constants.LLI_CURRENT_VERSION} by {constants.LLI_AUTHOR}.")

    try:
        run(ephemeral_config, action)
    except UserExitedFromAsk:
        # This isn't a critical failure, the user doesn't need a traceback,
        # they are the ones who told us to exit.
        pass


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
