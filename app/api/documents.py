"""문서 API — 업로드 / 조회 / 재처리 / 삭제 / 청크 확인.

응답은 전부 프론트 `types.ts` 형식(camelCase, DocStatus)으로 나간다. 변환은 schemas.py 가 담당.
"""
import logging

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, Response, UploadFile

from app import chunk_repo, document_repo, storage
from app.config import settings
from app.ingestion import parser, pipeline, preprocess
from app.ingestion.parser import PdfParseError
from app.models import DocumentMeta, DocumentStatus
from app.schemas import ChunkResponse, DocumentResponse
from app.storage import InvalidPdfError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _get_or_404(document_id: str) -> DocumentMeta:
    doc = document_repo.load(document_id)
    if doc is None:
        raise HTTPException(404, "문서를 찾을 수 없습니다.")
    return doc


# ---------------------------------------------------------------------------
# 업로드 / 조회 / 재처리 / 삭제
# ---------------------------------------------------------------------------
@router.post("", status_code=202, response_model=DocumentResponse, summary="PDF 업로드")
def upload(response: Response, background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """202 Accepted: 파일은 저장됐고 파싱·청킹은 백그라운드에서 진행 중.
    프론트는 GET /api/documents/{id} 를 2~3초마다 폴링해 status 가 ready / error 가 될 때까지 본다.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "PDF 파일만 업로드할 수 있습니다.")

    document_id = storage.new_document_id()
    storage_name = f"{document_id}.pdf"

    # 1) 저장 → 검증 → 해시  (스트림은 한 번만 읽고, 검증은 디스크에서)
    try:
        path = storage.save_pdf(file.file, document_id)
        size = storage.validate_pdf(path, settings.max_file_size)
        file_hash = storage.sha256_of(path)
    except InvalidPdfError as e:
        storage.delete(storage_name)
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001
        storage.delete(storage_name)
        logger.exception("업로드 실패")
        raise HTTPException(500, f"업로드 실패: {e}") from e

    # 2) 같은 내용의 파일이 이미 있으면
    existing = document_repo.find_by_hash(file_hash)
    if existing:
        storage.delete(storage_name)
        if existing.status == DocumentStatus.FAILED:
            # 전에 실패한 문서면 그걸 다시 돌린다 (새 레코드 안 만듦)
            document_repo.update(existing.document_id, DocumentStatus.UPLOADED,
                                 error_message=None, chunk_count=None)
            background_tasks.add_task(pipeline.ingest, existing.document_id)
            logger.info("실패했던 동일 파일 재처리: %s", existing.document_id)
            return DocumentResponse.from_meta(document_repo.load(existing.document_id))
        logger.info("이미 업로드된 동일 파일: %s", existing.document_id)
        response.status_code = 200      # 새로 만든 게 아니므로 202 가 아니라 200
        return DocumentResponse.from_meta(existing)

    # 3) 메타데이터 기록 (모델 생성까지 try 안에 — 여기서 터져도 PDF 를 되돌린다)
    try:
        doc = DocumentMeta(
            document_id=document_id,
            original_name=file.filename,
            storage_name=storage_name,
            file_size=size,
            file_hash=file_hash,
        )
        document_repo.save(doc)
    except Exception as e:  # noqa: BLE001
        storage.delete(storage_name)
        logger.exception("메타데이터 저장 실패")
        raise HTTPException(500, f"메타데이터 저장 실패: {e}") from e

    # 4) 파이프라인 예약 — 응답을 먼저 보내고 뒤에서 돈다.
    #    ※ 디버깅할 땐 이 줄을  pipeline.ingest(document_id)  로 바꾸면 에러가 응답에 바로 뜬다.
    background_tasks.add_task(pipeline.ingest, document_id)

    logger.info("업로드: %s → %s (%d bytes)", file.filename, storage_name, size)
    return DocumentResponse.from_meta(doc)


@router.get("", response_model=list[DocumentResponse], summary="문서 목록 (최신순)")
def list_documents():
    return [DocumentResponse.from_meta(m) for m in document_repo.list_all()]


@router.get("/{document_id}", response_model=DocumentResponse, summary="문서 상태 조회 (폴링용)")
def get_document(document_id: str):
    return DocumentResponse.from_meta(_get_or_404(document_id))


@router.post("/{document_id}/reindex", status_code=202, response_model=DocumentResponse,
             summary="다시 청킹 (chunk_size 바꾼 뒤 등)")
def reindex(document_id: str, background_tasks: BackgroundTasks):
    """원본 PDF 만 있으면 청크는 언제든 재생성할 수 있다는 원칙이 이 API 하나로 구현된다."""
    doc = _get_or_404(document_id)
    if not storage.resolve(doc.storage_name).exists():
        raise HTTPException(409, "원본 PDF가 없어 재처리할 수 없습니다.")
    document_repo.update(document_id, DocumentStatus.UPLOADED, error_message=None, chunk_count=None)
    background_tasks.add_task(pipeline.ingest, document_id)
    return DocumentResponse.from_meta(document_repo.load(document_id))


@router.delete("/{document_id}", status_code=204, summary="문서 삭제 (PDF + 메타 + 청크)")
def delete_document(document_id: str):
    doc = _get_or_404(document_id)
    chunk_repo.delete(document_id)
    storage.delete(doc.storage_name)
    document_repo.delete(document_id)


# ---------------------------------------------------------------------------
# 결과 확인
# ---------------------------------------------------------------------------
@router.get("/{document_id}/chunks", response_model=list[ChunkResponse], summary="청크 조회 (프론트 DocChunk 형식)")
def get_chunks(
    document_id: str,
    page: int | None = Query(None, ge=1, description="이 페이지 청크만"),
):
    doc = _get_or_404(document_id)
    chunks = chunk_repo.load(document_id)
    if chunks is None:
        raise HTTPException(409, f"아직 청킹이 안 됐습니다. 현재 상태: {doc.status.value}")
    if page is not None:
        chunks = [c for c in chunks if c.page_number == page]
    return [ChunkResponse.from_chunk(c, doc.original_name) for c in chunks]


@router.get("/{document_id}/chunk-stats", summary="청킹 품질 통계 (디버깅용)")
def chunk_stats(document_id: str):
    doc = _get_or_404(document_id)
    chunks = chunk_repo.load(document_id)
    if chunks is None:
        raise HTTPException(409, f"아직 청킹이 안 됐습니다. 현재 상태: {doc.status.value}")

    tokens = [c.token_count for c in chunks]
    per_page: dict[int, int] = {}
    for c in chunks:
        per_page[c.page_number] = per_page.get(c.page_number, 0) + 1

    return {
        "documentId": document_id,
        "pageCount": doc.page_count,
        "chunkCount": len(chunks),
        "tokenMin": min(tokens),
        "tokenAvg": round(sum(tokens) / len(tokens), 1),
        "tokenMax": max(tokens),
        "chunksPerPage": dict(sorted(per_page.items())),
        "tinyChunks": sum(1 for t in tokens if t < 40),
        "duplicateChunks": len(chunks) - len({c.content for c in chunks}),
    }


@router.get("/{document_id}/pages", summary="파싱 결과 확인 (디버깅용, 매번 재파싱)")
def get_pages(
    document_id: str,
    page: int | None = Query(None, ge=1, description="이 페이지만 전체 텍스트로"),
    clean: bool = Query(False, description="true 면 전처리 적용 후 텍스트"),
):
    doc = _get_or_404(document_id)
    try:
        page_count, pages = parser.parse_pdf(storage.resolve(doc.storage_name), document_id)
    except PdfParseError as e:
        raise HTTPException(422, str(e)) from e

    scanned = parser.is_scanned(pages)
    if clean:
        pages = preprocess.preprocess(pages)

    if page is not None:
        sel = [p for p in pages if p.page_number == page]
        if not sel:
            raise HTTPException(404, f"페이지 범위 밖: 1~{page_count}")
        return {
            "documentId": document_id, "pageCount": page_count, "scanned": scanned, "clean": clean,
            "page": page, "chars": len(sel[0].text), "text": sel[0].text,
        }

    return {
        "documentId": document_id, "pageCount": page_count, "scanned": scanned, "clean": clean,
        "pages": [{"page": p.page_number, "chars": len(p.text), "preview": p.text[:200]} for p in pages],
    }
