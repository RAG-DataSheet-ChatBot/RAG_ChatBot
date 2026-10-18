"""청크 저장소.  data/chunks/{document_id}.json

다음 담당자(임베딩)가 읽어가는 인수인계 파일이다.

    [
      {
        "chunk_id": "447ed261-...-p2-c0",     ← 벡터 DB 의 id 로 그대로 쓰면 됨
        "document_id": "447ed261-...",
        "page_number": 2,                      ← 반드시 metadata 에 보존할 것
        "chunk_index": 0,
        "content": "1. Feature & Application: ...",   ← 이걸 임베딩
        "token_count": 407
      }
    ]
"""
import json
import logging
from pathlib import Path
from typing import Optional

from app.config import settings
from app.ingestion.models import DocumentChunk

logger = logging.getLogger(__name__)


def _path(document_id: str) -> Path:
    return settings.chunk_dir / f"{document_id}.json"


def save(document_id: str, chunks: list[DocumentChunk]) -> None:
    """임시 파일에 쓰고 원자적으로 교체. 문서 하나당 파일 하나라 재처리하면 덮어써진다."""
    settings.ensure_dirs()
    target = _path(document_id)
    temp = target.with_name(target.name + ".part")
    temp.write_text(
        json.dumps([c.to_dict() for c in chunks], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(target)
    logger.info("[%s] 청크 저장: %d개", document_id, len(chunks))


def load(document_id: str) -> Optional[list[DocumentChunk]]:
    p = _path(document_id)
    if not p.exists():
        return None
    return [DocumentChunk.from_dict(d) for d in json.loads(p.read_text(encoding="utf-8"))]


def delete(document_id: str) -> None:
    _path(document_id).unlink(missing_ok=True)
