import pdfplumber
from app.doc_pipeline.parsers.base import BaseParser, ParsedBlock


class PdfParser(BaseParser):
    def parse(self, file_path: str) -> list[ParsedBlock]:
        blocks: list[ParsedBlock] = []
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                for table in page.extract_tables():
                    rows = [
                        " | ".join(str(c) if c is not None else "" for c in row)
                        for row in table
                    ]
                    table_text = "\n".join(rows)
                    if table_text.strip():
                        blocks.append(ParsedBlock(type="table", text=table_text, page_num=page_num))

                text = page.extract_text()
                if text and text.strip():
                    blocks.append(ParsedBlock(type="paragraph", text=text.strip(), page_num=page_num))

        return blocks
