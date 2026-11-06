"""FastAPI 진입점.

실행:  uv run uvicorn app.main:app --reload
문서:  http://localhost:8000/docs
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import documents
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(
    title="RAG ChatBot",
    description="PDF 업로드 → 파싱 → 전처리 → 청킹 → 청크 JSON 저장",
)

# 프론트가 다른 포트(React 3000, Streamlit 8501)에서 호출할 수 있게
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # 개발용. 배포 시 프론트 주소로 제한
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)


@app.on_event("startup")
def on_startup() -> None:
    settings.ensure_dirs()
    logging.getLogger(__name__).info(
        "기동 | chunk_size=%d overlap=%d | data=%s",
        settings.chunk_size, settings.chunk_overlap, settings.data_dir,
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "chunkSize": settings.chunk_size,
        "chunkOverlap": settings.chunk_overlap,
        "dataDir": str(settings.data_dir),
        "openaiKeySet": bool(settings.openai_api_key),
        "geminiKeySet": bool(settings.gemini_api_key),
    }
