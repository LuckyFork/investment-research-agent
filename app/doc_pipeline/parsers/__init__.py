from app.doc_pipeline.parsers.base import BaseParser, ParsedBlock
from app.doc_pipeline.parsers.pdf import PdfParser
from app.doc_pipeline.parsers.excel import ExcelParser
from app.doc_pipeline.parsers.html import HtmlParser
from app.doc_pipeline.parsers.txt import TxtParser

_PARSER_MAP: dict[str, type[BaseParser]] = {
    "pdf": PdfParser,
    "xlsx": ExcelParser,
    "xls": ExcelParser,
    "html": HtmlParser,
    "htm": HtmlParser,
    "txt": TxtParser,
}

SUPPORTED_TYPES: frozenset[str] = frozenset(_PARSER_MAP)


def get_parser(file_type: str) -> BaseParser:
    cls = _PARSER_MAP.get(file_type.lower())
    if cls is None:
        raise ValueError(f"Unsupported file type: {file_type}")
    return cls()
