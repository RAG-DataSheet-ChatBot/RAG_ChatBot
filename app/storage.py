"""PDF 원본 파일 저장.

원본은 Source of Truth. 이것만 있으면 청크는 언제든 재생성할 수 있다.
파일명은 원본 이름 대신 UUID — 충돌 없음, 경로 이탈 불가, OS별 한글 정규화 문제 회피.
"""
import hashlib
import logging
import shutil
import uuid
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"


class InvalidPdfError(Exception):
    pass


def new_document_id() -> str:
    return str(uuid.uuid4())


def save_pdf(file_obj, document_id: str) -> Path:
    """업로드 스트림을 {uuid}.pdf 로 저장한다.

    .part 에 먼저 쓰고 원자적으로 이름을 바꾼다 → 중간에 죽어도 반쪽짜리 .pdf 가 안 남는다.
    """
    settings.ensure_dirs()
    target = settings.pdf_dir / f"{document_id}.pdf"
    temp = settings.pdf_dir / f"{document_id}.part"

    try:
        with open(temp, "wb") as out:
            shutil.copyfileobj(file_obj, out)
        temp.replace(target)
    except Exception:
        temp.unlink(missing_ok=True)
        raise

    return target


def validate_pdf(path: Path, max_size: int) -> int:
    """저장된 파일을 검증한다. 반환값은 파일 크기.

    저장 후에 검사하는 이유: 업로드 스트림은 한 번만 읽는 게 안전하다.
    """
    size = path.stat().st_size

    if size == 0:
        raise InvalidPdfError("빈 파일입니다.")
    if size > max_size:
        raise InvalidPdfError(f"파일이 너무 큽니다. 최대 {max_size // 1024 // 1024}MB")

    # 확장자·Content-Type 은 위조 가능. 파일 내용의 첫 5바이트로 최종 확인.
    with open(path, "rb") as f:
        if f.read(len(PDF_MAGIC)) != PDF_MAGIC:
            raise InvalidPdfError("PDF 형식이 아닙니다.")

    return size


def sha256_of(path: Path) -> str:
    """8KB 씩 끊어 읽어 큰 파일도 메모리에 통째로 안 올린다."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve(storage_name: str) -> Path:
    return settings.pdf_dir / storage_name


def delete(storage_name: str) -> None:
    try:
        resolve(storage_name).unlink(missing_ok=True)
    except OSError as e:
        logger.warning("파일 삭제 실패(고아 파일로 남음): %s (%s)", storage_name, e)
