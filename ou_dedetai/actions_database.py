from pathlib import Path

from ou_dedetai.config import EphemeralConfiguration, PersistentConfiguration, get_wine_prefix_path, get_wine_user, \
    get_logos_appdata_dir, get_logos_user_id
from ou_dedetai.database import NotesDatabase, DatabaseInspector
from ou_dedetai.paths import LogosPaths


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
