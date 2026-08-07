from dataclasses import dataclass
from sqlite3 import Row
from typing import Optional


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

    @classmethod
    def from_row(cls, row: Row) -> "LogosNote":
        return cls(**dict(row))
