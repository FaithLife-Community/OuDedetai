from . import actions_database


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
    dump_parser = db_commands.add_parser(
        "dump",
        help="dump rows from a database table",
    )
    dump_parser.add_argument(
        "table",
        help="table to dump",
    )
    dump_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="maximum number of rows",
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
    notes_commands.add_parser(
        "tables",
        help="list Notes database tables",
    )
    schema_parser = notes_commands.add_parser(
        "schema",
        help="show Notes database table schema",
    )
    schema_parser.add_argument(
        "table",
        help="table name",
    )
    get_parser = notes_commands.add_parser(
        "get",
        help="show a single note",
    )
    get_parser.add_argument(
        "note_id",
        type=int,
        help="NoteId to display",
    )
    render_parser = notes_commands.add_parser(
        "render",
        help="render a note as Markdown",
    )
    render_parser.add_argument(
        "note_id",
        type=int,
        help="NoteId to render",
    )
    return db_parser


def parse_database_command(args, ephemeral_config):
    ephemeral_config.database_command = args.database_command
    if args.database_command == "inspect":
        ephemeral_config.database_path = args.path
        return actions_database.database_operation

    if args.database_command == "list":
        return actions_database.database_list_operation

    if args.database_command == "dump":
        ephemeral_config.database_table = args.table
        ephemeral_config.database_limit = args.limit
        return actions_database.database_dump_operation

    if args.database_command == "notes":
        ephemeral_config.notes_command = args.notes_command
        if args.notes_command == "count":
            return actions_database.database_notes_count_operation
        if args.notes_command == "info":
            return actions_database.database_notes_info_operation
        if args.notes_command == "tables":
            return actions_database.database_notes_tables_operation
        if args.notes_command == "schema":
            ephemeral_config.database_table = args.table
            return actions_database.database_notes_schema_operation
        if args.notes_command == "get":
            ephemeral_config.note_id = args.note_id
            return actions_database.database_notes_get_operation
        if args.notes_command == "render":
            ephemeral_config.note_id = args.note_id
            return actions_database.database_notes_render_operation

    raise RuntimeError(f"Unknown database command: {args.database_command}")
