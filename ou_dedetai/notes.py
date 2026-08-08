from dataclasses import dataclass, field
from sqlite3 import Row
from typing import Optional
import xml.etree.ElementTree as ET


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


