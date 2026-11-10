import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ou_dedetai.database_faithlife import FaithlifeDatabase


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


class LibraryCatalogDatabase(FaithlifeDatabase):
    def _database_path(self) -> Path:
        return self.logos_app_dir / "Data" / self.logos_user_id / "LibraryCatalog" / "catalog.db"

    def get_resource(self, resource_id: str) -> Optional[sqlite3.Row]:
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

    def get_resource_title(self, resource_id: str) -> Optional[str]:
        row = self.get_resource(resource_id)
        if row is None:
            return None
        return row["Title"]

    def get_alternate_resource_ids(self, resource_id: str) -> list[str]:
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

    def get_resource_ids(self, resource_id: str) -> list[str]:
        row = self.get_resource(resource_id)
        if row is None:
            return []
        return [
            row["ResourceId"],
            *self.get_alternate_resource_ids(resource_id),
        ]

    def get_logosres_id(self, resource_id: str) -> str | None:
        row = self.get_resource(resource_id)
        if row is None:
            return None
        alternate_ids = self.get_alternate_resource_ids(resource_id)
        for alternate_id in alternate_ids:
            if not alternate_id.lower().startswith("lls:"):
                return alternate_id
        return None

    def get_logosres_url(self, resource_id: str) -> str | None:
        logosres_id = self.get_logosres_id(resource_id)
        if logosres_id is None:
            return None
        return f"https://ref.ly/logosres/{logosres_id}"

    def get_resource_traits(self, resource_id: str) -> list[str]:
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

    def get_reference_systems(self, resource_id: str) -> list[str]:
        return [
            trait.removeprefix("supports-")
            for trait in self.get_resource_traits(resource_id)
            if trait.startswith("supports-")
        ]

    def get_resource_metadata(self, resource_id: str) -> ResourceMetadata | None:
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
