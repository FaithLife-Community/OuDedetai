from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LogosPaths:
    """
    Paths to the major Logos data locations for a user installation.
    """
    appdata: Path
    data: Path
    documents: Path
    user_id: str

    @property
    def databases(self) -> list[Path]:
        """
        Return all SQLite databases in known Logos locations.
        """
        return sorted(
            [
                *self.data.rglob("*.db"),
                *self.documents.rglob("*.db"),
            ]
        )