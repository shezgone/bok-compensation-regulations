"""
자연어 질문 → TypeQL 변환 → TypeDB 실행 → 자연어 답변 파이프라인

Ollama (qwen2.5-coder:14b-instruct) 로컬 모델을 사용하여
한국어 질문을 TypeQL로 변환하고, 결과를 자연어로 요약합니다.
"""

import json
import os
import re
import sys
import urllib.request
from typing import Optional

from typedb.driver import TransactionType
from bok_compensation.config import TypeDBConfig
from bok_compensation.connection import get_driver

# ── 설정 ──────────────────────────────────────────────────────────
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:14b-instruct")

# 스키마 파일 읽기
SCHEMA_PATH = os.path.join(
    os.path.dirname(__file__), os.pardir, os.pardir,
    "schema", "compensation_regulation.tql"
)
with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
    SCHEMA_TEXT = f.read()

# ── Few-shot 예시 ─────────────────────────────────────────────────
FEW_SHOT_EXAMPLES = """
### 예시 1
질문: "4급의 호봉 목록을 보여줘"
TypeQL:
```typeql
match
    $grade isa 직급, has 직급코드 "4급";
    (소속직급: $grade, 구성호봉: $step) isa 호봉체계구성;
    $step has 호봉번호 $n, has 호봉금액 $amt;
sort $n;
```
결과변수: n(호봉번호, integer), amt(호봉금액, double)

### 예시 2
질문: "부서장(가) 1급 직책급은 얼마야?"
TypeQL:
```typeql
match
    $grade isa 직급, has 직급코드 "1급";
    $pos isa 직위, has 직위명 $posname;
    { $posname == "부서장(가)"; };
    (적용기준: $std, 해당직급: $grade, 해당직위: $pos) isa 직책급결정;
    $std has 직책급액 $ppay;
```
결과변수: ppay(직책급액, double)

### 예시 3
질문: "3급 직원이 팀장 직책을 맡고 EX 평가를 받은 경우, 본봉·직책급·상여금지급률·연봉차등액·연봉상한액은?"
TypeQL:
```typeql
match
    $grade isa 직급, has 직급코드 "3급";
    $pos isa 직위, has 직위명 $posname;
    { $posname == "팀장"; };
    $eval isa 평가결과, has 평가등급 "EX";
    (소속직급: $grade, 구성호봉: $step) isa 호봉체계구성;
    $step has 호봉번호 $n, has 호봉금액 $salary;
    (적용기준: $ppstd, 해당직급: $grade, 해당직위: $pos) isa 직책급결정;
    $ppstd has 직책급액 $ppay;
    (적용기준: $bstd, 해당직책구분: $pos, 해당등급: $eval) isa 상여금결정;
    $bstd has 지급률 $brate;
    (적용기준: $dstd, 해당직급: $grade, 해당등급: $eval) isa 연봉차등;
    $dstd has 차등액 $diff;
    (적용기준: $cstd, 해당직급: $grade) isa 연봉상한;
    $cstd has 상한액 $cap;
sort $n desc;
limit 1;
```
결과변수: n(호봉번호, integer), salary(본봉, double), ppay(직책급액, double), brate(지급률, double), diff(차등액, double), cap(상한액, double)

### 예시 4
질문: "수당 목록을 보여줘"
TypeQL:
```typeql
match
    $a isa 수당, has 수당명 $name, has 수당유형 $type;
```
결과변수: name(수당명, string), type(수당유형, string)

### 예시 5
질문: "임금피크제 기본급 지급률은?"
TypeQL:
```typeql
match
    $wp isa 임금피크제기준, has 적용연차 $yr, has 지급률 $rate;
sort $yr;
```
결과변수: yr(적용연차, integer), rate(지급률, double)

### 예시 6
질문: "미국 주재 2급 직원의 국외본봉은?"
TypeQL:
```typeql
match
    $grade isa 직급, has 직급코드 "2급";
    (적용기준: $os, 해당직급: $grade) isa 국외본봉결정;
    $os has 국가명 "미국", has 기본급액 $amt, has 통화단위 $cur;
```
결과변수: amt(기본급액, double), cur(통화단위, string)

### 예시 7
질문: "3급과 4급의 20호봉 본봉 차이는 얼마야?"
설명: TypeQL은 산술연산을 지원하지 않으므로, 두 값을 각각 조회한 뒤 답변 단계에서 차이를 계산합니다.
TypeQL:
```typeql
match
    $g3 isa 직급, has 직급코드 "3급";
    $g4 isa 직급, has 직급코드 "4급";
    (소속직급: $g3, 구성호봉: $s3) isa 호봉체계구성;
    $s3 has 호봉번호 20, has 호봉금액 $amt3;
    (소속직급: $g4, 구성호봉: $s4) isa 호봉체계구성;
    $s4 has 호봉번호 20, has 호봉금액 $amt4;
```
결과변수: amt3(3급 본봉, double), amt4(4급 본봉, double)

### 예시 8
질문: "G5 직원의 초봉은?"
TypeQL:
```typeql
match
    $s isa 직렬, has 직렬명 "종합기획직원";
    (대상직렬: $s, 적용기준: $std) isa 초임호봉결정;
    $std has 초임호봉번호 $n, has 설명 $desc;
    $desc contains "5급";
    $g isa 직급, has 직급코드 "5급";
    (소속직급: $g, 구성호봉: $step) isa 호봉체계구성;
    $step has 호봉번호 $sn, has 호봉금액 $salary;
    $sn == $n;
```
결과변수: n(초임호봉번호, integer), desc(설명, string), salary(호봉금액, double)
참고: '초봉/초임호봉'은 초임호봉기준 테이블을 조회한 뒤, 해당 호봉번호로 호봉 테이블을 JOIN하여 금액까지 함께 조회해야 함. 종합기획은 5급(G5)과 6급으로 나뉨. ⚠️ 초임호봉번호와 호봉번호는 서로 다른 속성 타입이므로 반드시 별도 변수($n, $sn)를 쓰고 $sn == $n으로 비교해야 함.

### 예시 9
질문: "보수규정 개정이력을 알려줘"
TypeQL:
```typeql
match
    $h isa 개정이력, has 개정일 $date, has 설명 $desc;
```
결과변수: date(개정일, datetime), desc(설명, string)
"""

# ── 시스템 프롬프트 ───────────────────────────────────────────────
SYSTEM_PROMPT = f"""당신은 한국은행 보수규정 DB 전문가입니다.
사용자의 한국어 질문을 TypeDB 3.x TypeQL READ 쿼리로 변환합니다.

## 규칙
1. match 절만 사용하세요 (insert/delete 절대 불가).
2. 스키마에 정의된 엔티티, 관계, 속성만 사용하세요.
3. 문자열 비교 시 {{ $var == "값"; }} 패턴을 사용하세요.
4. 결과에 필요한 속성을 반드시 변수로 바인딩하세요.
5. 응답은 반드시 아래 JSON 형식으로만 출력하세요. 다른 텍스트를 추가하지 마세요.
6. **절대 금지**: TypeQL match 절 안에서 산술 연산(`$x = $a - $b`, `$x = $a + $b` 등)을 사용하지 마세요. TypeQL 3.x에서는 match 절 내 산술 연산을 지원하지 않습니다. 비교가 필요하면 두 값을 각각 변수로 조회하고, 답변 단계에서 계산하세요.
7. **절대 금지**: reduce, aggregate, count, sum, min, max 같은 집계 함수를 사용하지 마세요. TypeQL 3.x에서는 지원하지 않습니다.
8. datetime 타입 속성은 type을 "datetime"으로 지정하세요.

## DB에 존재하는 실제 데이터 값 (참고)
- 직급코드: "1급", "2급", "3급", "4급", "5급", "6급", "총재", "부총재", "감사", "부총재보", "금통위원", "국장", "부국장", "부장"
- 직위명: "부서장(가)", "부서장(나)", "국소속실장", "부장", "팀장", "조사역", "조사역(C2)", "조사역(C3)", "주임조사역(C1)", "반장"
- 직렬명: "종합기획직원", "일반사무직원", "서무직원", "청원경찰", "별정직원"
- 평가등급: "EX", "EE", "ME", "BE", "정기"
- 국가명: "미국", "독일", "일본", "영국", "홍콩", "중국"
- 호봉번호: 1~50 (3~6급 각 50호봉)

## 응답 JSON 형식
{{
  "typeql": "match ... ;",
  "variables": [
    {{"name": "변수명", "label": "표시라벨", "type": "integer|double|string"}}
  ],
  "explanation": "쿼리 설명 (한국어)"
}}

## DB 스키마
{SCHEMA_TEXT}

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
    # ```json ... ``` 블록 먼저 시도
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    # 중괄호 직접 탐지
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    raise ValueError(f"JSON을 찾을 수 없습니다:\n{text}")


def nl_to_typeql(question: str) -> dict:
    """자연어 질문 → TypeQL + 메타데이터 dict"""
    print(f"\n🔄 LLM에 질문 전송 중... (모델: {MODEL_NAME})")
    raw = call_ollama(question)
    print(f"📝 LLM 원본 응답:\n{raw}\n")
    return extract_json(raw)


# ── TypeDB 실행 ──────────────────────────────────────────────────
def execute_typeql(query: str, variables: list) -> list:
    """TypeQL 쿼리를 TypeDB에서 실행하고 결과를 dict 리스트로 반환"""
    config = TypeDBConfig()
    driver = get_driver(config)
    tx = driver.transaction(config.database, TransactionType.READ)

    result = tx.query(query).resolve()
    rows = []
    for row in result:
        record = {}
        for var in variables:
            name = var["name"]
            vtype = var.get("type", "string")
            concept = row.get(name)
            if concept is None:
                record[name] = None
                continue
            if vtype == "integer":
                record[name] = concept.get_integer()
            elif vtype == "double":
                record[name] = concept.get_double()
            elif vtype == "datetime":
                # TypeDB datetime → 문자열로 변환
                raw = concept.get_value()
                record[name] = str(raw)[:10] if raw else None
            else:
                record[name] = concept.get_value()
        rows.append(record)

    tx.close()
    driver.close()
    return rows


def format_value(val, vtype: str) -> str:
    """값을 보기 좋게 포맷"""
    if val is None:
        return "-"
    if vtype == "double":
        return f"{val:,.0f}"
    if vtype == "integer":
        return str(val)
    return str(val)


# ── 결과 후처리 가드 ─────────────────────────────────────────────
def _enrich_starting_step(rows: list, variables: list) -> (list, list):
    """초임호봉번호만 조회되고 호봉금액이 없을 때, 자동으로 호봉 테이블을 JOIN하여 보강.

    LLM이 few-shot 예시를 무시하고 간단한 쿼리를 생성하는 경우 방어.
    """
    if not rows:
        return rows, variables

    var_names = {v["name"] for v in variables}
    has_hobong_num = bool(var_names & {"n", "초임호봉번호", "hobong"})
    has_salary = bool(var_names & {"salary", "호봉금액", "amt", "amount"})

    if not has_hobong_num or has_salary:
        return rows, variables

    # 초임호봉번호 키 찾기
    hobong_key = next(k for k in ("n", "초임호봉번호", "hobong") if k in var_names)
    sample = rows[0]

    # 설명에서 직급 힌트 추출
    desc_val = sample.get("desc", sample.get("설명", ""))
    grade_code = None
    if "5급" in str(desc_val) or "G5" in str(desc_val):
        grade_code = "5급"
    elif "6급" in str(desc_val):
        grade_code = "6급"

    if grade_code is None:
        return rows, variables

    hobong_num = sample[hobong_key]
    if not isinstance(hobong_num, (int, float)):
        return rows, variables
    hobong_num = int(hobong_num)

    print(f"\n🔧 초임호봉 결과 보강: {grade_code} {hobong_num}호봉 금액 조회 중...")
    try:
        config = TypeDBConfig()
        driver = get_driver(config)
        tx = driver.transaction(config.database, TransactionType.READ)
        result = tx.query(f"""
            match
                $g isa 직급, has 직급코드 "{grade_code}";
                (소속직급: $g, 구성호봉: $h) isa 호봉체계구성;
                $h has 호봉번호 {hobong_num}, has 호봉금액 $salary;
        """).resolve()
        salary_rows = list(result)
        tx.close()
        driver.close()

        if salary_rows:
            salary = salary_rows[0].get("salary").get_double()
            for row in rows:
                row["salary"] = salary
            variables.append({"name": "salary", "label": "호봉금액", "type": "double"})
            print(f"   → {hobong_num}호봉 = {salary:,.0f}원 보강 완료")
    except Exception as e:
        print(f"   ⚠️ 보강 실패: {e}")

    return rows, variables


# ── 자연어 답변 생성 ─────────────────────────────────────────────
def generate_answer(question: str, variables: list, rows: list) -> str:
    """쿼리 결과를 자연어 답변으로 변환 (LLM 사용)"""
    # 결과 데이터를 텍스트로 정리
    if not rows:
        return "조회 결과가 없습니다."

    result_text = ""
    for i, row in enumerate(rows[:20]):  # 최대 20행
        parts = []
        for var in variables:
            label = var.get("label", var["name"])
            val = format_value(row.get(var["name"]), var.get("type", "string"))
            parts.append(f"{label}={val}")
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
    """전체 파이프라인: 자연어 → TypeQL → 실행 → 자연어 답변"""
    print("=" * 70)
    print(f"💬 질문: {question}")
    print("=" * 70)

    MAX_RETRIES = 2
    rows = None
    typeql = None
    variables = None
    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        # 1단계: 자연어 → TypeQL
        if attempt == 0:
            parsed = nl_to_typeql(question)
        else:
            print(f"\n🔄 재시도 {attempt}/{MAX_RETRIES} — 오류를 LLM에 전달하여 쿼리 수정 중...")
            retry_prompt = f"""이전 질문: {question}

생성했던 TypeQL 쿼리:
{typeql}

실행 오류:
{last_error}

위 오류를 수정하여 올바른 TypeQL 쿼리를 다시 생성해주세요. 동일한 JSON 형식으로 응답하세요."""
            parsed = nl_to_typeql(retry_prompt)

        typeql = parsed["typeql"]
        variables = parsed["variables"]
        explanation = parsed.get("explanation", "")

        print(f"📋 쿼리 설명: {explanation}")
        print(f"\n📌 생성된 TypeQL 쿼리:")
        print(f"{'─' * 50}")
        print(typeql)
        print(f"{'─' * 50}")
        var_labels = ", ".join(f'{v["name"]}({v.get("label", v["name"])})' for v in variables)
        print(f"📊 결과 변수: {var_labels}")

        # 2단계: TypeDB 실행
        print(f"\n🔍 TypeDB 쿼리 실행 중...")
        try:
            rows = execute_typeql(typeql, variables)
            print(f"✅ {len(rows)}건 조회됨")
            break  # 성공 시 루프 탈출
        except Exception as e:
            last_error = str(e)
            print(f"❌ 쿼리 실행 오류: {e}")
            if attempt == MAX_RETRIES:
                print(f"\n⛔ {MAX_RETRIES}회 재시도 후에도 실패했습니다.")
                return

    # 결과 후처리: 초임호봉 결과 보강 가드
    rows, variables = _enrich_starting_step(rows, variables)

    # 결과 테이블 출력
    if rows:
        print(f"\n{'─' * 50}")
        print("  [조회 결과]")
        for i, row in enumerate(rows[:20]):
            parts = []
            for var in variables:
                label = var.get("label", var["name"])
                val = format_value(row.get(var["name"]), var.get("type", "string"))
                parts.append(f"{label}: {val}")
            print(f"  {i+1}. {' | '.join(parts)}")
        if len(rows) > 20:
            print(f"  ... 외 {len(rows) - 20}건")
        print(f"{'─' * 50}")

    # 3단계: 자연어 답변 생성
    print(f"\n🔄 자연어 답변 생성 중...")
    answer = generate_answer(question, variables, rows)

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
