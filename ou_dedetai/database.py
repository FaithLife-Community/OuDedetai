import abc
import contextlib
import logging
import sqlite3
from typing_extensions import deprecated

import inotify.adapters # type: ignore
from pathlib import Path
from typing import Any, Optional
from collections.abc import Sequence


class FaithlifeDatabase(contextlib.AbstractContextManager):
    """Class for interacting with internal Faithlife databases.
    
    Use with python's context manager"""

    logos_app_dir: Path
    logos_user_id: str
    _db: Optional[sqlite3.Connection]

    def __init__(
        self,
        logos_app_dir: Path,
        logos_user_id: str
    ):
        self.logos_app_dir = logos_app_dir
        self.logos_user_id = logos_user_id
        self._db = None

    @abc.abstractmethod
    def _database_path(self) -> Path:
        """Path to the database"""
        pass

    def execute(
        self,
        sql_statement: str,
        parameters: Sequence[Any] = None,
    ) -> sqlite3.Cursor:
        if parameters is None:
            parameters = ()
        return self.database.execute(sql_statement, parameters)

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
        return self.scalar(sql_statement, parameters)

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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self._db:
            self._db.__exit__(exc_type, exc_value, traceback)
            self._db = None


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
    
    # Need to override __enter__ to return the proper type.
    def __enter__(self):
        super().__enter__()
        return self


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
