from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ParsedBlock:
    type: Literal["paragraph", "table", "title"]
    text: str
    page_num: int = 0
    section_title: str = ""


class BaseParser(ABC):
    @abstractmethod
    def parse(self, file_path: str) -> list[ParsedBlock]:
        ...
