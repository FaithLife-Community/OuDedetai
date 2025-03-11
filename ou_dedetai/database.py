import abc
import contextlib
import logging
import sqlite3
import inotify.adapters # type: ignore
from pathlib import Path
from typing import Any, Optional


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

    @abc.abstractmethod
    def _database_path(self) -> Path:
        """Path to the database"""
        pass

    def execute_sql(
        self,
        sql_statement: str,
        parameters: list[str] = list(frozenset())
    ) -> list[Any]:
        return self.database.execute(sql_statement, parameters).fetchall()
        
    def fetch_one(
        self,
        sql_statement: str,
        parameters: list[str] = list(frozenset())
    ) -> Optional[Any]:
        contents = self.execute_sql(sql_statement, parameters)
        if contents and len(contents) > 0:
            # Content comes in as a tuple, trailing , unpacks first argument
            content, = contents[0]
            return content
        return None

    @property
    def database(self) -> sqlite3.Connection:
        if not self._db:
            self._db = self._connect()
        return self._db

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._database_path()), autocommit=True)

    def close(self):
        if self._db:
            self._db.close()

    def __enter__(self):
        self._db = self._connect()
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
        self.execute_sql(
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
