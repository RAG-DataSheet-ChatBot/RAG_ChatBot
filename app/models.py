""" 문서 메타데이터 모델. """
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

def utcnow() -> datetime :
    return datetime.now(timezone.utc)

class DocumentStatus(str, Enum):
    UPLOADED = "UPLOADED"       # 파일 저장 완료 상태
    EXTRACTING = "EXTRACTING"   # PDF 텍스트 추출 중
    CHUNKING = "CHUNKING"       # 전처리 + 청크 분할 중
    CHUNKED = "CHUNKED"         # 완료 (현재 범위의 끝)

    OCR_REQUIRED = "OCR_REQUIRED" # 스캔 PDF. 에러 아님
    FAILED = "FAIL(ED"           # 그 외 실패

    @property
    def is_terminal(self) -> bool:
        return self in (DocumentStatus.CHUNKED,
                        DocumentStatus.OCR_REQUIRED,
                        DocumentStatus.FAILED)

class DocumentsMeta(BaseModel):
    document_id: str
    original_name: str
    storage_name: str
    file_size: int
    file_hash: str

    status: DocumentStatus = DocumentStatus.UPLOADED
    page_count: Optional[int] = None
    chunk_count: Optional[int] = None
    error_message: Optional[str] = None

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)