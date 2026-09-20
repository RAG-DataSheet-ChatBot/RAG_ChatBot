import logging

from fastapi import FastAPI
from app.config import settings  

from app.api import documents


logging.basicConfig(level=logging.INFO, format="%s(asctime)s %(levelname)-5s [%(name)s]")
app = FastAPI(title="RAG Chatbot")
app.include_router(documents.router)


@app.get("/health")
def health():
    return {"status": "ok",
            "chunkSize": settings.chunk_size,
            "chunkOverlap": settings.chunk_overlap,
            "pdfDir": str(settings.pdf_dir),
            "openaiKeySet": bool(settings.openai_api_key),
            "geminiKeySet": bool(settings.gemini_api_key),
            }
