"""파이프라인 단계 사이를 오가는 데이터 구조.

PDF → PageText → DocumentChunk → (다음 담당자: 임베딩 → 벡터)

★ page_number 는 여기서 한 번 부여된 뒤 청크 JSON 까지 절대 유실되지 않는다.
  나중에 "이 답변은 17페이지에서 나왔습니다"를 하려면 이게 살아 있어야 한다.
"""
from dataclasses import asdict, dataclass


@dataclass
class PageText:
    document_id: str
    page_number: int      # 사람이 보는 기준. 1부터 시작
    text: str

    @property
    def is_blank(self) -> bool:
        return not self.text or not self.text.strip()

    def with_text(self, new_text: str) -> "PageText":
        return PageText(self.document_id, self.page_number, new_text)


@dataclass
class DocumentChunk:
    chunk_id: str         # "{document_id}-p{page}-c{index}"
    document_id: str
    page_number: int
    chunk_index: int      # 해당 '페이지 안에서의' 순번. 0부터
    content: str
    token_count: int

    @staticmethod
    def build_id(document_id: str, page_number: int, chunk_index: int) -> str:
        """결정론적 ID. 같은 문서를 다시 처리해도 같은 값 → 벡터 DB upsert 시 중복 안 생김."""
        return f"{document_id}-p{page_number}-c{chunk_index}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "DocumentChunk":
        return cls(**d)
