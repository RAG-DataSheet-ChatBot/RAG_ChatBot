"""1단계 — PDF → 페이지별 텍스트.

PyPDFLoader 는 페이지 하나당 Document 하나를 돌려준다.
전체를 하나의 문자열로 뽑으면 나중에 페이지 경계를 복원할 방법이 없다.
"""
import logging
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader

from app.ingestion.models import PageText

logger = logging.getLogger(__name__)

# 스캔 PDF 판정 기준
_MIN_AVG_CHARS_PER_PAGE = 30
_MIN_TEXT_PAGE_RATIO = 0.1


class PdfParseError(Exception):
    pass


def parse_pdf(pdf_path: Path, document_id: str) -> tuple[int, list[PageText]]:
    """PDF 를 페이지별 텍스트로 추출한다. 반환: (페이지 수, PageText 리스트)"""
    try:
        docs = PyPDFLoader(str(pdf_path)).load()
    except Exception as e:  # noqa: BLE001
        msg = str(e).lower()
        if "password" in msg or "encrypt" in msg:
            raise PdfParseError("암호로 보호된 PDF입니다. 암호를 해제한 뒤 업로드해 주세요.") from e
        raise PdfParseError(f"PDF를 열 수 없습니다. 파일이 손상되었을 수 있습니다. ({e})") from e

    if not docs:
        raise PdfParseError("페이지가 없는 PDF입니다.")

    # PyPDFLoader 는 순서가 보장되므로 enumerate 로 1-based 를 직접 매긴다.
    # (metadata['page'] 는 0-based 이고 버전에 따라 없을 수도 있다)
    pages = [
        PageText(document_id=document_id, page_number=i + 1, text=doc.page_content or "")
        for i, doc in enumerate(docs)
    ]
    logger.info("[%s] 파싱: %d페이지", document_id, len(pages))
    return len(pages), pages


def is_scanned(pages: list[PageText]) -> bool:
    """텍스트 레이어가 사실상 없는 문서인지 판정.

    평균 글자 수와 '텍스트가 있는 페이지 비율'을 둘 다 본다.
    표지만 텍스트고 본문 전체가 이미지인 PDF 가 흔해서, 평균만 보면 놓친다.
    """
    if not pages:
        return True
    total_chars = sum(len(p.text.strip()) for p in pages)
    pages_with_text = sum(1 for p in pages if len(p.text.strip()) >= _MIN_AVG_CHARS_PER_PAGE)
    avg_chars = total_chars / len(pages)
    text_page_ratio = pages_with_text / len(pages)
    return avg_chars < _MIN_AVG_CHARS_PER_PAGE or text_page_ratio < _MIN_TEXT_PAGE_RATIO
