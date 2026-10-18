"""API 응답 스키마 — 프론트 `frontend/src/types.ts` 와 1:1 로 맞춘다.

내부 모델(DocumentMeta, DocumentChunk)은 snake_case 로 디스크에 저장되고,
API 로 나갈 때만 여기서 camelCase + 프론트 상태값으로 변환한다.
프론트 타입이 바뀌면 이 파일만 고치면 된다.
"""
from typing import Literal, Optional

from pydantic import BaseModel

from app.ingestion.models import DocumentChunk
from app.models import DocumentMeta, DocumentStatus

# ---------------------------------------------------------------------------
# 상태 매핑  (백엔드 DocumentStatus → 프론트 DocStatus)
# ---------------------------------------------------------------------------
FrontStatus = Literal["parsing", "chunking", "embedding", "ready", "error"]

_STATUS_MAP: dict[DocumentStatus, FrontStatus] = {
    DocumentStatus.UPLOADED: "parsing",       # 접수됨. 프론트 입장에선 '처리 시작'
    DocumentStatus.EXTRACTING: "parsing",
    DocumentStatus.CHUNKING: "chunking",
    DocumentStatus.CHUNKED: "ready",          # 임베딩 단계가 붙으면 "embedding" 으로 바꿀 것
    DocumentStatus.OCR_REQUIRED: "error",     # errorMessage 에 사유가 들어 있음
    DocumentStatus.FAILED: "error",
    # 다음 담당자가 추가할 것:
    #   EMBEDDING → "embedding",  INDEXING → "embedding",  INDEXED → "ready"
}


def to_front_status(status: DocumentStatus) -> FrontStatus:
    return _STATUS_MAP.get(status, "error")


# ---------------------------------------------------------------------------
# 문서  (프론트 SourceDocument)
# ---------------------------------------------------------------------------
class DocumentResponse(BaseModel):
    """프론트 SourceDocument 와 동일. 단, chunks 배열은 내려주지 않는다 —
    목록/폴링마다 청크 본문을 다 보내면 무겁고, 검색은 이제 서버가 하므로 프론트에 필요 없다.
    청크가 필요하면 GET /api/documents/{id}/chunks 를 쓴다.
    """
    id: str
    name: str
    sizeBytes: int
    pageCount: int
    status: FrontStatus
    errorMessage: Optional[str] = None
    chunkCount: int = 0
    # 백엔드 원래 상태도 같이 내려준다. 디버깅용. 프론트는 무시해도 됨
    rawStatus: str

    @classmethod
    def from_meta(cls, m: DocumentMeta) -> "DocumentResponse":
        return cls(
            id=m.document_id,
            name=m.original_name,
            sizeBytes=m.file_size,
            pageCount=m.page_count or 0,
            status=to_front_status(m.status),
            errorMessage=m.error_message,
            chunkCount=m.chunk_count or 0,
            rawStatus=m.status.value,
        )


# ---------------------------------------------------------------------------
# 청크  (프론트 DocChunk — embedding 필드는 제외. 서버가 들고 있을 것)
# ---------------------------------------------------------------------------
class ChunkResponse(BaseModel):
    id: str
    docId: str
    docName: str
    page: int
    text: str
    tokenCount: int

    @classmethod
    def from_chunk(cls, c: DocumentChunk, doc_name: str) -> "ChunkResponse":
        return cls(
            id=c.chunk_id,
            docId=c.document_id,
            docName=doc_name,
            page=c.page_number,
            text=c.content,
            tokenCount=c.token_count,
        )


# ---------------------------------------------------------------------------
# 질의응답  (프론트 Citation / 답변)  — 13단계 담당자가 /api/chat 만들 때 이 형식으로
# ---------------------------------------------------------------------------
class Citation(BaseModel):
    """프론트 Citation 과 동일."""
    chunkId: str
    docName: str
    page: int
    snippet: str        # 청크 본문 앞 200자 정도
    score: float        # 유사도 0~1 (코사인 거리라면 1 - distance)


class ChatRequest(BaseModel):
    question: str
    documentId: Optional[str] = None    # 없으면 전체 문서 대상


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation] = []
