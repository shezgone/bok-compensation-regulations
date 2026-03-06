"""
자연어 질문 → Cypher 변환 → Neo4j 실행 → 자연어 답변 파이프라인

Ollama (qwen2.5-coder:14b-instruct) 로컬 모델을 사용하여
한국어 질문을 Cypher로 변환하고, 결과를 자연어로 요약합니다.
"""

import json
import os
import re
import sys
import urllib.request
from typing import Optional

from bok_compensation_neo4j.config import Neo4jConfig
from bok_compensation_neo4j.connection import get_driver

# ── 설정 ──────────────────────────────────────────────────────────
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:14b-instruct")

# ── 그래프 스키마 설명 (Cypher용) ─────────────────────────────────
GRAPH_SCHEMA = """
## Neo4j 그래프 스키마

### 노드 레이블 및 주요 프로퍼티

(:규정 {규정번호, 명칭, 설명, 시행일, 활성여부})
(:조문 {조번호, 항번호?, 조문내용})
(:개정이력 {개정일, 설명})
(:직렬 {직렬코드, 직렬명, 설명})
(:직급 {직급코드, 직급명, 서열})
(:직위 {직위코드, 직위명, 서열})
(:호봉 {호봉번호, 호봉금액, 적용시작일})
(:수당 {수당코드, 수당명, 수당유형, 수당액?, 지급률?, 지급조건, 설명})
(:보수기준 {코드, 명칭, 기본급액, 적용시작일, 설명})
(:직책급기준 {코드, 직책급액, 적용시작일, 설명})
(:상여금기준 {코드, 상여유형, 명칭, 연간지급률?, 지급률?, 설명})
(:연봉차등액기준 {코드, 차등액, 적용시작일, 설명})
(:연봉상한액기준 {코드, 상한액, 적용시작일, 설명})
(:임금피크제기준 {코드, 적용연차, 지급률, 설명})
(:국외본봉기준 {코드, 국가코드, 국가명, 기본급액, 통화단위, 적용시작일, 설명})
(:초임호봉기준 {코드, 초임호봉번호, 설명})
(:평가결과 {평가등급, 평가년도, 승급호봉수, 배분율})

### 관계 (방향: 화살표 방향)

(:규정)-[:규정구성]->(:조문)
(:규정)-[:규정개정]->(:개정이력)
(:직렬)-[:직렬분류]->(:직급)
(:직급)-[:호봉체계구성]->(:호봉)
(:직책급기준)-[:해당직급]->(:직급)
(:직책급기준)-[:해당직위]->(:직위)
(:상여금기준)-[:해당직책구분]->(:직위)
(:상여금기준)-[:해당등급]->(:평가결과)
(:연봉차등액기준)-[:해당직급]->(:직급)
(:연봉차등액기준)-[:해당등급]->(:평가결과)
(:연봉상한액기준)-[:해당직급]->(:직급)
(:국외본봉기준)-[:해당직급]->(:직급)
(:초임호봉기준)-[:대상직렬]->(:직렬)
"""

# ── Few-shot 예시 ─────────────────────────────────────────────────
FEW_SHOT_EXAMPLES = """
### 예시 1
질문: "4급의 호봉 목록을 보여줘"
Cypher:
```cypher
MATCH (g:직급 {직급코드: '4급'})-[:호봉체계구성]->(h:호봉)
RETURN h.호봉번호 AS n, h.호봉금액 AS amt
ORDER BY n
```

### 예시 2
질문: "부서장(가) 1급 직책급은 얼마야?"
Cypher:
```cypher
MATCH (pp:직책급기준)-[:해당직급]->(g:직급 {직급코드: '1급'}),
      (pp)-[:해당직위]->(pos:직위 {직위명: '부서장(가)'})
RETURN pp.직책급액 AS ppay
```

### 예시 3
질문: "3급 직원이 팀장 직책을 맡고 EX 평가를 받은 경우, 본봉·직책급·상여금지급률·연봉차등액·연봉상한액은?"
Cypher:
```cypher
MATCH (grade:직급 {직급코드: '3급'})-[:호봉체계구성]->(step:호봉)
MATCH (pos:직위 {직위명: '팀장'})
MATCH (eval:평가결과 {평가등급: 'EX'})
MATCH (pp:직책급기준)-[:해당직급]->(grade), (pp)-[:해당직위]->(pos)
MATCH (b:상여금기준)-[:해당직책구분]->(pos), (b)-[:해당등급]->(eval)
MATCH (d:연봉차등액기준)-[:해당직급]->(grade), (d)-[:해당등급]->(eval)
MATCH (c:연봉상한액기준)-[:해당직급]->(grade)
RETURN step.호봉번호 AS n, step.호봉금액 AS salary,
       pp.직책급액 AS ppay, b.지급률 AS brate,
       d.차등액 AS diff, c.상한액 AS cap
ORDER BY n DESC
LIMIT 1
```

### 예시 4
질문: "수당 목록을 보여줘"
Cypher:
```cypher
MATCH (a:수당)
RETURN a.수당명 AS name, a.수당유형 AS type
```

### 예시 5
질문: "임금피크제 기본급 지급률은?"
Cypher:
```cypher
MATCH (wp:임금피크제기준)
RETURN wp.적용연차 AS yr, wp.지급률 AS rate
ORDER BY yr
```

### 예시 6
질문: "미국 주재 2급 직원의 국외본봉은?"
Cypher:
```cypher
MATCH (o:국외본봉기준 {국가명: '미국'})-[:해당직급]->(g:직급 {직급코드: '2급'})
RETURN o.기본급액 AS amt, o.통화단위 AS cur
```

### 예시 7
질문: "3급과 4급의 25호봉 본봉 차이는 얼마야?"
Cypher:
```cypher
MATCH (g3:직급 {직급코드: '3급'})-[:호봉체계구성]->(s3:호봉 {호봉번호: 25})
MATCH (g4:직급 {직급코드: '4급'})-[:호봉체계구성]->(s4:호봉 {호봉번호: 25})
RETURN s3.호봉금액 AS amt3, s4.호봉금액 AS amt4, s3.호봉금액 - s4.호봉금액 AS diff
```

### 예시 8
질문: "G5 직원의 초봉은?"
Cypher:
```cypher
MATCH (s:초임호봉기준)-[:대상직렬]->(ct:직렬 {직렬명: '종합기획직원'})
WHERE s.설명 CONTAINS '5급'
WITH s.초임호봉번호 AS n, s.설명 AS desc
MATCH (g:직급 {직급코드: '5급'})-[:호봉체계구성]->(h:호봉 {호봉번호: n})
RETURN n, desc, h.호봉금액 AS salary
```
설명: '초봉/초임호봉'은 초임호봉기준 테이블을 조회한 뒤, 해당 호봉번호로 호봉 테이블을 JOIN하여 금액까지 함께 조회해야 함. 종합기획은 5급(G5)과 6급으로 나뉨.

### 예시 9
질문: "보수규정 개정이력을 알려줘"
Cypher:
```cypher
MATCH (reg:규정)-[:규정개정]->(h:개정이력)
RETURN h.개정일 AS date, h.설명 AS desc
ORDER BY h.개정일
```
"""

# ── 시스템 프롬프트 ───────────────────────────────────────────────
SYSTEM_PROMPT = f"""당신은 한국은행 보수규정 Neo4j DB 전문가입니다.
사용자의 한국어 질문을 Neo4j Cypher READ 쿼리로 변환합니다.

## 규칙
1. MATCH/RETURN만 사용하세요 (CREATE/DELETE/SET 절대 불가).
2. 스키마에 정의된 노드 레이블, 관계 타입, 프로퍼티만 사용하세요.
3. 문자열 비교 시 프로퍼티 매칭 {{직급코드: '3급'}} 또는 WHERE 절을 사용하세요.
4. 결과에 필요한 프로퍼티를 반드시 RETURN에 AS 별칭으로 포함하세요.
5. 응답은 반드시 아래 JSON 형식으로만 출력하세요. 다른 텍스트를 추가하지 마세요.
6. Cypher에서는 산술 연산 (a - b, a + b 등)을 RETURN 절에서 사용할 수 있습니다.
7. Cypher에서는 count(), sum(), avg(), min(), max() 집계 함수를 사용할 수 있습니다.

## DB에 존재하는 실제 데이터 값 (참고)
- 직급코드: '1급', '2급', '3급', '4급', '5급', '6급', '총재', '부총재', '감사', '부총재보', '금통위원', '국장', '부국장', '부장'
- 직위명: '부서장(가)', '부서장(나)', '국소속실장', '부장', '팀장', '조사역', '조사역(C2)', '조사역(C3)', '주임조사역(C1)', '반장'
- 직렬명: '종합기획직원', '일반사무직원', '서무직원', '청원경찰', '별정직원'
- 평가등급: 'EX', 'EE', 'ME', 'BE', '정기'
- 국가명: '미국', '독일', '일본', '영국', '홍콩', '중국'
- 호봉번호: 1~50 (3~6급 각 호봉표 참조)

## 응답 JSON 형식
{{{{
  "cypher": "MATCH ... RETURN ...",
  "explanation": "쿼리 설명 (한국어)"
}}}}

{GRAPH_SCHEMA}

## Few-shot 예시
{FEW_SHOT_EXAMPLES}
"""


# ── Ollama API 호출 ──────────────────────────────────────────────
def call_ollama(prompt: str, system: str = SYSTEM_PROMPT) -> str:
    """Ollama REST API로 모델 호출"""
    payload = json.dumps({
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 2048},
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["message"]["content"]


def extract_json(text: str) -> dict:
    """LLM 응답에서 JSON 블록 추출"""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    raise ValueError(f"JSON을 찾을 수 없습니다:\n{text}")


def nl_to_cypher(question: str) -> dict:
    """자연어 질문 → Cypher + 메타데이터 dict"""
    print(f"\n🔄 LLM에 질문 전송 중... (모델: {MODEL_NAME})")
    raw = call_ollama(question)
    print(f"📝 LLM 원본 응답:\n{raw}\n")
    return extract_json(raw)


# ── Neo4j 실행 ───────────────────────────────────────────────────
def execute_cypher(query: str) -> list:
    """Cypher 쿼리를 Neo4j에서 실행하고 결과를 dict 리스트로 반환"""
    config = Neo4jConfig()
    driver = get_driver(config)

    with driver.session(database=config.database) as session:
        result = session.run(query)
        rows = [dict(record) for record in result]

    driver.close()
    return rows


def format_value(val) -> str:
    """값을 보기 좋게 포맷"""
    if val is None:
        return "-"
    if isinstance(val, float):
        return f"{val:,.0f}"
    if isinstance(val, int):
        return str(val)
    return str(val)


# ── 결과 후처리 가드 ─────────────────────────────────────────────
def _enrich_starting_step(rows: list) -> list:
    """초임호봉번호만 조회되고 호봉금액이 없을 때, 자동으로 호봉 테이블을 JOIN하여 보강.

    LLM이 few-shot 예시를 무시하고 간단한 쿼리를 생성하는 경우 방어.
    """
    if not rows:
        return rows

    # 초임호봉번호가 있지만 salary/호봉금액이 없는 경우만 보강
    sample = rows[0]
    has_hobong_num = any(k in sample for k in ("n", "초임호봉번호", "hobong"))
    has_salary = any(k in sample for k in ("salary", "호봉금액", "amt", "amount"))

    if not has_hobong_num or has_salary:
        return rows

    # 초임호봉번호 키 찾기
    hobong_key = next(k for k in ("n", "초임호봉번호", "hobong") if k in sample)

    # 설명에서 직급 힌트 추출 → 호봉 조회 직급 결정
    desc_val = sample.get("desc", sample.get("설명", ""))
    grade_code = None
    desc_str = str(desc_val)
    # 종합기획직원 직급 패턴
    if "5급" in desc_str or "G5" in desc_str:
        grade_code = "5급"
    elif "6급" in desc_str:
        grade_code = "6급"
    # 일반사무/서무/청원경찰 직렬 패턴
    elif "일반사무" in desc_str:
        grade_code = "GA"
    elif "서무" in desc_str:
        grade_code = "CL"
    elif "청원경찰" in desc_str:
        grade_code = "PO"

    if grade_code is None:
        return rows

    hobong_num = sample[hobong_key]
    if not isinstance(hobong_num, (int, float)):
        return rows
    hobong_num = int(hobong_num)

    print(f"\n🔧 초임호봉 결과 보강: {grade_code} {hobong_num}호봉 금액 조회 중...")
    try:
        config = Neo4jConfig()
        driver = get_driver(config)
        with driver.session(database=config.database) as session:
            result = session.run(
                "MATCH (g:직급 {직급코드: $grade})-[:호봉체계구성]->(h:호봉 {호봉번호: $n}) "
                "RETURN h.호봉금액 AS salary",
                grade=grade_code, n=hobong_num,
            )
            rec = result.single()
        driver.close()

        if rec and rec["salary"] is not None:
            salary = rec["salary"]
            for row in rows:
                row["salary"] = salary
            print(f"   → {hobong_num}호봉 = {salary:,.0f}원 보강 완료")
    except Exception as e:
        print(f"   ⚠️ 보강 실패: {e}")

    return rows


# ── 자연어 답변 생성 ─────────────────────────────────────────────
def generate_answer(question: str, rows: list) -> str:
    """쿼리 결과를 자연어 답변으로 변환 (LLM 사용)"""
    if not rows:
        return "조회 결과가 없습니다."

    result_text = ""
    for i, row in enumerate(rows[:20]):
        parts = []
        for key, val in row.items():
            parts.append(f"{key}={format_value(val)}")
        result_text += f"  행{i+1}: {', '.join(parts)}\n"

    answer_prompt = f"""아래 질문과 DB 조회 결과를 바탕으로, 사용자에게 도움이 되는 한국어 답변을 작성하세요.
금액은 원 단위로, 비율은 %로 표시하세요. 간결하되 핵심 수치를 모두 포함하세요.

❗절대 규칙: 조회 결과에 없는 수치나 금액을 절대 만들어내지 마세요. 조회 결과에 있는 값만 그대로 사용하세요.

질문: {question}

조회 결과 ({len(rows)}건):
{result_text}

답변:"""

    answer_system = "당신은 한국은행 보수규정 전문 비서입니다. 조회 결과를 바탕으로 정확하고 간결한 한국어 답변을 작성합니다."
    return call_ollama(answer_prompt, system=answer_system)


# ── 메인 ─────────────────────────────────────────────────────────
def run(question: str):
    """전체 파이프라인: 자연어 → Cypher → 실행 → 자연어 답변"""
    print("=" * 70)
    print(f"💬 질문: {question}")
    print("=" * 70)

    MAX_RETRIES = 2
    rows = None
    cypher = None
    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        # 1단계: 자연어 → Cypher
        if attempt == 0:
            parsed = nl_to_cypher(question)
        else:
            print(f"\n🔄 재시도 {attempt}/{MAX_RETRIES} — 오류를 LLM에 전달하여 쿼리 수정 중...")
            retry_prompt = f"""이전 질문: {question}

생성했던 Cypher 쿼리:
{cypher}

실행 오류:
{last_error}

위 오류를 수정하여 올바른 Cypher 쿼리를 다시 생성해주세요. 동일한 JSON 형식으로 응답하세요."""
            parsed = nl_to_cypher(retry_prompt)

        cypher = parsed["cypher"]
        explanation = parsed.get("explanation", "")

        print(f"📋 쿼리 설명: {explanation}")
        print(f"\n📌 생성된 Cypher 쿼리:")
        print(f"{'─' * 50}")
        print(cypher)
        print(f"{'─' * 50}")

        # 2단계: Neo4j 실행
        print(f"\n🔍 Neo4j 쿼리 실행 중...")
        try:
            rows = execute_cypher(cypher)
            print(f"✅ {len(rows)}건 조회됨")
            break
        except Exception as e:
            last_error = str(e)
            print(f"❌ 쿼리 실행 오류: {e}")
            if attempt == MAX_RETRIES:
                print(f"\n⛔ {MAX_RETRIES}회 재시도 후에도 실패했습니다.")
                return

    # 결과 후처리: 초임호봉 결과 보강 가드
    rows = _enrich_starting_step(rows)

    # 결과 테이블 출력
    if rows:
        print(f"\n{'─' * 50}")
        print("  [조회 결과]")
        for i, row in enumerate(rows[:20]):
            parts = []
            for key, val in row.items():
                parts.append(f"{key}: {format_value(val)}")
            print(f"  {i+1}. {' | '.join(parts)}")
        if len(rows) > 20:
            print(f"  ... 외 {len(rows) - 20}건")
        print(f"{'─' * 50}")

    # 3단계: 자연어 답변 생성
    print(f"\n🔄 자연어 답변 생성 중...")
    answer = generate_answer(question, rows)

    print(f"\n{'=' * 70}")
    print(f"💡 답변:")
    print(f"{'=' * 70}")
    print(answer)
    print(f"{'=' * 70}")


def main():
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
    else:
        question = "3급 직원이 팀장 직책을 맡고 EX 평가를 받은 경우, 본봉·직책급·상여금지급률·연봉차등액·연봉상한액은?"
    run(question)


if __name__ == "__main__":
    main()
