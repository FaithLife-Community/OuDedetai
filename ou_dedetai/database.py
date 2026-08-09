import abc
import contextlib
import logging
import sqlite3
from dataclasses import dataclass

import inotify.adapters # type: ignore
from pathlib import Path
from typing import Any, Optional
from collections.abc import Sequence

from ou_dedetai.notes import LogosNote, LogosNotebook, LogosTag


@dataclass(frozen=True)
class ResourceMetadata:
    resource_id: str
    logosres_id: str | None
    resource_url: str | None
    title: str | None
    abbreviated_title: str | None
    authors: str | None
    publisher: str | None
    publication_date: str | None
    resource_type: str | None
    traits: list[str]
    reference_systems: list[str]


@dataclass(frozen=True)
class NoteResource:
    resource_id: str
    metadata: ResourceMetadata

    @property
    def url(self) -> str | None:
        return self.metadata.resource_url


class SQLiteDatabase(contextlib.AbstractContextManager):
    """Class for interacting with internal Faithlife databases.

    Use with python's context manager"""

    logos_app_dir: Path
    logos_user_id: str
    _db: Optional[sqlite3.Connection]

    def __init__(self, path: Path):
        self.path = path
        self._db = None

    def _database_path(self) -> Path:
        return self.path

    def execute(
        self,
        sql_statement: str,
        parameters: Sequence[Any] = None,
    ) -> sqlite3.Cursor:
        if parameters is None:
            parameters = ()
        return self.database.execute(sql_statement, parameters)

    def execute_many(
        self,
        sql_statement: str,
        parameters: Sequence[Sequence[Any]],
    ) -> sqlite3.Cursor:
        return self.database.executemany(
            sql_statement,
            parameters,
        )

    def query(
        self,
        sql_statement: str,
        parameters: Sequence[Any] = None,
    ) -> list[sqlite3.Row]:
        if parameters is None:
            parameters = ()
        return self.execute(sql_statement, parameters).fetchall()

    def query_one(
        self,
        sql_statement: str,
        parameters: Sequence[Any] = None,
    ) -> Optional[sqlite3.Row]:
        if parameters is None:
            parameters = ()
        return self.execute(sql_statement, parameters).fetchone()

    def scalar(
        self,
        sql_statement: str,
        parameters: Sequence[Any] = None,
    ) -> Optional[Any]:
        row = self.query_one(sql_statement, parameters)
        return None if row is None else row[0]

    def fetch_one(
        self,
        sql_statement: str,
        parameters: Sequence[Any] = None,
    ) -> Optional[Any]:
        if parameters is None:
            parameters = ()
        return self.execute(sql_statement, parameters).fetchone()

    def fetch_value(self, query, params=()):
        row = self.fetch_one(query, params)
        if row is None:
            return None
        return row[0]

    def table_names(self) -> list[str]:
        rows = self.query("""
            SELECT name
            FROM sqlite_master
            WHERE type='table'
            ORDER BY name
        """)
        return [row["name"] for row in rows]

    def column_names(
        self,
        table: str,
    ) -> list[str]:
        return [
            column["name"]
            for column in self.columns(table)
        ]

    def views(self) -> list[str]:
        rows = self.query("""
            SELECT name
            FROM sqlite_master
            WHERE type='view'
            ORDER BY name
        """)
        return [row["name"] for row in rows]

    def indexes(self) -> list[str]:
        rows = self.query("""
            SELECT name
            FROM sqlite_master
            WHERE type='index'
            ORDER BY name
        """)
        return [row["name"] for row in rows]

    def pragma(
        self,
        name: str,
    ) -> list[sqlite3.Row]:
        return self.query(f"PRAGMA {name}")

    def index_info(
        self,
        index: str,
    ) -> list[sqlite3.Row]:
        return self.query(
            f"PRAGMA index_info([{index}])"
        )

    def index_schema(
        self,
        index: str,
    ) -> str | None:
        return self.scalar(
            """
            SELECT sql
            FROM sqlite_master
            WHERE type = 'index'
              AND name = ?
            """,
            [index],
        )

    def has_table(
        self,
        table: str,
    ) -> bool:
        return table in self.table_names()
    def columns(
        self,
        table: str,
    ) -> list[sqlite3.Row]:
        if not self.has_table(table):
            raise ValueError(f"Unknown table: {table}")
        return self.query(f"PRAGMA table_info([{table}])")

    def schema(self) -> list[sqlite3.Row]:
        return self.query("""
            SELECT
                type,
                name,
                tbl_name,
                sql
            FROM sqlite_master
            ORDER BY type, name
        """)

    def view_schema(
        self,
        view: str,
    ) -> str | None:
        return self.scalar(
            """
            SELECT sql
            FROM sqlite_master
            WHERE type = 'view'
              AND name = ?
            """,
            [view],
        )

    def table_schema(
        self,
        table: str,
    ) -> str | None:
        return self.scalar(
            """
            SELECT sql
            FROM sqlite_master
            WHERE type='table'
              AND name=?
            """,
            [table],
        )

    def count(
        self,
        table: str,
    ) -> int:
        if not self.has_table(table):
            raise ValueError(f"Unknown table: {table}")
        return self.scalar(f"SELECT COUNT(*) FROM {table}") or 0

    def table_indexes(
        self,
        table: str,
    ) -> list[str]:
        if not self.has_table(table):
            raise ValueError(f"Unknown table: {table}")

        rows = self.query(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='index'
              AND tbl_name=?
            ORDER BY name
            """,
            [table],
        )

        return [row["name"] for row in rows]

    def describe(
        self,
        table: str,
    ) -> dict[str, Any]:
        if not self.has_table(table):
            raise ValueError(f"Unknown table: {table}")

        return {
            "table": table,
            "columns": [
                dict(row)
                for row in self.columns(table)
            ],
            "indexes": self.table_indexes(table),
            "foreign_keys": [
                dict(row)
                for row in self.foreign_keys(table)
            ],
            "count": self.count(table),
            "schema": self.table_schema(table),
        }

    def foreign_keys(
        self,
        table: str,
    ) -> list[sqlite3.Row]:
        if not self.has_table(table):
            raise ValueError(f"Unknown table: {table}")

        return self.query(
            f"PRAGMA foreign_key_list([{table}])"
        )

    def sample(
        self,
        table: str,
        limit: int = 5,
    ) -> list[sqlite3.Row]:
        if not self.has_table(table):
            raise ValueError(f"Unknown table: {table}")

        return self.query(
            f"""
            SELECT *
            FROM [{table}]
            LIMIT ?
            """,
            [limit],
        )

    def triggers(self) -> list[str]:
        rows = self.query("""
            SELECT name
            FROM sqlite_master
            WHERE type='trigger'
            ORDER BY name
        """)
        return [row["name"] for row in rows]

    def trigger_schema(
        self,
        trigger: str,
    ) -> str | None:
        return self.scalar(
            """
            SELECT sql
            FROM sqlite_master
            WHERE type = 'trigger'
              AND name = ?
            """,
            [trigger],
        )

    def database_info(self) -> dict[str, Any]:
        return {
            "path": str(self._database_path()),
            "size": self._database_path().stat().st_size,
            "tables": self.table_names(),
            "views": self.views(),
            "indexes": self.indexes(),
            "triggers": self.triggers(),
        }

    def dump(
        self,
        table: str,
        limit: int = 10,
    ) -> None:
        for row in self.sample(table, limit):
            print(dict(row))

    @property
    def database(self) -> sqlite3.Connection:
        if not self._db:
            self._db = self._connect()
        return self._db

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(
            str(self._database_path()),
            autocommit=True,
        )
        db.row_factory = sqlite3.Row
        return db

    def close(self):
        if self._db:
            self._db.close()
            self._db = None

    # Need to override __enter__ to return the proper type.
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self._db:
            self._db.__exit__(exc_type, exc_value, traceback)
            self._db = None


class FaithlifeDatabase(SQLiteDatabase):
    def __init__(self, logos_app_dir: Path, logos_user_id: str):
        self.logos_app_dir = logos_app_dir
        self.logos_user_id = logos_user_id
        super().__init__(self._database_path())

    @abc.abstractmethod
    def _database_path(self) -> Path:
        pass


class LibraryCatalogDatabase(FaithlifeDatabase):
    def _database_path(self) -> Path:
        return (
            self.logos_app_dir
            / "Data"
            / self.logos_user_id
            / "LibraryCatalog"
            / "catalog.db"
        )

    def get_resource(
        self,
        resource_id: str,
    ) -> Optional[sqlite3.Row]:
        resource_id = resource_id.lower()
        row = self.query_one(
            """
            SELECT *
            FROM Records
            WHERE lower(ResourceId) = ?
            LIMIT 1
            """,
            (resource_id,),
        )
        if row is not None:
            return row
        return self.query_one(
            """
            SELECT Records.*
            FROM Records
            JOIN AlternateResourceIds
                ON Records.RecordId = AlternateResourceIds.RecordId
            WHERE lower(AlternateResourceIds.AlternateResourceId) = ?
            LIMIT 1
            """,
            (resource_id,),
        )

    def get_resource_title(
        self,
        resource_id: str,
    ) -> Optional[str]:
        row = self.get_resource(resource_id)
        if row is None:
            return None
        return row["Title"]

    def get_alternate_resource_ids(
        self,
        resource_id: str,
    ) -> list[str]:
        row = self.get_resource(resource_id)
        if row is None:
            return []
        rows = self.query(
            """
            SELECT AlternateResourceId
            FROM AlternateResourceIds
            WHERE RecordId = ?
            ORDER BY AlternateResourceId
            """,
            (row["RecordId"],),
        )
        return [
            row["AlternateResourceId"]
            for row in rows
        ]

    def get_resource_ids(
        self,
        resource_id: str,
    ) -> list[str]:
        row = self.get_resource(resource_id)
        if row is None:
            return []
        return [
            row["ResourceId"],
            *self.get_alternate_resource_ids(resource_id),
        ]

    def get_logosres_id(
        self,
        resource_id: str,
    ) -> str | None:
        row = self.get_resource(resource_id)
        if row is None:
            return None
        alternate_ids = self.get_alternate_resource_ids(resource_id)
        for alternate_id in alternate_ids:
            if not alternate_id.lower().startswith("lls:"):
                return alternate_id
        return None

    def get_logosres_url(
            self,
            resource_id: str,
    ) -> str | None:
        logosres_id = self.get_logosres_id(resource_id)
        if logosres_id is None:
            return None
        return f"https://ref.ly/logosres/{logosres_id}"

    def get_resource_traits(
            self,
            resource_id: str,
    ) -> list[str]:
        row = self.get_resource(resource_id)
        if row is None:
            return []
        rows = self.query(
            """
            SELECT t.Value
            FROM RecordTraits rt
            JOIN Traits t
                ON t.TraitId = rt.TraitId
            WHERE rt.RecordId = ?
            ORDER BY t.Value
            """,
            (row["RecordId"],),
        )
        return [row["Value"] for row in rows]

    def get_reference_systems(
            self,
            resource_id: str,
    ) -> list[str]:
        return [
            trait.removeprefix("supports-")
            for trait in self.get_resource_traits(resource_id)
            if trait.startswith("supports-")
        ]

    def get_resource_metadata(
        self,
        resource_id: str,
    ) -> ResourceMetadata | None:
        row = self.get_resource(resource_id)

        if row is None:
            return None

        logosres_id = self.get_logosres_id(resource_id)

        return ResourceMetadata(
            resource_id=row["ResourceId"],
            logosres_id=logosres_id,
            resource_url=self.get_logosres_url(resource_id),
            title=row["Title"],
            abbreviated_title=row["AbbreviatedTitle"],
            authors=row["Authors"],
            publisher=row["Publishers"],
            publication_date=row["PublicationDate"],
            resource_type=row["Type"],
            traits=self.get_resource_traits(resource_id),
            reference_systems=self.get_reference_systems(resource_id),
        )

    def __enter__(self):
        super().__enter__()
        return self


class LocalUserPreferencesManager(FaithlifeDatabase):
    def _database_path(self):
        return self.logos_app_dir / "Documents" / self.logos_user_id / "LocalUserPreferences" / "PreferencesManager.db"

    @property
    def app_local_preferences(self) -> Optional[str]:
        return self.fetch_one(
            "SELECT Data FROM Preferences WHERE `Type`='AppLocalPreferences' LIMIT 1"
        )

    @app_local_preferences.setter
    def app_local_preferences(self, value: str):
        self.query(
            "UPDATE Preferences SET Data= ? WHERE `Type`='AppLocalPreferences'",
            [value]
        )

    def __enter__(self):
        super().__enter__()
        return self


class NotesDatabase(FaithlifeDatabase):
    def _database_path(self):
        return self.logos_app_dir / "Documents" / self.logos_user_id / "NotesToolManager" / "notestool.db"

    def notes(self) -> list[LogosNote]:
        rows = self.query("""
            SELECT *
            FROM Notes
            WHERE IsDeleted = 0
              AND IsTrashed = 0
            ORDER BY ModifiedDate DESC
        """)
        return [
            self.hydrate_note(LogosNote.from_row(row))
            for row in rows
        ]

    def note_count(self) -> int:
        return self.scalar("""
            SELECT COUNT(*)
            FROM Notes
            WHERE IsDeleted = 0
              AND IsTrashed = 0
        """) or 0

    def hydrate_note(
        self,
        note: LogosNote,
    ) -> LogosNote:
        note.Notebook = self.get_notebook_for_note(note)
        note.Tags = self.get_tags_for_note(note)
        return note

    def get_note(self, note_id: int) -> LogosNote:
        row = self.fetch_one(
            "SELECT * FROM Notes WHERE NoteId = ?",
            (note_id,)
        )
        if row is None:
            raise RuntimeError(f"Note not found: {note_id}")
        return self.hydrate_note(LogosNote.from_row(row))

    def __enter__(self):
        super().__enter__()
        return self

    def notebooks(self) -> list[LogosNotebook]:
        rows = self.query("""
            SELECT *
            FROM Notebooks
            WHERE IsDeleted = 0
              AND IsTrashed = 0
            ORDER BY Title
        """)
        return [LogosNotebook.from_row(row) for row in rows]

    def get_notebook(self, notebook_id: int) -> LogosNotebook:
        row = self.query_one(
            "SELECT * FROM Notebooks WHERE NotebookId = ?",
            (notebook_id,),
        )
        if row is None:
            raise RuntimeError(f"Notebook not found: {notebook_id}")
        return LogosNotebook.from_row(row)

    def tags(self) -> list[LogosTag]:
        rows = self.query("""
            SELECT *
            FROM Tags
            ORDER BY Text
        """)
        return [LogosTag.from_row(row) for row in rows]

    def get_notebook_by_external_id(
        self,
        external_id: str,
    ) -> LogosNotebook:
        row = self.query_one(
            "SELECT * FROM Notebooks WHERE ExternalId = ?",
            (external_id,),
        )
        if row is None:
            raise RuntimeError(
                f"Notebook not found: {external_id}"
            )
        return LogosNotebook.from_row(row)

    def get_notebook_for_note(
        self,
        note: LogosNote,
    ) -> LogosNotebook | None:
        if not note.NotebookExternalId:
            return None
        return self.get_notebook_by_external_id(note.NotebookExternalId)

    def get_tag(self, tag_id: int) -> LogosTag:
        row = self.fetch_one(
            "SELECT * FROM Tags WHERE TagId = ?",
            (tag_id,),
        )
        if row is None:
            raise RuntimeError(
                f"Tag not found: {tag_id}"
            )
        return LogosTag.from_row(row)

    def get_tags_for_note(
        self,
        note: LogosNote,
    ) -> list[LogosTag]:
        rows = self.query(
            """
            SELECT Tags.*
            FROM Tags
            JOIN NoteTags
                ON Tags.TagId = NoteTags.TagId
            WHERE NoteTags.NoteId = ?
            ORDER BY Tags.Text
            """,
            (note.NoteId,),
        )
        return [LogosTag.from_row(row) for row in rows]

    def get_resource_ids_for_note(
        self,
        note_id: int,
    ) -> list[str]:
        rows = self.query(
            """
            SELECT DISTINCT ResourceIds.ResourceId
            FROM NoteAnchorTextRanges
            JOIN ResourceIds
                ON ResourceIds.ResourceIdId =
                   NoteAnchorTextRanges.ResourceIdId
            WHERE NoteAnchorTextRanges.NoteId = ?
            ORDER BY ResourceIds.ResourceId
            """,
            (note_id,),
        )

        return [
            row["ResourceId"]
            for row in rows
        ]

    def get_anchor_text_ranges(
        self,
        note_id: int,
    ) -> list[sqlite3.Row]:
        return self.query(
            """
            SELECT *
            FROM NoteAnchorTextRanges
            WHERE NoteId = ?
            ORDER BY ResourceIdId, Offset
            """,
            (note_id,),
        )

    def get_anchor_references(
        self,
        note_id: int,
    ) -> list[sqlite3.Row]:
        return self.query(
            """
            SELECT *
            FROM NoteAnchorReferences
            WHERE NoteId = ?
            ORDER BY DataTypeId
            """,
            (note_id,),
        )

    def search_notes(
            self,
            query: str,
            limit: int = 20,
    ) -> list[LogosNote]:
        rows = self.query(
            """
            SELECT *
            FROM Notes
            WHERE IsDeleted = 0
              AND IsTrashed = 0
              AND FoldedContent LIKE ?
            ORDER BY ModifiedDate DESC
            LIMIT ?
            """,
            (f"%{query.lower()}%", limit),
        )
        return [
            LogosNote.from_row(row)
            for row in rows
        ]


# FIXME: refactor into FaithlifeDatabase class
def watch_db(path: str, sql_statements: list[str]):
    """Runs SQL statements against a sqlite db once to start with, then again every time
    The sqlite db is written to.

    Handles -wal/-shm as well

    This function may run infinitely, spawn it on it's own thread
    """
    # Silence inotify logs
    logging.getLogger('inotify').setLevel(logging.CRITICAL)
    i = inotify.adapters.Inotify()
    i.add_watch(path)

    def execute_sql(cur):
        # logging.debug(f"Executing SQL against {path}: {sql_statements}")
        for statement in sql_statements:
            try:
                cur.execute(statement)
            # Database may be locked, keep trying later.
            except sqlite3.OperationalError:
                logging.exception("Best-effort db update failed")
                pass

    with sqlite3.connect(path, autocommit=True) as con:
        cur = con.cursor()

        # Execute once before we start the loop
        execute_sql(cur)
        swallow_one = True

        # Keep track of if we've added -wal and -shm are added yet
        # They may not exist when we start
        watching_wal_and_shm = False
        for event in i.event_gen(yield_nones=False):
            (_, type_names, _, _) = event
            # These files may not exist when it's executes for the first time
            if (
                not watching_wal_and_shm
                and Path(path + "-wal").exists()
                and Path(path + "-shm").exists()
            ):
                i.add_watch(path + "-wal")
                i.add_watch(path + "-shm")
                watching_wal_and_shm = True

            if 'IN_MODIFY' in type_names or 'IN_CLOSE_WRITE' in type_names:
                # Check to make sure that we aren't responding to our own write
                if swallow_one:
                    swallow_one = False
                    continue
                execute_sql(cur)
                swallow_one = True
        # Shouldn't be possible to get here, but on the off-chance it happens,
        # we'd like to know and cleanup
        logging.debug(f"Stopped watching {path}")


class NoteResourceResolver:
    def __init__(
        self,
        notes_db: NotesDatabase,
        catalog_db: LibraryCatalogDatabase,
    ):
        self.notes_db = notes_db
        self.catalog_db = catalog_db

    def get_resources_for_note(
        self,
        note_id: int,
    ) -> list[NoteResource]:
        resources = []

        for resource_id in self.notes_db.get_resource_ids_for_note(
            note_id
        ):
            metadata = self.catalog_db.get_resource_metadata(
                resource_id
            )

            if metadata is None:
                continue

            resources.append(
                NoteResource(
                    resource_id=resource_id,
                    metadata=metadata,
                )
            )

        return resources


class DatabaseInspector:
    def __init__(
        self,
        database: SQLiteDatabase,
    ):
        self.database = database

    def tables(self) -> list[str]:
        rows = self.database.query("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            ORDER BY name
        """)

        return [row["name"] for row in rows]

    def schema(self, table: str):
        return self.database.query(
            f"PRAGMA table_info('{table}')"
        )

    def summary(self) -> dict[str, Any]:
        return self.database.database_info()

    def print_summary(self) -> None:
        info = self.summary()

        print("Database:")
        print(f"  {info['path']}")
        print()

        print("Tables:")
        for table in info["tables"]:
            print(f"  {table}")

        print()

        print("Views:")
        if info["views"]:
            for view in info["views"]:
                print(f"  {view}")
        else:
            print("  none")

        print()

        print("Indexes:")
        for index in info["indexes"]:
            print(f"  {index}")

    def describe_table(
        self,
        table: str,
    ) -> None:
        info = self.database.describe(table)
        print(f"Schema:")
        print(f"  {info['schema'] or 'none'}")

        print(f"Table: {table}")
        print()

        print(f"Rows: {info['count']}")
        print()

        print("Columns:")

        for column in info["columns"]:
            name = column["name"]
            dtype = column["type"]
            nullable = not column["notnull"]

            print(
                f"  {name:<20} "
                f"{dtype:<15} "
                f"{'NULL' if nullable else 'NOT NULL'}"
            )

        print()

        print("Indexes:")
        for index in info["indexes"]:
            print(f"  {index}")

        print()
        print("Foreign Keys:")

        if info["foreign_keys"]:
            for foreign_key in info["foreign_keys"]:
                print(f"  {dict(foreign_key)}")
        else:
            print("  none")

    def sample_table(
        self,
        table: str,
        limit: int = 5,
    ) -> None:

        print(f"Sample rows from {table}:")
        print()

        for row in self.database.sample(table, limit):
            print(dict(row))
            print()
