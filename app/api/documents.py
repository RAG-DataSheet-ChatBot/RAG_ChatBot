import logging

from fastapi import APIRouter, File, HTTPException, Response,  UploadFile

from app import document_repo, storage
from app.config import settings
from app.models import DocumentsMeta
from app.storage import InvaidPdfError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])

@router.post("", status_code=201, response_model=DocumentsMeta, summary="문서 업로드 중복시 기존 pdf 반환")
def upload(response: Response, file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "PDF 파일만 업로드 할 수 있습니다.")

    document_id = storage.new_document_id()
    storage_name = f"{document_id}.pdf"

    # 1) 저장 → 검증 → 해시
    try:
        path = storage.save_pdf(file.file, document_id)
        size = storage.validate_pdf(path, settings.max_file_size)
        file_hash = storage.sha256_of(path)
    except InvaidPdfError as e:
        storage.delete(f"{document_id}.pdf")
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        storage.delete(f"{document_id}.pdf")
        logger.exception("업로드 실패")
        raise HTTPException(500, f"업로드 실패: {e}") from e

    # 2) 같은 내용의 파일이 이미 있으면 그걸 돌려준다
    existing = document_repo.find_by_hash(file_hash)
    if existing:
        storage.delete(storage_name)
        logger.info("이미 업로드된 동일 파일: %s",existing.document_id)
        response.status_code = 200       # 새로 만든게 아니므로 201 아닌 200
        return existing

    # 3) 메타데이터 기록 (실패하면 PDF도 되돌린다)
    doc = DocumentsMeta(
        document_id=document_id,
        original_name=file.filename,
        storage_name=storage_name,
        file_size=size,
        file_hash=file_hash,
    )

    try:
        document_repo.save(doc)
    except Exception as e:
        storage.delete(storage_name)
        raise HTTPException(500, f"메타데이터 저장 실패: {e}") from e

    
    logger.info("업로드: %s -> %s (%d bytes)", file.filename, storage_name, size)
    return doc

@router.get("", response_model=list[DocumentsMeta], summary="올라온 문서 전체 목록 (최신순)")
def list_documents():
    return document_repo.list_all()

@router.get("/{document_id}", response_model=DocumentsMeta , summary="문서 하나 조회")
def get_document(document_id: str):
    doc = document_repo.load(document_id)
    if doc is None:
        raise HTTPException(404, "문서를 찾을 수 없습니다.")
    return doc


@router.delete("/{document_id}", status_code=204, summary="PDF 파일 + 메타 JSON 둘 다 삭제")
def delete_document(document_id: str):
    doc = document_repo.load(document_id)
    if doc is None:
        raise HTTPException(404, "문서를 찾을 수 없습니다.")
    storage.delete(doc.storage_name)
    document_repo.delete(document_id)

    