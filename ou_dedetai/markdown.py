import re
import unicodedata
from pathlib import Path
from typing import Iterable, Callable

import yaml

from ou_dedetai.database import NoteResourceResolver, NoteResource
from ou_dedetai.notes import LogosNote, LogosNotebook


class MarkdownNoteExporter:
    NO_CONTENT = "<!-- No Content -->"
    def __init__(
        self,
        resolver: NoteResourceResolver
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
        resources = self.resolver.get_resources_for_note(note.NoteId)
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

    def sanitize_filename(
        self,
        value: str,
    ) -> str:
        value = unicodedata.normalize("NFC", value)
        value = re.sub(r"""[<>:;"'/\\|?*\x00-\x1f]""", "-", value)
        value = re.sub(r"""['"‘’“”().]""", "", value)
        value = value.replace("*", "")
        value = value.replace(",", "_").replace(",_", "_")
        value = re.sub(r"\s+", "_", value)
        value = re.sub(r"\t+", "_and_", value)
        value = re.sub("&", "and", value)
        value = value.replace("-_", "_").replace("_-", "_")
        value = re.sub(r"_+", "_", value)
        value = re.sub(r"-+", "-", value)
        return value

    def resource_filename(
        self,
        resource,
    ) -> str:
        title = self.resource_title(resource)
        authors = self.resource_authors(resource)
        parts = ["Outline_of"]
        if len(authors) == 1:
            parts.append(authors[0])
        elif len(authors) == 2:
            parts.append(f"{authors[0]}_and_{authors[1]}")
        elif authors:
            parts.append("_".join(authors[:-1]) + "_and_" + authors[-1])
        parts.append(title)
        filename = "_".join(
            self.sanitize_filename(part)
            for part in parts
        )
        return f"{filename}.md"

    def notebook_filename(
        self,
        notebook: LogosNotebook,
    ) -> str:
        return (
            f"Notebook_"
            f"{self.sanitize_filename(notebook.Title)}.md"
        )

    def export_notebook_outline(
        self,
        notebook: LogosNotebook,
        notes: Iterable[LogosNote],
        note_id_width: int
    ) -> str:
        lines = [f"# {notebook.Title}", ""]
        for note in notes:
            lines.append(f"- [[{str(note.NoteId).zfill(note_id_width)}]]")
        return "\n".join(lines) + "\n"

    def export_resource_outline(
        self,
        resource,
        notes: Iterable[LogosNote],
        note_id_width: int
    ) -> str:
        metadata = resource.metadata
        title = (
                metadata.title
                or metadata.abbreviated_title
                or resource.resource_id
        )
        lines = [f"# {title}", ""]
        for note in notes:
            lines.append(f"- [[{str(note.NoteId).zfill(note_id_width)}]]")
        return "\n".join(lines) + "\n"

    def write_notebook_outline(
        self,
        notebook: LogosNotebook,
        notes: Iterable[LogosNote],
        output_directory: Path,
        note_id_width: int
    ) -> Path:
        path = output_directory / self.notebook_filename(notebook)
        path.write_text(self.export_notebook_outline(notebook, notes, note_id_width), encoding="utf-8")
        return path

    def resource_title(
        self,
        resource,
    ) -> str:
        metadata = resource.metadata
        return (
            metadata.title
            or metadata.abbreviated_title
            or resource.resource_id
        )

    def resource_authors(
        self,
        resource,
    ) -> list[str]:
        metadata = resource.metadata
        if not metadata.authors:
            return []
        if isinstance(metadata.authors, str):
            raw_authors = [metadata.authors]
        else:
            raw_authors = []
            for value in metadata.authors:
                raw_authors.extend(value.split("\t"))
        authors: list[str] = []
        for raw_author in raw_authors:
            author = raw_author.strip()
            if not author:
                continue
            if "," in author:
                author = author.split(",", 1)[0].strip()
            authors.append(author)
        return authors

    def write_resource_outline(
        self,
        resource,
        notes: Iterable[LogosNote],
        output_directory: Path,
        note_id_width: int
    ) -> Path:
        path = output_directory / self.resource_filename(resource)
        path.write_text(self.export_resource_outline(resource, notes, note_id_width), encoding="utf-8")
        return path

    def filename(
        self,
        note: LogosNote,
        note_id_width: int
    ) -> str:
        return f"Logos_{note.NoteId:0{note_id_width}d}.md"

    def write_note(
        self,
        note: LogosNote,
        output_directory: Path,
        note_id_width: int
    ) -> Path:
        output_directory.mkdir(
            parents=True,
            exist_ok=True,
        )
        filename = self.filename(note, note_id_width)
        path = output_directory / filename
        path.write_text(self.export_note(note), encoding="utf-8")
        return path

    def group_by_notebook(
        self,
        notes: Iterable[LogosNote],
    ) -> dict[int | None, list[LogosNote]]:
        grouped: dict[int | None, list[LogosNote]] = {}
        for note in notes:
            notebook_id = (note.Notebook.NotebookId if note.Notebook is not None else None)
            grouped.setdefault(notebook_id, []).append(note)
        return grouped

    def group_by_resource(
        self,
        notes: Iterable[LogosNote],
    ) -> dict[str, tuple[NoteResource, list[LogosNote]]]:
        grouped: dict[str, tuple[NoteResource, list[LogosNote]]] = {}
        for note in notes:
            resources = self.resolver.get_resources_for_note(note.NoteId)
            for resource in resources:
                if resource.resource_id not in grouped:
                    grouped[resource.resource_id] = (resource, [])
                grouped[resource.resource_id][1].append(note)
        return grouped

    def export_all(
        self,
        notes: Iterable[LogosNote],
        output_directory: Path,
        progress_callback: Callable[[int, int], None] | None = None,
        status_callback: Callable[[str], None] | None = None,
    ) -> list[Path]:
        notes = list(notes)
        paths: list[Path] = []
        if status_callback is not None:
            status_callback("Calculating")
        notebook_groups = list(self.group_by_notebook(notes).values())
        resource_groups = list(self.group_by_resource(notes).values())
        notebook_count = sum(1 for notebook_notes in notebook_groups
                             if notebook_notes and notebook_notes[0].Notebook is not None)
        resource_count = len(resource_groups)
        total = len(notes) + notebook_count + resource_count
        print("\n")
        print(f"Found: {len(notes)} notes, {notebook_count} notebooks, and {resource_count} resources referenced.")
        note_id_width = max(1, len(str(max((note.NoteId for note in notes), default=1))))
        if status_callback is not None:
            status_callback("ready")
        current = 0
        def report_progress() -> None:
            nonlocal current
            current += 1
            if progress_callback is not None:
                progress_callback(current, total)
        for note in notes:
            paths.append(self.write_note(note, output_directory, note_id_width=note_id_width))
            report_progress()
        for notebook_notes in notebook_groups:
            notebook = notebook_notes[0].Notebook
            if notebook is None:
                continue
            paths.append(self.write_notebook_outline(notebook, notebook_notes, output_directory, note_id_width))
            report_progress()
        for resource, resource_notes in resource_groups:
            paths.append(self.write_resource_outline(resource, resource_notes, output_directory, note_id_width))
            report_progress()
        return paths
