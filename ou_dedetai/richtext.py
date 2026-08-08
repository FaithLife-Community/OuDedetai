from dataclasses import dataclass, field
from xml.etree import ElementTree as ET


@dataclass
class RichTextBlock:
    type: str
    content: str | None = None
    children: list[RichTextBlock] = field(default_factory=list)
    formatting: list[str] = field(default_factory=list)


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
        root = ET.fromstring( f"<Root>{xml_text}</Root>" )
        if root.tag in {"Paragraph", "List", "ListItem"}:
            return RichTextDocument(
                blocks=[self.parse_element(root)]
            )
        return RichTextDocument(
            blocks=[
                self.parse_element(child)
                for child in root
                if self.is_meaningful_element(child)
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
                    children=self.parse_runs(element),
                )
            case "List":
                return RichTextBlock(
                    type="list",
                    children=[
                        self.parse_element(child)
                        for child in element
                        if self.is_meaningful_element(child)
                    ],
                )
            case "ListItem":
                return RichTextBlock(
                    type="item",
                    children=[
                        self.parse_element(child)
                        for child in element
                        if self.is_meaningful_element(child)
                    ],
                )
            case _:
                return RichTextBlock(
                    type=element.tag,
                    children=[
                        self.parse_element(child)
                        for child in element
                        if self.is_meaningful_element(child)
                    ],
                    content=self.extract_text(element),
                )

    def run_format(
        self,
        run: ET.Element,
    ) -> list[str]:
        formats = []
        if run.attrib.get("FontBold", "").lower() == "true":
            formats.append("bold")
        if run.attrib.get("FontItalic", "").lower() == "true":
            formats.append("italic")
        if run.attrib.get("FontUnderline", "").lower() == "true":
            formats.append("underline")
        return formats

    def parse_runs(
        self,
        element: ET.Element,
    ) -> list[RichTextBlock]:
        blocks = []
        for run in element:
            if run.tag != "Run":
                continue
            text = run.attrib.get("Text", "")
            if not text:
                continue
            blocks.append(
                RichTextBlock(
                    type="run",
                    content=text,
                    formatting=self.run_format(run)
                )
            )

        return blocks

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

    def is_meaningful_element(
        self,
        element: ET.Element,
    ) -> bool:
        if element.tag == "Paragraph":
            return bool(self.extract_text(element).strip())
        if element.tag == "Run":
            return bool(element.attrib.get("Text", "").strip())
        return True


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
                return "".join(
                    self.block_to_markdown(child, depth)
                    for child in block.children
                )
            case "run":
                text = block.content or ""
                if "bold" in block.formatting:
                    text = f"**{text}**"
                if "italic" in block.formatting:
                    text = f"_{text}_"
                if "underline" in block.formatting:
                    text = f"<u>{text}</u>"
                return text
            case "list":
                return "\n".join(
                    self.block_to_markdown(child, depth)
                    for child in block.children
                )
            case "item":
                text = "".join(
                    self.block_to_markdown(child, depth)
                    for child in block.children
                )
                return f"- {text}"
            case _:
                if block.children:
                    return "".join(
                        self.block_to_markdown(child, depth)
                        for child in block.children
                    )
                return block.content or ""
