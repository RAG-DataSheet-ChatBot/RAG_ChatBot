import os

from google import genai
from google.genai.types import GenerateContentConfig
from dotenv import load_dotenv
from pydantic import BaseModel, Field


# 1. API 설정

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

MODEL = "gemini-3.1-flash-lite"

# 2. Gemini가 반환할 JSON 구조

class Source(BaseModel):
    page: int = Field(
        description="답변의 근거가 되는 데이터시트 페이지 번호"
    )


class Answer(BaseModel):
    answer: str = Field(
        description="사용자의 질문에 대한 한국어 답변"
    )

    sources: list[Source] = Field(
        description="답변의 근거가 되는 데이터시트 출처"
    )


class Result(BaseModel):
    answers: list[Answer] = Field(
        description="사용자의 질문에 대한 답변 목록"
    )

# 3. RAG 프롬프트

PROMPT = """
당신은 하드웨어 데이터시트를 분석하는 AI 어시스턴트입니다.

사용자의 질문에 답할 때 반드시 제공된 Context를 근거로 답변하세요.

[중요 규칙]

1. Context에 명시적으로 존재하는 정보만 사용하세요.

2. Context에 없는 정보를 일반적인 지식이나 추측으로 추가하지 마세요.

3. 질문에 대한 정보를 Context에서 찾을 수 없다면
   다음 문장으로 답변하세요.

   "제공된 데이터시트에는 해당 정보가 없습니다."

4. 데이터시트에 있는 숫자와 단위를 임의로 변경하지 마세요.

5. 사용자가 단위 변환을 요청한 경우에만 단위를 변환하세요.

6. 단위 변환을 할 경우 계산 결과를 정확하게 작성하세요.
   예:
   2.3V ~ 5.5V
   → 2300mV ~ 5500mV

7. 데이터시트의 범위와 의미를 변경하지 마세요.
   예를 들어 다음을 서로 혼동하지 마세요.

   - 최소값
   - 최대값
   - 전형값
   - 권장값
   - 동작 범위

8. 데이터시트에 명시되지 않은 권장사항이나 사양을 만들어내지 마세요.

9. 사용자가 여러 가지를 질문한 경우 각각의 내용을 빠뜨리지 말고
   하나의 자연스러운 답변으로 종합하세요.

10. 각 답변의 sources에는 해당 답변의 근거가 되는
    Context의 페이지 번호를 포함하세요.

11. Context에 존재하지 않는 페이지 번호를 만들어내지 마세요.

12. 답변은 한국어로 작성하세요.

13. 답변에 마크다운 문법이나 불필요한 특수기호를 사용하지 마세요.

[Context]
{context}

[사용자 질문]
{question}
"""

# 4. 검색 결과를 Context로 변환

def make_context(chunks):
    context = ""

    for chunk in chunks:
        context += f"""
[Page {chunk["page"]}]
{chunk["text"]}
"""

    return context

# 5. Gemini에게 질문

def ask(question, chunks):

    # 검색 결과가 없으면 Gemini에게 보내지 않는다.
    if not chunks:
        return {
            "answers": [
                {
                    "answer": "제공된 데이터시트에는 해당 정보가 없습니다.",
                    "sources": []
                }
            ]
        }

    # 검색 결과를 Context 형태로 변환
    context = make_context(chunks)

    # 질문과 Context를 PROMPT에 넣는다.
    prompt = PROMPT.format(
        context=context,
        question=question
    )

    try:
        # Gemini API 호출
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=Result,
            ),
        )

        result = response.parsed

        valid_pages = {chunk["page"] for chunk in chunks}

        for answer in result.answers:
            answer.sources = [
                source
                for source in answer.sources
                if source.page in valid_pages
            ]

        return result.model_dump()

    except Exception as e:
        # 구글 서버 통신 에러, 타임아웃 등이 발생했을 때 프로그램이 죽지 않고 안전한 JSON을 반환
        print(f"[Error] Gemini API 호출 중 오류 발생: {e}")
        return {
            "answers": [
                {
                    "answer": "현재 AI 서버 응답이 지연되고 있습니다. 잠시 후 다시 시도해 주세요.",
                    "sources": []
                }
            ]
        }

# ============================================================
# 6. 테스트용 데이터
# ============================================================

chunks = [
    {
        "text": "The DS3231 is a low-cost, extremely accurate I2C real-time clock (RTC).",
        "page": 12
    },
    {
        "text": "Operating temperature range: -40°C to +85°C.",
        "page": 13
    },
    {
        "text": "Operating voltage: 2.3V to 5.5V.",
        "page": 15
    }
]

# 7. 테스트용 질문

question = "동작 전압은?"

# 8. 테스트 실행

result = ask(question, chunks)

print("=== AI 챗봇 답변 ===")
print(result)