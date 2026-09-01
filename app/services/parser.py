import re
from pathlib import Path
from typing import Protocol

from docx import Document
from pypdf import PdfReader

from app.core.errors import AppError
from app.models.schemas import ExtractedSection


class DocumentParser(Protocol):
    def parse(self, path: Path, mime_type: str) -> list[ExtractedSection]: ...


class StandardDocumentParser:
    def parse(self, path: Path, mime_type: str) -> list[ExtractedSection]:
        try:
            if mime_type == "application/pdf":
                sections = self._parse_pdf(path)
            elif mime_type.endswith("wordprocessingml.document"):
                sections = self._parse_docx(path)
            elif path.suffix.lower() == ".md":
                sections = self._parse_markdown(path)
            else:
                sections = self._parse_text(path)
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                "DOCUMENT_PARSE_FAILED", "文档解析失败或文件已损坏", 422
            ) from exc

        normalized = [section for section in sections if section.text.strip()]
        if not normalized:
            raise AppError("EMPTY_DOCUMENT", "文件没有可解析的正文", 422)
        return normalized

    def _parse_pdf(self, path: Path) -> list[ExtractedSection]:
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
        return sections

    def _parse_docx(self, path: Path) -> list[ExtractedSection]:
        document = Document(path)
        sections: list[ExtractedSection] = []
        headings: list[str] = []
        current: list[str] = []

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

        for paragraph in document.paragraphs:
            text = paragraph.text.strip()
            if not text:
                continue
            style = paragraph.style.name if paragraph.style else ""
            match = re.match(r"Heading\s+(\d+)", style, flags=re.IGNORECASE)
            if match:
                flush()
                level = max(1, int(match.group(1)))
                headings[level - 1 :] = [text]
            else:
                current.append(text)
        for table in document.tables:
            rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows]
            if any(row.strip(" |") for row in rows):
                current.append("\n".join(rows))
        flush()
        return sections

    def _parse_markdown(self, path: Path) -> list[ExtractedSection]:
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
        return sections

    def _parse_text(self, path: Path) -> list[ExtractedSection]:
        text = self._normalize_text(path.read_text(encoding="utf-8-sig"))
        return [ExtractedSection(order=0, text=text)] if text else []

    @staticmethod
    def _normalize_text(text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        lines = [line.strip() for line in text.splitlines()]
        return "\n".join(lines).strip()

