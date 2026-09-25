from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LogosPaths:
    appdata: Path
    data: Path
    documents: Path
    user_id: str

    @property
    def databases(self) -> list[Path]:
        return sorted([*self.data.rglob("*.db"), *self.documents.rglob("*.db")])
