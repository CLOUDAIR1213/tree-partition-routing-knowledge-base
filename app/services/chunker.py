import hashlib
import re

from app.models.schemas import ChunkCandidateData, ExtractedSection

TOKEN_PATTERN = re.compile(r"[\u3400-\u9fff]|[A-Za-z0-9_./:+-]+|[^\s]")


class SectionChunker:
    def __init__(
        self,
        target_tokens: int,
        min_tokens: int,
        max_tokens: int,
        overlap_tokens: int,
    ) -> None:
        self.target_tokens = target_tokens
        self.min_tokens = min_tokens
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens

    def chunk(
        self,
        document_id: str,
        document_title: str,
        sections: list[ExtractedSection],
    ) -> list[ChunkCandidateData]:
        chunks: list[ChunkCandidateData] = []
        for section in sections:
            parts = self._split_section(section.text)
            for part in parts:
                index = len(chunks)
                embedding_text = self._embedding_text(document_title, section, part)
                chunks.append(
                    ChunkCandidateData(
                        chunk_id=f"{document_id}:v1:{index:05d}",
                        document_id=document_id,
                        chunk_index=index,
                        text=part,
                        embedding_text=embedding_text,
                        title=document_title,
                        section_path=section.section_path,
                        page_start=section.page_start,
                        page_end=section.page_end,
                        checksum_sha256=hashlib.sha256(
                            embedding_text.encode("utf-8")
                        ).hexdigest(),
                    )
                )
        return chunks

    def _split_section(self, text: str) -> list[str]:
        if self._token_count(text) <= self.max_tokens:
            return [text]
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        if len(paragraphs) == 1:
            paragraphs = [part.strip() for part in text.splitlines() if part.strip()]
        chunks: list[str] = []
        current: list[str] = []
        for paragraph in paragraphs:
            if self._token_count(paragraph) > self.max_tokens:
                if current:
                    chunks.append("\n\n".join(current))
                    current = []
                chunks.extend(self._window_split(paragraph))
                continue
            candidate = "\n\n".join([*current, paragraph])
            if current and self._token_count(candidate) > self.target_tokens:
                chunks.append("\n\n".join(current))
                current = [paragraph]
            else:
                current.append(paragraph)
        if current:
            tail = "\n\n".join(current)
            if chunks and self._token_count(tail) < self.min_tokens:
                merged = f"{chunks[-1]}\n\n{tail}"
                if self._token_count(merged) <= self.max_tokens:
                    chunks[-1] = merged
                else:
                    chunks.append(tail)
            else:
                chunks.append(tail)
        return chunks

    def _window_split(self, text: str) -> list[str]:
        units = list(TOKEN_PATTERN.finditer(text))
        step = self.max_tokens - self.overlap_tokens
        windows: list[tuple[int, int]] = []
        for start in range(0, len(units), step):
            end = min(start + self.max_tokens, len(units))
            if start >= end:
                break
            if windows and end - start < self.min_tokens and end <= windows[-1][1]:
                break
            windows.append((start, end))
        return [text[units[start].start() : units[end - 1].end()].strip() for start, end in windows]

    @staticmethod
    def token_count(text: str) -> int:
        return len(TOKEN_PATTERN.findall(text))

    @staticmethod
    def _token_count(text: str) -> int:
        return SectionChunker.token_count(text)

    @staticmethod
    def _embedding_text(
        document_title: str, section: ExtractedSection, text: str
    ) -> str:
        section_path = section.section_path or "正文"
        return f"文档：{document_title}\n章节：{section_path}\n正文：{text}"
