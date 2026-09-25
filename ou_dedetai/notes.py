from dataclasses import dataclass, field
from sqlite3 import Row
from typing import Optional

from ou_dedetai.richtext import LogosRichTextParser, LogosRichTextRenderer


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
        if self.ContentRichText:
            document = LogosRichTextParser().parse(self.ContentRichText)
            return LogosRichTextRenderer().to_markdown(document)
        if self.FoldedContent:
            return self.FoldedContent.strip()
        return ""


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
