"""문서 메타데이터 저장소.  data/documents/{document_id}.json

문서 하나당 파일 하나다. 하나의 index.json 에 전부 넣지 않는 이유:
두 요청이 동시에 같은 파일을 쓰면 한쪽이 덮어써서 문서가 사라진다.
문서별 파일이면 서로 건드릴 일이 없다.
"""
import logging
from pathlib import Path
from typing import Optional

from app.config import settings
from app.models import DocumentMeta, DocumentStatus, utcnow

logger = logging.getLogger(__name__)


def _path(document_id: str) -> Path:
    return settings.document_dir / f"{document_id}.json"


def save(doc: DocumentMeta) -> None:
    """임시 파일에 쓰고 원자적으로 교체한다. 반쯤 쓰인 JSON 은 파싱이 안 돼 문서가 '사라진다'."""
    settings.ensure_dirs()
    target = _path(doc.document_id)
    temp = target.with_name(target.name + ".part")
    temp.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    temp.replace(target)


def load(document_id: str) -> Optional[DocumentMeta]:
    p = _path(document_id)
    if not p.exists():
        return None
    return DocumentMeta.model_validate_json(p.read_text(encoding="utf-8"))


def list_all() -> list[DocumentMeta]:
    settings.ensure_dirs()
    docs: list[DocumentMeta] = []
    for p in settings.document_dir.glob("*.json"):
        try:
            docs.append(DocumentMeta.model_validate_json(p.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            logger.warning("깨진 메타데이터 파일 무시: %s", p.name)
    return sorted(docs, key=lambda d: d.created_at, reverse=True)


def find_by_hash(file_hash: str) -> Optional[DocumentMeta]:
    for d in list_all():
        if d.file_hash == file_hash:
            return d
    return None


def update(document_id: str, status: DocumentStatus, **fields) -> DocumentMeta:
    """상태를 바꾸고 즉시 저장한다. 파이프라인이 단계마다 호출한다."""
    doc = load(document_id)
    if doc is None:
        raise FileNotFoundError(f"문서를 찾을 수 없습니다: {document_id}")
    doc = doc.model_copy(update={"status": status, "updated_at": utcnow(), **fields})
    save(doc)
    return doc


def delete(document_id: str) -> None:
    _path(document_id).unlink(missing_ok=True)
