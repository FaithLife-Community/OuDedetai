from pathlib import Path
from typing import Iterable

import yaml

from ou_dedetai.database import NoteResourceResolver
from ou_dedetai.notes import LogosNote


class MarkdownNoteExporter:
    NO_CONTENT = "<!-- No Content -->"

    def __init__(
        self,
        resolver: NoteResourceResolver,
    ):
        self.resolver = resolver

    def export_note(
        self,
        note: LogosNote,
    ) -> str:
        front_matter = self.build_front_matter(note)
        content = self.build_content(note)

        return (
            "---\n"
            f"{yaml.safe_dump(front_matter, sort_keys=False).strip()}\n"
            "---\n\n"
            f"{content.rstrip()}\n"
        )

    def build_front_matter(
        self,
        note: LogosNote,
    ) -> dict:
        front_matter = {
            "note_id": note.NoteId,
            "external_id": note.ExternalId,
            "created": note.CreatedDate,
            "modified": note.ModifiedDate,
        }

        if note.Notebook is not None:
            front_matter["notebook"] = note.Notebook.Title

        if note.Tags:
            front_matter["tags"] = [
                tag.Text
                for tag in note.Tags
            ]

        resources = self.resolver.get_resources_for_note(
            note.NoteId
        )

        if resources:
            front_matter["anchors"] = [
                self.resource_metadata(resource)
                for resource in resources
            ]

        return front_matter

    def resource_metadata(
        self,
        resource,
    ) -> dict:
        metadata = resource.metadata
        result = {}
        result = {"resource_id": resource.resource_id}
        if metadata.logosres_id:
            result["logosres_id"] = metadata.logosres_id
        if metadata.authors:
            result["authors"] = metadata.authors
        if metadata.logosres_id:
            result["url"] = (
                f"https://ref.ly/logosres/{metadata.logosres_id}"
            )
        return result

    def build_content(
        self,
        note: LogosNote,
    ) -> str:
        content = note.to_markdown().strip()
        resources = self.resolver.get_resources_for_note(
            note.NoteId
        )
        sections = []
        if content:
            sections.append(content)
        else:
            sections.append(self.NO_CONTENT)

        if resources:
            sections.append(
                self.render_resources(resources)
            )

        return "\n\n".join(sections)

    def render_resources(
        self,
        resources,
    ) -> str:
        lines = [
            "## Resources",
            "",
        ]

        for resource in resources:
            metadata = resource.metadata

            title = (
                metadata.title
                or metadata.abbreviated_title
                or resource.resource_id
            )

            if metadata.logosres_id:
                url = (
                    f"https://ref.ly/logosres/"
                    f"{metadata.logosres_id}"
                )
                lines.append(f"- [{title}]({url})")
            else:
                lines.append(f"- {title}")

        return "\n".join(lines)

    def write_note(
        self,
        note: LogosNote,
        output_directory: Path,
    ) -> Path:
        output_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        filename = self.filename(note)
        path = output_directory / filename

        path.write_text(
            self.export_note(note),
            encoding="utf-8",
        )

        return path

    def filename(
        self,
        note: LogosNote,
    ) -> str:
        return f"{note.NoteId}.md"

    def export_all(
        self,
        notes: Iterable[LogosNote],
        output_directory: Path,
    ) -> list[Path]:
        paths = []

        for note in notes:
            paths.append(
                self.write_note(
                    note,
                    output_directory,
                )
            )

        return paths
