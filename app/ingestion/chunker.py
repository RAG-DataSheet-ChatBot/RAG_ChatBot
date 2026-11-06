"""3단계 — 청크 분할.

★ 이 프로젝트에서 가장 중요한 제약: 청크는 페이지 경계를 넘지 않는다.

  구현은 단순하다. splitter 에 '문서 전체'를 주지 않고
  '페이지 하나씩' 따로 준다. 그러면 구조적으로 경계를 넘을 수 없다.

  이유: 답변 인용 시 페이지가 하나로 확정되어야
        "17페이지에서 확인하세요" + PDF Viewer 페이지 이동이 성립한다.
"""
import logging

import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.ingestion.models import DocumentChunk, PageText

logger = logging.getLogger(__name__)

ENCODING_NAME = "cl100k_base"   # text-embedding-3-small 이 쓰는 토크나이저
_encoding = tiktoken.get_encoding(ENCODING_NAME)


def count_tokens(text: str) -> int:
    return len(_encoding.encode(text))


def _build_splitter(chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
    """토큰 기준 splitter.

    글자 수 기준으로 자르면 안 되는 이유:
      "역전파 알고리즘은..." 26자  → 약 33토큰  (한국어는 글자보다 토큰이 많다)
      "The backpropagation..." 57자 → 약 9토큰   (영어는 글자 ÷ 4)
    같은 '500자'가 언어에 따라 5배 차이 난다.
    """
    return RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=ENCODING_NAME,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        # 앞 구분자부터 우선 시도. 문단 → 줄 → 문장 → 어절 → 글자
        separators=["\n\n", "\n", ". ", "다. ", "? ", "! ", " ", ""],
    )


def chunk_pages(pages: list[PageText], chunk_size: int, chunk_overlap: int) -> list[DocumentChunk]:
    splitter = _build_splitter(chunk_size, chunk_overlap)
    chunks: list[DocumentChunk] = []

    for page in pages:
        if page.is_blank:
            continue

        # ★ 페이지 단위로 따로 호출한다. 이게 페이지 경계 보장의 전부다.
        pieces = splitter.split_text(page.text)

        for index, piece in enumerate(pieces):
            content = piece.strip()
            if not content:
                continue
            chunks.append(DocumentChunk(
                chunk_id=DocumentChunk.build_id(page.document_id, page.page_number, index),
                document_id=page.document_id,
                page_number=page.page_number,
                chunk_index=index,
                content=content,
                token_count=count_tokens(content),
            ))

    if chunks:
        avg = sum(c.token_count for c in chunks) / len(chunks)
        logger.info("청킹: %d개 (평균 %.0f토큰)", len(chunks), avg)
    return chunks
