"""2단계 — 텍스트 정제.

문서 '전체'를 받는 것이 핵심이다.
"이 줄이 머리말인가?"는 한 페이지만 봐서는 알 수 없고,
여러 페이지에 같은 줄이 반복되는지를 봐야 알 수 있다.

주의: 문단 경계(\\n\\n)는 반드시 남긴다.
      다음 단계 splitter 가 문단을 1순위 분할 지점으로 쓰기 때문이다.
"""
import logging
import re
import unicodedata
from collections import Counter

from app.ingestion.models import PageText

logger = logging.getLogger(__name__)

EDGE_LINES = 2               # 페이지 상/하단 몇 줄을 header/footer 후보로 볼지
                             #   3으로 올리면 본문 첫 문장까지 후보에 들어가
                             #   구조가 비슷한 페이지에서 본문이 지워진다. 2가 안전선.
REPEAT_RATIO = 0.5           # 전체 페이지의 이 비율 이상 반복되면 header/footer 로 판정
MIN_PAGES_FOR_DETECTION = 5  # 이보다 짧은 문서는 반복 탐지를 하지 않는다
MAX_EDGE_LINE_LEN = 80       # 이보다 긴 줄은 후보에서 제외. 머리말은 거의 항상 짧다.
                             #   없으면 "Table #. Register map" 같은 본문 제목이 오인되어 지워진다.

_ZERO_WIDTH = re.compile("[​-‍﻿]")
_NBSP = re.compile("[ 　]")
_TRAILING_SPACE = re.compile(r"[ \t]+(?=\n)")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
_HYPHEN_BREAK = re.compile(r"([A-Za-z])-\n([a-z])")
_PAGE_NUM_ONLY = re.compile(r"^\s*[-–]?\s*(\d{1,4}|[ivxlcdmIVXLCDM]{1,7})\s*[-–]?\s*$")
_PAGE_LABEL = re.compile(r"^\s*page\s*\d+\s*(of\s*\d+)?\s*$", re.IGNORECASE)
_DIGITS = re.compile(r"\d+")
_WS = re.compile(r"\s+")
# '-----', '=====', '*****' 처럼 장식/구분 목적의 줄. 줄 전체가 장식일 때만 매치한다.
# → 본문 속 '3Pin---NC' 같은 하이픈은 보존된다.
_DECOR_LINE = re.compile(r"^[\s\-=_~*.·•—–+|]{5,}$")


def preprocess(pages: list[PageText]) -> list[PageText]:
    repeated = _detect_repeated_edge_lines(pages)
    if repeated:
        logger.info("반복 header/footer %d종 제거: %s", len(repeated), list(repeated)[:3])
    return [p.with_text(_clean(p.text, repeated)) for p in pages]


def _mask(line: str) -> str:
    """비교용 정규화.

    ① 연속 공백을 한 칸으로 — PDF 추출은 같은 머리말도 페이지마다 내부 띄어쓰기가
       미묘하게 달라진다. 정규화 안 하면 서로 다른 줄로 세어져 탐지가 통째로 실패한다.
    ② 숫자를 # 로 — '3장 서론  12' / '3장 서론  13' 을 같은 것으로.
    """
    return _DIGITS.sub("#", _WS.sub(" ", line).strip())


def _detect_repeated_edge_lines(pages: list[PageText]) -> set[str]:
    if len(pages) < MIN_PAGES_FOR_DETECTION:
        return set()

    counter: Counter[str] = Counter()
    for page in pages:
        if page.is_blank:
            continue
        lines = [ln.strip() for ln in page.text.splitlines() if ln.strip()]
        if not lines:
            continue

        candidates = set(lines[:EDGE_LINES]) | set(lines[-EDGE_LINES:])
        counter.update(
            _mask(c) for c in candidates
            if len(_mask(c)) <= MAX_EDGE_LINE_LEN and not _DECOR_LINE.match(c)
        )

    threshold = max(2, int(len(pages) * REPEAT_RATIO))
    return {line for line, count in counter.items() if count >= threshold}


def _clean(raw: str, repeated_masked: set[str]) -> str:
    if not raw or not raw.strip():
        return ""

    # 한글 자모 분리(NFD) 방지. macOS 를 거친 파일에서 특히 중요하다.
    text = unicodedata.normalize("NFC", raw)

    text = _ZERO_WIDTH.sub("", text)
    text = _NBSP.sub(" ", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 영문 하이픈 줄바꿈 결합: "embed-\nding" → "embedding"
    text = _HYPHEN_BREAK.sub(r"\1\2", text)

    kept = []
    for line in text.split("\n"):
        s = line.strip()
        if _PAGE_NUM_ONLY.match(s):
            continue
        if _PAGE_LABEL.match(s):
            continue
        if _DECOR_LINE.match(s):
            continue
        if s and _mask(s) in repeated_masked:
            continue
        kept.append(line)
    text = "\n".join(kept)

    text = _TRAILING_SPACE.sub("", text)
    text = _MULTI_SPACE.sub(" ", text)
    text = _MULTI_NEWLINE.sub("\n\n", text)   # 문단 경계는 살린다
    return text.strip()
