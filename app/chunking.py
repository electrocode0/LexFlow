from dataclasses import dataclass
import re


@dataclass(frozen=True)
class TextChunk:
    index: int
    text: str
    start_offset: int
    end_offset: int


def chunk_text(text: str, max_chars: int = 500, overlap: int = 80) -> list[TextChunk]:
    if max_chars <= 0 or overlap < 0 or overlap >= max_chars:
        raise ValueError("overlap must be non-negative and smaller than max_chars")
    if not text.strip():
        return []

    paragraphs = [
        (start, start + len(paragraph))
        for start, paragraph in _paragraphs_with_offsets(text)
        if paragraph.strip()
    ]
    chunks: list[TextChunk] = []
    start = paragraphs[0][0]
    final_end = paragraphs[-1][1]
    previous_end = -1

    while start < final_end:
        window_end = min(start + max_chars, final_end)
        paragraph_ends = [
            end for _, end in paragraphs if end > previous_end and end <= window_end
        ]
        end = max(paragraph_ends, default=window_end)
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(TextChunk(len(chunks), chunk, start, end))
        if end >= final_end:
            break
        previous_end = end
        start = end - overlap

    return chunks


def _paragraphs_with_offsets(text: str):
    offset = 0
    for separator in re.finditer(r"\r?\n(?:[ \t]*\r?\n)+", text):
        yield offset, text[offset : separator.start()]
        offset = separator.end()
    yield offset, text[offset:]
