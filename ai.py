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
[Page {chunk["page_number"]}]
{chunk["content"]}
"""

    return context

# 5. Gemini에게 질문

def ask(question, chunks):

    if chunks and isinstance(chunks[0], list):
        chunks = chunks[0]

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

        valid_pages = {chunk["page_number"] for chunk in chunks}

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
    [
        {
            "chunk_id": "dump-p1-c0",
            "document_id": "dump",
            "page_number": 1,
            "chunk_index": 0,
            "content": "---------------------------------------------------------------------------------------------------------------------\n Your specialist in innovating humidity & temperature sensors\nDigital-output relative humidity & temperature sensor/module\nDHT22 (DHT22 also named as AM2302)\n\n Capacitive-type humidity and temperature module/sensor\nThomas Liu (Business Manager)",
            "token_count": 52
        },
        {
            "chunk_id": "dump-p2-c0",
            "document_id": "dump",
            "page_number": 2,
            "chunk_index": 0,
            "content": "---------------------------------------------------------------------------------------------------------------------\n Your specialist in innovating humidity & temperature sensors\n1. Feature & Application:\n* Full range temperature compensated * Relative humidity and temperature measurement\n* Calibrated digital signal *Outstanding long-term stability *Extra components not needed\n* Long transmission distance * Low power consumption *4 pins packaged and fully interchangeable\n2. Description:\nDHT22 output calibrated digital signal. It utilizes exclusive digital-signal-collecting-technique and humidity\nsensing technology, assuring its reliability and stability.Its sensing elements is connected with 8-bit single-chip\ncomputer.\nEvery sensor of this model is temperature compensated and calibrated in accurate calibration chamber and the\ncalibration-coefficient is saved in type of programme in OTP memory, when the sensor is detecting, it will cite\ncoefficient from memory.\nSmall size & low consumption & long transmission distance(20m) enable DHT22 to be suited in all kinds of\nharsh application occasions.\nSingle-row packaged with four pins, making the connection very convenient.\n3. Technical Specification:\nModel DHT22\nPower supply 3.3-6V DC\nOutput signal digital signal via single-bus\nSensing element Polymer capacitor\nOperating range humidity 0-100%RH; temperature -40~80Celsius\nAccuracy humidity +-2%RH(Max +-5%RH); temperature <+-0.5Celsius\nResolution or sensitivity humidity 0.1%RH; temperature 0.1Celsius\nRepeatability humidity +-1%RH; temperature +-0.2Celsius\nHumidity hysteresis +-0.3%RH\nLong-term Stability +-0.5%RH/year\nSensing period Average: 2s\nInterchangeability fully interchangeable\nDimensions small size 14*18*5.5mm; big size 22*28*5mm\n4. Dimensions: (unit----mm)\n 1) Small size dimensions: (unit----mm)\nThomas Liu (Business Manager)",
            "token_count": 407
        },
        {
            "chunk_id": "dump-p3-c0",
            "document_id": "dump",
            "page_number": 3,
            "chunk_index": 0,
            "content": "---------------------------------------------------------------------------------------------------------------------\n Your specialist in innovating humidity & temperature sensors\nThomas Liu (Business Manager)",
            "token_count": 19
        },
        {
            "chunk_id": "dump-p4-c0",
            "document_id": "dump",
            "page_number": 4,
            "chunk_index": 0,
            "content": "---------------------------------------------------------------------------------------------------------------------\n Your specialist in innovating humidity & temperature sensors\n\n Pin sequence number: 1 2 3 4 (from left to right direction).\nPin Function\n 1 VDD----power supply\n 2 DATA--signal\n 3 NULL\n 4 GND\n\nThomas Liu (Business Manager)",
            "token_count": 64
        },
        {
            "chunk_id": "dump-p5-c0",
            "document_id": "dump",
            "page_number": 5,
            "chunk_index": 0,
            "content": "---------------------------------------------------------------------------------------------------------------------\n Your specialist in innovating humidity & temperature sensors\n5. Electrical connection diagram:\n\n 3Pin---NC, AM2302 is another name for DHT22\n6. Operating specifications:\n(1) Power and Pins\nPower's voltage should be 3.3-6V DC. When power is supplied to sensor, don't send any instruction to the sensor\nwithin one second to pass unstable status. One capacitor valued 100nF can be added between VDD and GND for\nwave filtering.\n\n(2) Communication and signal\nSingle-bus data is used for communication between MCU and DHT22, it costs 5mS for single time\ncommunication.\nData is comprised of integral and decimal part, the following is the formula for data.\nDHT22 send out higher data bit firstly!\n DATA=8 bit integral RH data+8 bit decimal RH data+8 bit integral T data+8 bit decimal T data+8 bit check-sum\nIf the data transmission is right, check-sum should be the last 8 bit of \"8 bit integral RH data+8 bit decimal RH\ndata+8 bit integral T data+8 bit decimal T data\".\nWhen MCU send start signal, DHT22 change from low-power-consumption-mode to running-mode. When MCU\nfinishs sending the start signal, DHT22 will send response signal of 40-bit data that reflect the relative humidity\nThomas Liu (Business Manager)",
            "token_count": 297
        },
        {
            "chunk_id": "dump-p6-c0",
            "document_id": "dump",
            "page_number": 6,
            "chunk_index": 0,
            "content": "---------------------------------------------------------------------------------------------------------------------\n Your specialist in innovating humidity & temperature sensors\nand temperature information to MCU. Without start signal from MCU, DHT22 will not give response signal to\nMCU. One start signal for one time's response data that reflect the relative humidity and temperature information\nfrom DHT22. DHT22 will change to low-power-consumption-mode when data collecting finish if it don't receive\nstart signal from MCU again.\n1) Check bellow picture for overall communication process:\n------------------------------------------------------------------------------------------------------------------------------------\n Host computer send out\n start signal. Data transmission finished,\n Sensor send out and RL pull up bus's voltage\n response signal. Output data: 1bit\"0\" for next transmission\n Pull up and wait Host's signal Sensor's signal Output data: 1bit \"1\"\n response from sensor Sensor pull down\n Pull up voltage and get bus's voltage\n ready for sensor's output.\n\nSingle-bus output\n------------------------------------------------------------------------------------------------------------------------------------\n2) Step 1: MCU send out start signal to DHT22\n Data-bus's free status is high voltage level. When communication between MCU and DHT22 begin, program of\nMCU will transform data-bus's voltage level from high to low level and this process must beyond at least 1ms to\nensure DHT22 could detect MCU's signal, then MCU will wait 20-40us for DHT22's response.\n Check bellow picture for step 1:\nThomas Liu (Business Manager)",
            "token_count": 299
        },
        {
            "chunk_id": "dump-p7-c0",
            "document_id": "dump",
            "page_number": 7,
            "chunk_index": 0,
            "content": "---------------------------------------------------------------------------------------------------------------------\n Your specialist in innovating humidity & temperature sensors\n-----------------------------------------------------------------------------------------------------------------------------------\n\n Host computer send start signal Sensor send out response signal\n and keep this signal at least 1ms and keep this signal 80us\n Host pull up voltage\n -and wait sensor's response Sensor pull up bus's voltage\n Signal from host Start data transmission\n Signal from sensor\nSingle-bus signal\n------------------------------------------------------------------------------------------------------------------------------------\n Step 2: DHT22 send response signal to MCU\n When DHT22 detect the start signal, DHT22 will send out low-voltage-level signal and this signal last 80us as\nresponse signal, then program of DHT22 transform data-bus's voltage level from low to high level and last 80us\nfor DHT22's preparation to send data.\n Check bellow picture for step 2:\nThomas Liu (Business Manager)",
            "token_count": 175
        },
        {
            "chunk_id": "dump-p8-c0",
            "document_id": "dump",
            "page_number": 8,
            "chunk_index": 0,
            "content": "---------------------------------------------------------------------------------------------------------------------\n Your specialist in innovating humidity & temperature sensors\n------------------------------------------------------------------------------------------------------------------------------------\n Start transmit 1bit data Start transmit next bit data\n 26-28us voltage-length means data \"0\"\n Host signal Sesnor's signal\n Single-bus signal\n------------------------------------------------------------------------------------------------------------------------------------\n Step 3: DHT22 send data to MCU\n When DHT22 is sending data to MCU, every bit's transmission begin with low-voltage-level that last 50us, the\nfollowing high-voltage-level signal's length decide the bit is \"1\" or \"0\".\n Check bellow picture for step 3:\nThomas Liu (Business Manager)",
            "token_count": 129
        },
        {
            "chunk_id": "dump-p9-c0",
            "document_id": "dump",
            "page_number": 9,
            "chunk_index": 0,
            "content": "---------------------------------------------------------------------------------------------------------------------\n Your specialist in innovating humidity & temperature sensors\n------------------------------------------------------------------------------------------------------------------------------------\n 70us voltage-length means 1bit data \"1\"\n Start transmit 1bit data Start transmit next bit data\n Host signal Sesnor's signal\nSingle-bus signal\n----------------------------------------------------------------------------------------------------------\n If signal from DHT22 is always high-voltage-level, it means DHT22 is not working properly, please check the\nelectrical connection status.\n7. Electrical Characteristics:\nItem Condition Min Typical Max Unit\nPower supply DC 3.3 5 6 V\nCurrent supply Measuring 1 1.5 mA\nStand-by 40 Null 50 uA\nCollecting\nperiod\nSecond 2 Second\n *Collecting period should be : >2 second.\nThomas Liu (Business Manager)",
            "token_count": 161
        },
        {
            "chunk_id": "dump-p10-c0",
            "document_id": "dump",
            "page_number": 10,
            "chunk_index": 0,
            "content": "---------------------------------------------------------------------------------------------------------------------\n Your specialist in innovating humidity & temperature sensors\n8. Attentions of application:\n(1) Operating and storage conditions\n We don't recommend the applying RH-range beyond the range stated in this specification. The DHT22 sensor\ncan recover after working in non-normal operating condition to calibrated status, but will accelerate sensors'\naging.\n(2) Attentions to chemical materials\n Vapor from chemical materials may interfere DHT22's sensitive-elements and debase DHT22's sensitivity.\n(3) Disposal when (1) & (2) happens\n Step one: Keep the DHT22 sensor at condition of Temperature 50~60Celsius, humidity <10%RH for 2 hours;\n Step two: After step one, keep the DHT22 sensor at condition of Temperature 20~30Celsius, humidity\n>70%RH for 5 hours.\n(4) Attention to temperature's affection\n Relative humidity strongly depend on temperature, that is why we use temperature compensation technology to\nensure accurate measurement of RH. But it's still be much better to keep the sensor at same temperature when\nsensing.\n DHT22 should be mounted at the place as far as possible from parts that may cause change to temperature.\n(5) Attentions to light\n Long time exposure to strong light and ultraviolet may debase DHT22's performance.\n(6) Attentions to connection wires\n The connection wires' quality will effect communication's quality and distance, high quality shielding-wire is\nrecommended.\n(7) Other attentions\n * Welding temperature should be bellow 260Celsius.\n * Avoid using the sensor under dew condition.\n * Don't use this product in safety or emergency stop devices or any other occasion that failure of DHT22 may\ncause personal injury.\n\nThomas Liu (Business Manager)",
            "token_count": 373
        }
    ]
]

# 7. 테스트용 질문

question = "동작 전압과 적정 온도를 알려줘"

# 8. 테스트 실행

result = ask(question, chunks)

print("=== AI 챗봇 답변 ===")
print(result)