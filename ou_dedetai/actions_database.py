import threading
import unicodedata
from pathlib import Path
from typing import Callable

from ou_dedetai.config import EphemeralConfiguration, PersistentConfiguration, get_wine_prefix_path, get_wine_user, \
    get_logos_appdata_dir, get_logos_user_id
from ou_dedetai.database import NotesDatabase, DatabaseInspector, LibraryCatalogDatabase, NoteResourceResolver
from ou_dedetai.markdown import MarkdownNoteExporter
from ou_dedetai.paths import LogosPaths
from ou_dedetai.richtext import LogosRichTextRenderer, LogosRichTextParser, RichTextBlock


def get_logos_paths(
    ephemeral_config: EphemeralConfiguration,
) -> LogosPaths:
    persistent_config = PersistentConfiguration.load_from_path(ephemeral_config.config_path)
    if persistent_config.install_dir is None:
        raise RuntimeError("No Logos installation found")
    if persistent_config.faithlife_product is None:
        raise RuntimeError("No Logos product found")
    wine_prefix = (
        ephemeral_config.wine_prefix
        or get_wine_prefix_path(persistent_config.install_dir)
    )
    wine_user = get_wine_user(wine_prefix)
    if wine_user is None:
        raise RuntimeError("Unable to find Wine user")

    appdata = Path(get_logos_appdata_dir(wine_prefix, wine_user, persistent_config.faithlife_product))
    logos_user_id = get_logos_user_id(str(appdata))
    if logos_user_id is None:
        raise RuntimeError("Unable to find Logos user ID")

    return LogosPaths(
        appdata=appdata,
        data=appdata / "Data" / logos_user_id,
        documents=appdata / "Documents" / logos_user_id,
        user_id=logos_user_id
    )


def get_logos_databases(ephemeral_config: EphemeralConfiguration) -> list[Path]:
    return get_logos_paths(ephemeral_config).databases


def database_operation(ephemeral_config: EphemeralConfiguration):
    from .database import SQLiteDatabase, DatabaseInspector
    if ephemeral_config.database_path:
        databases = [Path(ephemeral_config.database_path)]
    else:
        databases = get_logos_databases(ephemeral_config)

    for database_path in databases:
        print(f"\n=== {database_path.name} ===")
        with SQLiteDatabase(database_path) as db:
            inspector = DatabaseInspector(db)
            inspector.print_summary()


def database_list_operation(ephemeral_config: EphemeralConfiguration):
    for database in get_logos_databases(ephemeral_config):
        print(database)


def database_dump_operation(ephemeral_config: EphemeralConfiguration):
    paths = get_logos_paths(ephemeral_config)
    with NotesDatabase(paths.appdata, paths.user_id) as db:
        for row in db.sample(
                ephemeral_config.database_table,
                ephemeral_config.database_limit,
        ):
            print(dict(row))
            print()


def database_notes_count_operation(ephemeral_config: EphemeralConfiguration):
    paths = get_logos_paths(ephemeral_config)
    with NotesDatabase(paths.appdata, paths.user_id) as db:
        counts = {
            "Notes": db.count("Notes"),
            "Notebooks": db.count("Notebooks"),
            "Tags": db.count("Tags"),
        }
    for name, count in counts.items():
        print(f"{name}: {count}")


def database_notes_info_operation(ephemeral_config: EphemeralConfiguration):
    paths = get_logos_paths(ephemeral_config)
    with NotesDatabase(paths.appdata, paths.user_id) as db:
        inspector = DatabaseInspector(db)
        inspector.print_summary()


def database_notes_tables_operation(ephemeral_config):
    paths = get_logos_paths(ephemeral_config)
    with NotesDatabase(paths.appdata, paths.user_id) as db:
        inspector = DatabaseInspector(db)
        for table in inspector.tables():
            print(table)


def database_notes_schema_operation(ephemeral_config):
    paths = get_logos_paths(ephemeral_config)
    with NotesDatabase(paths.appdata, paths.user_id) as db:
        inspector = DatabaseInspector(db)
        for column in inspector.schema(ephemeral_config.database_table):
            print(f"{column['name']}: {column['type']}")


def database_notes_get_operation(ephemeral_config: EphemeralConfiguration):
    paths = get_logos_paths(ephemeral_config)
    with NotesDatabase(paths.appdata, paths.user_id) as db:
        note = db.get_note(ephemeral_config.note_id)
    print(note)


def database_notes_render_operation(ephemeral_config: EphemeralConfiguration):
    paths = get_logos_paths(ephemeral_config)
    with (
        NotesDatabase(paths.appdata, paths.user_id) as notes_db,
        LibraryCatalogDatabase(paths.appdata, paths.user_id) as catalog_db
    ):
        note = notes_db.get_note(ephemeral_config.note_id)
        resolver = NoteResourceResolver(notes_db, catalog_db)
        exporter = MarkdownNoteExporter(resolver)
        print(exporter.export_note(note))


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


def database_notes_export_operation(
    ephemeral_config: EphemeralConfiguration,
):
    persistent_config = PersistentConfiguration.load_from_path(
        ephemeral_config.config_path
    )
    if ephemeral_config.export_dir is not None:
        output_directory = Path(ephemeral_config.export_dir)
    else:
        if persistent_config.install_dir is None:
            raise RuntimeError("No Logos installation found")
        output_directory = Path(persistent_config.install_dir) / "export"
    output_directory = output_directory.absolute()
    paths = get_logos_paths(ephemeral_config)
    with (
        NotesDatabase(paths.appdata, paths.user_id) as notes_db,
        LibraryCatalogDatabase(
            paths.appdata,
            paths.user_id,
        ) as catalog_db,
    ):
        notes = notes_db.notes()
        resolver = NoteResourceResolver(
            notes_db,
            catalog_db,
        )
        exporter = MarkdownNoteExporter(resolver)
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
