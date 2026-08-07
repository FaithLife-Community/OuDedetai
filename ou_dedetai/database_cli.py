from pathlib import Path

from .database import NotesDatabase, SQLiteDatabase, DatabaseInspector
from .paths import LogosPaths
from .config import (
    EphemeralConfiguration,
    PersistentConfiguration,
    get_wine_prefix_path,
    get_wine_user,
    get_logos_appdata_dir,
    get_logos_user_id,
)


def add_database_parser(subparsers):
    db_parser = subparsers.add_parser(
        "database",
        help="inspect Logos SQLite databases",
    )

    db_commands = db_parser.add_subparsers(
        dest="database_command",
        title="database commands",
        required=True,
    )

    db_commands.add_parser(
        "list",
        help="list Logos SQLite databases",
    )

    inspect_parser = db_commands.add_parser(
        "inspect",
        help="inspect a SQLite database",
    )

    inspect_parser.add_argument(
        "--path",
        metavar="DATABASE",
        help="Path to SQLite database. Defaults to installed Logos database.",
    )

    notes_parser = db_commands.add_parser(
        "notes",
        help="inspect Logos Notes database",
    )

    notes_commands = notes_parser.add_subparsers(
        dest="notes_command",
        title="notes commands",
        required=True,
    )

    notes_commands.add_parser(
        "count",
        help="show note counts",
    )

    notes_commands.add_parser(
        "info",
        help="show Notes database information",
    )

    dump_parser = notes_commands.add_parser(
        "dump",
        help="dump sample notes",
    )

    dump_parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="number of notes to dump",
    )

    return db_parser


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


def database_notes_dump_operation(ephemeral_config: EphemeralConfiguration):
    paths = get_logos_paths(ephemeral_config)
    with NotesDatabase(paths.appdata, paths.user_id) as db:
        for note in db.sample("Notes", ephemeral_config.database_limit):
            print(dict(note))
            print()

def parse_database_command(args, ephemeral_config):
    ephemeral_config.database_command = args.database_command

    if args.database_command == "list":
        return database_list_operation

    if args.database_command == "notes":
        ephemeral_config.notes_command = args.notes_command

        if args.notes_command == "count":
            return database_notes_count_operation
        
        if args.notes_command == "info":
            return database_notes_info_operation

        if args.notes_command == "dump":
            ephemeral_config.database_limit = args.limit
            return database_notes_dump_operation

    if args.database_command == "inspect":
        ephemeral_config.database_path = args.path
        return database_operation

    raise RuntimeError(
        f"Unknown database command: {args.database_command}"
    )
