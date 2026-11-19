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
