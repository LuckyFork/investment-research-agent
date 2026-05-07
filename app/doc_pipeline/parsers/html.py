from bs4 import BeautifulSoup
from app.doc_pipeline.parsers.base import BaseParser, ParsedBlock


class HtmlParser(BaseParser):
    def parse(self, file_path: str) -> list[ParsedBlock]:
        blocks: list[ParsedBlock] = []
        with open(file_path, encoding="utf-8", errors="replace") as f:
            soup = BeautifulSoup(f.read(), "lxml")

        for tag in soup(["script", "style"]):
            tag.decompose()

        for heading in soup.find_all(["h1", "h2", "h3"]):
            text = heading.get_text(strip=True)
            if text:
                blocks.append(ParsedBlock(type="title", text=text))

        for table in soup.find_all("table"):
            rows = [
                " | ".join(td.get_text(strip=True) for td in row.find_all(["td", "th"]))
                for row in table.find_all("tr")
            ]
            table_text = "\n".join(rows)
            if table_text.strip():
                blocks.append(ParsedBlock(type="table", text=table_text))

        for p in soup.find_all("p"):
            text = p.get_text(strip=True)
            if text:
                blocks.append(ParsedBlock(type="paragraph", text=text))

        return blocks
