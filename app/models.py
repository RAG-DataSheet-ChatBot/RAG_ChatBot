"""문서 메타데이터 모델."""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DocumentStatus(str, Enum):
    UPLOADED = "UPLOADED"          # 파일 저장 완료, 파이프라인 대기
    EXTRACTING = "EXTRACTING"      # PDF 텍스트 추출 중
    CHUNKING = "CHUNKING"          # 전처리 + 청크 분할 중
    CHUNKED = "CHUNKED"            # 완료 (현재 범위의 끝)

    OCR_REQUIRED = "OCR_REQUIRED"  # 스캔 PDF. 에러 아님
    FAILED = "FAILED"              # 그 외 실패

    @property
    def is_terminal(self) -> bool:
        return self in (DocumentStatus.CHUNKED,
                        DocumentStatus.OCR_REQUIRED,
                        DocumentStatus.FAILED)


class DocumentMeta(BaseModel):
    document_id: str
    original_name: str            # "DHT22.pdf" — 화면 표시용
    storage_name: str             # "c27b69d7-....pdf" — 실제 파일명
    file_size: int
    file_hash: str                # SHA-256. 같은 파일 재업로드 감지

    status: DocumentStatus = DocumentStatus.UPLOADED
    page_count: Optional[int] = None
    chunk_count: Optional[int] = None
    error_message: Optional[str] = None

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
