from pathlib import Path

from .database import NotesDatabase, LogosPaths
from .config import (
    EphemeralConfiguration,
    PersistentConfiguration,
    get_wine_prefix_path,
    get_wine_user,
    get_logos_appdata_dir,
    get_logos_user_id,
)
from .utils import get_logos_databases


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


def database_list_operation(ephemeral_config: EphemeralConfiguration):
    for database in get_logos_databases(ephemeral_config):
        print(database)


def database_notes_dump_operation(ephemeral_config: EphemeralConfiguration, limit: int):
    paths = get_logos_paths(ephemeral_config)
    with NotesDatabase(paths.appdata, paths.user_id) as db:
        for note in db.sample("Notes", limit):
            print(dict(note))
            print()

def parse_database_command(args, ephemeral_config):
    ephemeral_config.database_command = args.database_command

    if args.database_command == "list":
        return database_list_operation

    if args.database_command == "notes":
        if args.notes_command == "dump":
            def database_notes_dump_action(config):
                return database_notes_dump_operation(config, args.limit)
            database_notes_dump_action.__name__ = "database_notes_dump_operation"
            return database_notes_dump_action

    raise RuntimeError(
        f"Unknown database command: {args.database_command}"
    )
