"""파이프라인 오케스트레이터.

  PDF → 파싱 → 전처리 → 청킹 → 청크 JSON 저장
  (임베딩 → Chroma 는 다음 담당자)

이 함수는 각 단계를 '호출만' 하고 로직을 갖지 않는다.
그래야 발표 자료의 다이어그램과 코드가 1:1로 대응된다.

상태는 각 단계 시작 '전'에 저장한다.
중간에 서버가 죽으면 어느 단계에서 죽었는지 메타에 남는다.
"""
import logging
import time

from app import chunk_repo, document_repo, storage
from app.config import settings
from app.ingestion import chunker, parser, preprocess
from app.ingestion.parser import PdfParseError
from app.models import DocumentStatus

logger = logging.getLogger(__name__)


def ingest(document_id: str) -> None:
    started = time.time()

    doc = document_repo.load(document_id)
    if doc is None:
        logger.error("[%s] 문서를 찾을 수 없습니다", document_id)
        return
    pdf_path = storage.resolve(doc.storage_name)

    try:
        # ---- 1. 파싱 -----------------------------------------------------
        document_repo.update(document_id, DocumentStatus.EXTRACTING)
        page_count, pages = parser.parse_pdf(pdf_path, document_id)

        if parser.is_scanned(pages):
            document_repo.update(
                document_id, DocumentStatus.OCR_REQUIRED,
                page_count=page_count,
                error_message="텍스트 레이어가 없는 PDF입니다. OCR이 필요합니다.",
            )
            logger.info("[%s] 텍스트 없음 → OCR_REQUIRED", document_id)
            return

        # ---- 2. 전처리 ---------------------------------------------------
        document_repo.update(document_id, DocumentStatus.CHUNKING, page_count=page_count)
        cleaned = preprocess.preprocess(pages)

        # ---- 3. 청킹 -----------------------------------------------------
        chunks = chunker.chunk_pages(cleaned, settings.chunk_size, settings.chunk_overlap)
        if not chunks:
            raise RuntimeError("생성된 청크가 없습니다. 전처리 결과가 비어 있는지 확인하세요.")

        # ---- 4. 저장 -----------------------------------------------------
        chunk_repo.save(document_id, chunks)
        document_repo.update(
            document_id, DocumentStatus.CHUNKED,
            chunk_count=len(chunks), error_message=None,
        )

        logger.info(
            "[%s] 완료: %d페이지 → %d청크, %.1f초",
            document_id, page_count, len(chunks), time.time() - started,
        )

        # ---- 다음 담당자 --------------------------------------------------
        # TODO: 임베딩 → Chroma 저장
        #   chunks 의 content 를 임베딩하고, page_number 를 metadata 에 넣어 저장.
        #   chunk_id 를 벡터 DB 의 id 로 쓰면 재처리 시 upsert 로 중복이 안 생긴다.

    except PdfParseError as e:
        _fail(document_id, str(e))
    except Exception as e:  # noqa: BLE001
        logger.exception("[%s] 파이프라인 실패", document_id)
        _fail(document_id, f"{type(e).__name__}: {e}")


def _fail(document_id: str, message: str) -> None:
    try:
        document_repo.update(document_id, DocumentStatus.FAILED, error_message=message[:2000])
    except Exception:  # noqa: BLE001
        logger.exception("[%s] 실패 상태 기록마저 실패", document_id)
