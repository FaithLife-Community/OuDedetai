import sqlite3
from dataclasses import dataclass

from ou_dedetai.database_faithlife import FaithlifeDatabase
from ou_dedetai.database_faithlife_catalog import ResourceMetadata, LibraryCatalogDatabase
from ou_dedetai.notes import LogosNote, LogosNotebook, LogosTag


@dataclass(frozen=True)
class NoteResource:
    resource_id: str
    metadata: ResourceMetadata

    @property
    def url(self) -> str | None:
        return self.metadata.resource_url


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
            limit: int = 5
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
