from dataclasses import dataclass
import tiktoken

from app.doc_pipeline.parsers.base import ParsedBlock
from app.core.logging import get_logger

logger = get_logger(__name__)

_enc = None
_enc_failed = False
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50


@dataclass
class TextChunk:
    text: str
    chunk_index: int
    chunk_type: str
    page_num: int
    section_title: str


def _split_text(text: str) -> list[str]:
    enc = _get_encoding()
    if enc is None:
        return _split_text_fallback(text)

    tokens = enc.encode(text)
    if len(tokens) <= CHUNK_SIZE:
        return [text]

    chunks = []
    start = 0
    while start < len(tokens):
        end = start + CHUNK_SIZE
        chunks.append(_enc.decode(tokens[start:end]))
        if end >= len(tokens):
            break
        start = end - CHUNK_OVERLAP
    return chunks


def _get_encoding():
    global _enc, _enc_failed
    if _enc is not None or _enc_failed:
        return _enc

    try:
        _enc = tiktoken.get_encoding("cl100k_base")
    except Exception as exc:
        _enc_failed = True
        logger.warning("tiktoken_encoding_unavailable", error=str(exc))
        return None

    return _enc


def _split_text_fallback(text: str) -> list[str]:
    if len(text) <= CHUNK_SIZE:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - CHUNK_OVERLAP
    return chunks


def chunk_blocks(blocks: list[ParsedBlock]) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    index = 0

    for block in blocks:
        if block.type in ("table", "title"):
            chunks.append(
                TextChunk(
                    text=block.text,
                    chunk_index=index,
                    chunk_type=block.type,
                    page_num=block.page_num,
                    section_title=block.section_title,
                )
            )
            index += 1
        else:
            for sub_text in _split_text(block.text):
                chunks.append(
                    TextChunk(
                        text=sub_text,
                        chunk_index=index,
                        chunk_type="paragraph",
                        page_num=block.page_num,
                        section_title=block.section_title,
                    )
                )
                index += 1

    return chunks
