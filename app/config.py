""" 애플리케이션 설정. .env 파일에서 값을 읽는다."""
from pathlib import Path    

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config =SettingsConfigDict(
        env_file= ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -- 저장 위치 --
    data_dir: Path = Path("./data")
    pdf_dir: Path = Path("./data/pdfs")
    document_dir: Path = Path("./data/documents")
    chunk_dir: Path = Path("./data/chunks")

    # --- 업로드 제한 ---
    max_file_size: int = 50 * 1024 * 1024   # 50MB

    # --- 청킹 (계속 바꿔가며 비교할 값) ---
    chunk_size: int = 600      # 토큰
    chunk_overlap: int = 100   # 토큰

    # --- API 키 (다음 범위에서 사용) ---
    openai_api_key: str = ""
    gemini_api_key: str = ""

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.pdf_dir, self.document_dir, self.chunk_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()