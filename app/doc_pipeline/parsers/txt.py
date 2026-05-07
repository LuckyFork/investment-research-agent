from app.doc_pipeline.parsers.base import BaseParser, ParsedBlock


class TxtParser(BaseParser):
    def parse(self, file_path: str) -> list[ParsedBlock]:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        return [ParsedBlock(type="paragraph", text=p) for p in paragraphs]
