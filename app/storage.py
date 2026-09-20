"""pdf 원본 저장"""

import logging
import shutil
import uuid
from pathlib import Path

import hashlib
from app.config import settings

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"

class InvaidPdfError(Exception):
    pass

def new_document_id() -> str:
    return str(uuid.uuid4())

def save_pdf(file_obj, document_id: str) -> Path:
    """ 업로드 스트림을 {uuid}.pdf 로 저장한다. """
    settings.ensure_dirs()
    target = settings.pdf_dir / f"{document_id}.pdf"
    temp = settings.pdf_dir /f"{document_id}.part"

    try:
        with open(temp, "wb") as out:
            shutil.copyfileobj(file_obj, out)
        temp.replace(target)
    except Exception:
        temp.unlink(missing_ok=True)
        raise

    return target

def validate_pdf(path: Path, max_size: int) -> int:
    """저장된 파일을 검증한다. 반환값을 파일 금지"""
    size = path.stat().st_size

    if size == 0:
        raise InvaidPdfError("빈 파일입니다.")
    if size > max_size:
        raise InvaidPdfError("파일이 너무 큽니다. 최대 {max_size // 1024 // 1024}MB")

    with open(path, "rb") as f:
        if f.read(len(PDF_MAGIC)) != PDF_MAGIC:
            raise InvaidPdfError("PDF 형식이 아닙니다.")
    return size

def resolve(storage_name: str) -> Path:
    return settings.pdf_dir / storage_name

def delete(storage_name: str) -> None:
    try:
        resolve(storage_name).unlink(missing_ok=True)
    except OSError as e:
        logger.warning("파일 삭제 실패: %s (%s)", storage_name, e)

def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            digest.update(block)
    return digest.hexdigest()

