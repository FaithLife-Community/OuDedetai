from dataclasses import dataclass, field
from pathlib import Path
from sqlite3 import Row
from typing import Optional, Iterable
import xml.etree.ElementTree as ET
import yaml

from .database import NoteResourceResolver


@dataclass
class LogosNote:
    NoteId: int
    ExternalId: str
    RevisionToken: str
    ImportId: Optional[str]
    CreatedDate: str
    ModifiedDate: str
    CreatedBy: Optional[str]
    ModifiedBy: Optional[str]
    IsDeleted: bool
    IsTrashed: bool
    IsSyncing: bool
    Kind: int
    ContentRichText: Optional[str]
    FoldedContent: Optional[str]
    NoteIndicatorId: Optional[int]
    NoteColorId: Optional[int]
    NoteStyleId: Optional[int]
    AnchorsJson: Optional[str]
    AnchorDataTypeId: Optional[int]
    AnchorLanguageId: Optional[int]
    AnchorResourceIdId: Optional[int]
    AnchorBibleBook: Optional[int]
    AnchorWorkflowTemplateIdId: Optional[int]
    AnchorWorkflowKeyId: Optional[int]
    AnchorGuideSectionId: Optional[int]
    AnchorInputIdId: Optional[int]
    TagsJson: Optional[str]
    NotebookExternalId: Optional[str]
    Rank: int
    Indent: int
    LabelsJson: Optional[str]
    ClippingTitleRichText: Optional[str]
    ClippingExcerptRichText: Optional[str]
    Role: int

    Notebook: Optional["LogosNotebook"] = None
    Tags: list["LogosTag"] = field(default_factory=list)

    @classmethod
    def from_row(cls, row: Row) -> "LogosNote":
        return cls(**dict(row))

    def to_markdown(self) -> str:
        if not self.ContentRichText:
            return ""
        document = LogosRichTextParser().parse(self.ContentRichText)
        return LogosRichTextRenderer().to_markdown(document)


@dataclass(slots=True)
class LogosNotebook:
    NotebookId: int
    ExternalId: str
    RevisionToken: str
    CreatedDate: str
    ModifiedDate: str
    CreatedBy: Optional[str]
    ModifiedBy: Optional[str]
    IsDeleted: bool
    IsTrashed: bool
    IsSyncing: bool
    Title: str
    ImportId: Optional[str]
    Role: int

    @classmethod
    def from_row(cls, row: Row) -> "LogosNotebook":
        return cls(**dict(row))

    def __repr__(self):
        return f"LogosNotebook({self.NotebookId}, {self.Title!r})"


@dataclass
class LogosTag:
    TagId: int
    Text: str
    FoldedText: str

    @classmethod
    def from_row(cls, row: Row) -> "LogosTag":
        return cls(**dict(row))

    def __repr__(self):
        return f"LogosTag({self.TagId}, {self.Text!r})"


@dataclass
class RichTextBlock:
    type: str
    content: str | None = None
    children: list[RichTextBlock] = field(default_factory=list)


@dataclass
class RichTextDocument:
    blocks: list[RichTextBlock] = field(default_factory=list)


class LogosRichTextParser:
    def parse(
        self,
        xml_text: str | None,
    ) -> RichTextDocument:
        if not xml_text:
            return RichTextDocument()

        root = ET.fromstring(xml_text)
        return RichTextDocument(
            blocks=[
                self.parse_element(child)
                for child in root
            ]
        )

    def parse_element(
        self,
        element: ET.Element,
    ) -> RichTextBlock:
        match element.tag:

            case "Paragraph":
                return RichTextBlock(
                    type="paragraph",
                    content=self.extract_text(element),
                )

            case "List":
                return RichTextBlock(
                    type="list",
                    children=[
                        self.parse_element(child)
                        for child in element
                    ],
                )

            case "ListItem":
                return RichTextBlock(
                    type="item",
                    children=[
                        self.parse_element(child)
                        for child in element
                    ],
                )

            case _:
                return RichTextBlock(
                    type=element.tag,
                    content=self.extract_text(element),
                )

    def extract_text(
        self,
        element: ET.Element,
    ) -> str:
        parts = []
        for child in element.iter():
            text = child.attrib.get("Text")
            if text:
                parts.append(text)
        return "".join(parts)


class LogosRichTextRenderer:
    def to_markdown(
        self,
        document: RichTextDocument,
    ) -> str:
        blocks = []
        for block in document.blocks:
            markdown = self.block_to_markdown(block)

            if markdown.strip():
                blocks.append(markdown)

        return "\n\n".join(blocks)

    def block_to_markdown(
        self,
        block: RichTextBlock,
        depth: int = 0,
    ) -> str:
        match block.type:
            case "paragraph":
                return block.content or ""
            case "list":
                return "\n".join(
                    self.block_to_markdown(child, depth)
                    for child in block.children
                )
            case "item":
                text = "\n".join(
                    self.block_to_markdown(child, depth)
                    for child in block.children
                )
                return f"- {text}"
            case _:
                return block.content or ""


class MarkdownNoteExporter:
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
            front_matter["resources"] = [
                self.resource_metadata(resource)
                for resource in resources
            ]

        return front_matter

    def resource_metadata(
        self,
        resource,
    ) -> dict:
        metadata = resource.metadata

        result = {
            "resource_id": resource.resource_id,
        }

        if metadata.logosres_id:
            result["logosres_id"] = metadata.logosres_id

        if metadata.title:
            result["title"] = metadata.title

        if metadata.abbreviated_title:
            result["abbreviated_title"] = metadata.abbreviated_title

        if metadata.authors:
            result["authors"] = metadata.authors

        if metadata.publisher:
            result["publisher"] = metadata.publisher

        if metadata.publication_date:
            result["publication_date"] = metadata.publication_date

        if metadata.resource_type:
            result["type"] = metadata.resource_type

        if metadata.reference_systems:
            result["reference_systems"] = metadata.reference_systems

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

        if resources:
            resource_section = self.render_resources(resources)

            if content:
                content += "\n\n"

            content += resource_section

        return content

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
