import abc
from pathlib import Path
from typing import Optional, Any

from ou_dedetai.database import SQLiteDatabase


class FaithlifeDatabase(SQLiteDatabase):
    def __init__(self, logos_app_dir: Path, logos_user_id: str):
        self.logos_app_dir = logos_app_dir
        self.logos_user_id = logos_user_id
        super().__init__(self._database_path())

    @abc.abstractmethod
    def _database_path(self) -> Path:
        pass


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
