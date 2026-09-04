import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from docx import Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader

from app.core.errors import AppError
from app.models.schemas import ExtractedSection


class DocumentParser(Protocol):
    def parse(self, path: Path, mime_type: str) -> list[ExtractedSection]: ...


@dataclass
class ParseDiagnostics:
    source_format: str
    page_count: int = 0
    blank_page_numbers: list[int] = field(default_factory=list)
    table_count: int = 0


@dataclass
class ParseResult:
    sections: list[ExtractedSection]
    diagnostics: ParseDiagnostics


class StandardDocumentParser:
    def parse(self, path: Path, mime_type: str) -> list[ExtractedSection]:
        return self.parse_with_diagnostics(path, mime_type).sections

    def parse_with_diagnostics(self, path: Path, mime_type: str) -> ParseResult:
        try:
            if mime_type == "application/pdf":
                sections, diagnostics = self._parse_pdf(path)
            elif mime_type.endswith("wordprocessingml.document"):
                sections, diagnostics = self._parse_docx(path)
            elif path.suffix.lower() == ".md":
                sections, diagnostics = self._parse_markdown(path)
            else:
                sections, diagnostics = self._parse_text(path)
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                "DOCUMENT_PARSE_FAILED", "文档解析失败或文件已损坏", 422
            ) from exc

        normalized = [section for section in sections if section.text.strip()]
        if not normalized:
            raise AppError("EMPTY_DOCUMENT", "文件没有可解析的正文", 422)
        return ParseResult(normalized, diagnostics)

    def _parse_pdf(self, path: Path) -> tuple[list[ExtractedSection], ParseDiagnostics]:
        reader = PdfReader(path)
        if reader.is_encrypted:
            try:
                if reader.decrypt("") == 0:
                    raise AppError("DOCUMENT_PARSE_FAILED", "无法读取加密 PDF", 422)
            except AppError:
                raise
            except Exception as exc:
                raise AppError("DOCUMENT_PARSE_FAILED", "无法读取加密 PDF", 422) from exc
        sections: list[ExtractedSection] = []
        blank_page_numbers: list[int] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = self._normalize_text(page.extract_text() or "")
            if text:
                sections.append(
                    ExtractedSection(
                        order=len(sections),
                        text=text,
                        section_path=f"第 {page_number} 页",
                        page_start=page_number,
                        page_end=page_number,
                    )
                )
            else:
                blank_page_numbers.append(page_number)
        return sections, ParseDiagnostics(
            source_format="pdf",
            page_count=len(reader.pages),
            blank_page_numbers=blank_page_numbers,
        )

    def _parse_docx(self, path: Path) -> tuple[list[ExtractedSection], ParseDiagnostics]:
        document = Document(path)
        sections: list[ExtractedSection] = []
        headings: list[str] = []
        current: list[str] = []
        table_count = 0

        def flush() -> None:
            text = self._normalize_text("\n\n".join(current))
            if text:
                sections.append(
                    ExtractedSection(
                        order=len(sections),
                        text=text,
                        title=headings[-1] if headings else None,
                        section_path=" > ".join(headings) or None,
                    )
                )
            current.clear()

        for child in document.element.body.iterchildren():
            if isinstance(child, CT_P):
                paragraph = Paragraph(child, document)
                text = paragraph.text.strip()
                if not text:
                    continue
                level = self._docx_heading_level(paragraph)
                if level is not None:
                    flush()
                    headings[level - 1 :] = [text]
                else:
                    current.append(text)
            elif isinstance(child, CT_Tbl):
                table_count += 1
                table = Table(child, document)
                rows = [
                    " | ".join(cell.text.strip() for cell in row.cells)
                    for row in table.rows
                ]
                if any(row.strip(" |") for row in rows):
                    current.append("\n".join(rows))
        flush()
        return sections, ParseDiagnostics(source_format="docx", table_count=table_count)

    def _parse_markdown(self, path: Path) -> tuple[list[ExtractedSection], ParseDiagnostics]:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        sections: list[ExtractedSection] = []
        headings: list[str] = []
        current: list[str] = []

        def flush() -> None:
            text = self._normalize_text("\n".join(current))
            if text:
                sections.append(
                    ExtractedSection(
                        order=len(sections),
                        text=text,
                        title=headings[-1] if headings else None,
                        section_path=" > ".join(headings) or None,
                    )
                )
            current.clear()

        in_code = False
        for line in lines:
            if line.lstrip().startswith("```"):
                in_code = not in_code
                current.append(line)
                continue
            match = None if in_code else re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
            if match:
                flush()
                level = len(match.group(1))
                headings[level - 1 :] = [match.group(2).strip()]
            else:
                current.append(line)
        flush()
        return sections, ParseDiagnostics(source_format="markdown")

    def _parse_text(self, path: Path) -> tuple[list[ExtractedSection], ParseDiagnostics]:
        text = self._normalize_text(path.read_text(encoding="utf-8-sig"))
        sections = [ExtractedSection(order=0, text=text)] if text else []
        return sections, ParseDiagnostics(source_format="text")

    @staticmethod
    def _docx_heading_level(paragraph: Paragraph) -> int | None:
        style = paragraph.style.name if paragraph.style else ""
        match = re.search(r"(?:heading|标题)\s*(\d+)", style, flags=re.IGNORECASE)
        return max(1, int(match.group(1))) if match else None

    @staticmethod
    def _normalize_text(text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        lines = [line.strip() for line in text.splitlines()]
        return "\n".join(lines).strip()
