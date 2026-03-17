"""Graph-first natural-language query entrypoint for TypeDB."""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from typedb.driver import TransactionType

from .config import TypeDBConfig
from .connection import get_driver
from .deterministic_executor import try_execute, try_execute_regulation
from .llm import create_chat_model
from .override_resolver import render_article_override_lines, resolve_active_overrides, select_effective_row
from .override_utils import is_effective_on, resolve_effective_date
from .question_validation import extract_step_no, validate_question


SOURCE_TEXT_PATH = Path(__file__).resolve().parents[2] / "extracted_pdf.txt"


def _invoke_text(prompt: str) -> str:
    from langchain_core.messages import HumanMessage

    model = create_chat_model(temperature=0.0)
    response = model.invoke([HumanMessage(content=prompt)])
    return response.content


def _invoke_json(prompt: str) -> Dict[str, Any]:
    from langchain_core.messages import HumanMessage

    model = create_chat_model(temperature=0.0, json_output=True)
    response = model.invoke([HumanMessage(content=prompt)])
    return json.loads(response.content)


def _regex_first(question: str, pattern: str) -> Optional[str]:
    match = re.search(pattern, question, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _sanitize_enum(value: Optional[str], allowed_values: List[str]) -> Optional[str]:
    if value in allowed_values:
        return value
    return None


def _parse_threshold(question: str) -> Optional[float]:
    amount_match = re.search(r"(\d+)\s*만\s*원", question)
    if amount_match:
        return float(amount_match.group(1)) * 10000.0
    plain_match = re.search(r"(\d{1,3}(?:,\d{3})+|\d+)\s*원", question)
    if plain_match:
        return float(plain_match.group(1).replace(",", ""))
    return None


def _normalize_threshold(value: Any, question: str) -> Optional[float]:
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric * 10000.0 if numeric < 10000 else numeric
    if isinstance(value, str):
        parsed = _parse_threshold(value)
        if parsed is not None:
            return parsed
        stripped = value.replace(",", "").strip()
        if stripped.isdigit():
            numeric = float(stripped)
            return numeric * 10000.0 if numeric < 10000 else numeric
    return _parse_threshold(question)


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _determine_hop_depth(question: str, entities: Dict[str, Any]) -> int:
    topics = set(entities.get("topics") or [])
    override_markers = ("부칙", "대체", "경과조치", "우선 적용", "우선적용", "개정")
    if any(marker in question for marker in override_markers) or "부칙" in topics:
        return 3
    if entities.get("article_no") is not None and topics.issubset({"조문"}):
        return 1
    if not topics and entities.get("article_no") is not None:
        return 1
    return 2


def extract_entities(question: str) -> Dict[str, Any]:
    prompt = f"""당신은 한국은행 보수규정 Graph RAG용 엔티티 추출기입니다.
질문에서 주요 엔티티와 탐색 토픽만 추출하세요.

반드시 아래 JSON 형식으로만 답하세요.
{{
  "grade": "",
  "position": "",
  "eval": "",
  "country": "",
  "track": "",
  "article_no": null,
  "topics": [],
  "keyword": "",
  "amount_threshold": null
}}

topics 예시:
- 연봉차등
- 연봉상한
- 직책급
- 상여금
- 임금피크제
- 본봉
- 보수
- 호봉
- 초임호봉
- 국외본봉
- 조문
- 부칙

질문: {question}
"""
    try:
        entities = _invoke_json(prompt)
    except Exception:
        entities = {}

    grade = entities.get("grade") or _regex_first(question, r"\b([1-6]급|G[1-5])\b")
    eval_grade = _sanitize_enum(entities.get("eval"), ["EX", "EE", "ME", "BE", "NI"]) or _regex_first(question, r"\b(EX|EE|ME|BE|NI)\b")
    article_no = entities.get("article_no")
    if article_no is None:
        article_match = _regex_first(question, r"제\s*(\d+)\s*조")
        article_no = int(article_match) if article_match else None

    topics = list(entities.get("topics") or [])
    detected_position = _sanitize_enum(entities.get("position"), ["총재", "위원", "부총재", "부총재보", "감사", "팀장", "부장", "반장", "부서장(가)", "부서장(나)"])
    if not detected_position:
        detected_position = next(
            (
                name
                for name in ["총재", "위원", "부총재", "부총재보", "감사", "팀장", "부장", "반장"]
                if name in question
            ),
            None,
        )
    keyword_map = {
        "연봉차등": ("차등", "차등액", "연봉차등"),
        "연봉상한": ("상한", "연봉상한"),
        "직책급": ("직책급",),
        "상여금": ("상여금", "평가상여금", "정기상여금"),
        "임금피크제": ("임금피크", "피크제", "임금피크제", "기본급지급률"),
        "본봉": ("본봉", "연간 본봉", "기본급"),
        "보수": ("보수",),
        "호봉": ("호봉",),
        "초임호봉": ("초봉", "초임"),
        "국외본봉": ("국외", "해외", "주재"),
        "조문": ("조문", "규정", "부칙", "가능", "대상", "해석"),
        "부칙": ("부칙", "대체", "경과조치"),
    }
    for topic, markers in keyword_map.items():
        if any(marker in question for marker in markers):
            topics.append(topic)

    return {
        "grade": grade,
        "position": detected_position,
        "eval": eval_grade,
        "country": _sanitize_enum(entities.get("country"), ["미국", "독일", "일본", "영국", "홍콩", "중국"]) or next((name for name in ["미국", "독일", "일본", "영국", "홍콩", "중국"] if name in question), None),
        "track": _sanitize_enum(entities.get("track"), ["종합기획직원", "전문직원", "일반기능직원"]) or ("종합기획직원" if "종합기획" in question or "G" in question else None),
        "step_no": extract_step_no(question),
        "article_no": article_no,
        "topics": _dedupe(topics),
        "keyword": entities.get("keyword") or question,
        "amount_threshold": _normalize_threshold(entities.get("amount_threshold"), question),
        "effective_date": resolve_effective_date(question).isoformat(),
    }


def _execute_rows(typeql: str, variables: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    config = TypeDBConfig()
    driver = get_driver(config)
    tx = None
    rows: List[Dict[str, Any]] = []
    try:
        tx = driver.transaction(config.database, TransactionType.READ)
        result = tx.query(typeql).resolve()
        for row in result:
            record: Dict[str, Any] = {}
            for variable in variables:
                name = variable["name"]
                concept = row.get(name)
                if concept is None:
                    record[name] = None
                elif variable.get("type") == "integer":
                    record[name] = concept.get_integer()
                elif variable.get("type") == "double":
                    record[name] = concept.get_double()
                else:
                    record[name] = concept.get_value()
            rows.append(record)
        return rows
    finally:
        if tx is not None:
            tx.close()
        driver.close()


def _merge_override_end_rows(
    rows: List[Dict[str, Any]],
    end_rows: List[Dict[str, Any]],
    key_names: List[str],
) -> List[Dict[str, Any]]:
    end_map = {
        tuple(row.get(key) for key in key_names): row.get("end")
        for row in end_rows
    }
    return [
        {**row, "end": end_map.get(tuple(row.get(key) for key in key_names))}
        for row in rows
    ]


class _TypeDBDeterministicProvider:
    def get_step_amount(self, grade: str, step_no: int) -> Optional[float]:
        rows = _execute_rows(
            f'''
match
    $g isa 직급, has 직급코드 "{grade}";
    (소속직급: $g, 구성호봉: $h) isa 호봉체계구성;
    $h has 호봉번호 {int(step_no)}, has 호봉금액 $amount;
'''.strip(),
            [{"name": "amount", "type": "double"}],
        )
        return float(rows[0]["amount"]) if rows and rows[0].get("amount") is not None else None

    def get_starting_salary(self, track: Optional[str], grade_hint: Optional[str]) -> Optional[Dict[str, Any]]:
        if not track:
            return None
        desc_filter = f'$desc contains "{grade_hint}";' if grade_hint else ''
        rows = _execute_rows(
            f'''
match
    $s isa 직렬, has 직렬명 "{track}";
    (대상직렬: $s, 적용기준: $std) isa 초임호봉결정;
    $std has 초임호봉번호 $step_no, has 초임호봉기준설명 $desc;
    {desc_filter}
'''.strip(),
            [
                {"name": "step_no", "type": "integer"},
                {"name": "desc", "type": "string"},
            ],
        )
        if not rows:
            return None
        if not grade_hint and len(rows) != 1:
            return None
        row = rows[0]
        salary_grade = grade_hint
        if salary_grade is None:
            match = re.search(r"([1-6]급)", str(row.get("desc") or ""))
            salary_grade = match.group(1) if match else None
        if salary_grade is None:
            return None
        return {"step_no": int(row["step_no"]), "salary_grade": salary_grade, "desc": row.get("desc") or ""}

    def _get_salary_diff_override_amount(self, grade: str, eval_grade: str, effective_date: Optional[str]) -> Optional[float]:
        if not effective_date:
            return None
        override_rows = _execute_rows(
            f'''
match
    $b isa 부칙, has 부칙조번호 $buchik_jo, has 부칙내용 $content, has 우선순위 $priority;
    $g isa 직급, has 직급코드 "{grade}";
    $ev isa 평가결과, has 평가등급 "{eval_grade}";
    $d isa 연봉차등액기준, has 연봉차등액코드 $base_code;
    (적용기준: $d, 해당직급: $g, 해당등급: $ev) isa 연봉차등;
    (대체규정: $b, 피대체대상: $d) isa 규정_대체,
        has 대체사유 $reason,
        has 대체시행일 $start;
'''.strip(),
            [
                {"name": "buchik_jo", "type": "integer"},
                {"name": "content", "type": "string"},
                {"name": "priority", "type": "integer"},
                {"name": "base_code", "type": "string"},
                {"name": "reason", "type": "string"},
                {"name": "start", "type": "datetime"},
            ],
        )
        override_rows_with_end = _execute_rows(
            f'''
match
    $b isa 부칙, has 부칙조번호 $buchik_jo;
    $g isa 직급, has 직급코드 "{grade}";
    $ev isa 평가결과, has 평가등급 "{eval_grade}";
    $d isa 연봉차등액기준, has 연봉차등액코드 $base_code;
    (적용기준: $d, 해당직급: $g, 해당등급: $ev) isa 연봉차등;
    (대체규정: $b, 피대체대상: $d) isa 규정_대체,
        has 대체사유 $reason,
        has 대체시행일 $start,
        has 대체만료일 $end;
'''.strip(),
            [
                {"name": "buchik_jo", "type": "integer"},
                {"name": "base_code", "type": "string"},
                {"name": "reason", "type": "string"},
                {"name": "start", "type": "datetime"},
                {"name": "end", "type": "datetime"},
            ],
        )
        combined_rows = _merge_override_end_rows(
            override_rows,
            override_rows_with_end,
            ["buchik_jo", "base_code", "reason", "start"],
        )
        resolution = resolve_active_overrides(
            combined_rows,
            effective_date=effective_date,
            dedupe_keys=["buchik_jo", "base_code", "reason"],
        )
        if not resolution.applied:
            return None
        rows = _execute_rows(
            f'''
match
    $g isa 직급, has 직급코드 "{grade}";
    $ev isa 평가결과, has 평가등급 "{eval_grade}";
    $d isa 연봉차등액기준, has 연봉차등액코드 $code, has 차등액 $amount;
    (적용기준: $d, 해당직급: $g, 해당등급: $ev) isa 연봉차등;
    $code contains "ADIFF";
'''.strip(),
            [{"name": "code", "type": "string"}, {"name": "amount", "type": "double"}],
        )
        row = select_effective_row(rows, effective_date=effective_date, dedupe_keys=["code", "start"])
        return float(row["amount"]) if row and row.get("amount") is not None else None

    def _get_salary_cap_override_amount(self, grade: str, effective_date: Optional[str]) -> Optional[float]:
        if not effective_date:
            return None
        override_rows = _execute_rows(
            f'''
match
    $b isa 부칙, has 부칙조번호 $buchik_jo, has 우선순위 $priority;
    $g isa 직급, has 직급코드 "{grade}";
    $cap isa 연봉상한액기준, has 연봉상한액코드 $base_code;
    (적용기준: $cap, 해당직급: $g) isa 연봉상한;
    (대체규정: $b, 피대체대상: $cap) isa 규정_대체,
        has 대체사유 $reason,
        has 대체시행일 $start;
'''.strip(),
            [
                {"name": "buchik_jo", "type": "integer"},
                {"name": "priority", "type": "integer"},
                {"name": "base_code", "type": "string"},
                {"name": "reason", "type": "string"},
                {"name": "start", "type": "datetime"},
            ],
        )
        override_end_rows = _execute_rows(
            f'''
match
    $b isa 부칙, has 부칙조번호 $buchik_jo;
    $g isa 직급, has 직급코드 "{grade}";
    $cap isa 연봉상한액기준, has 연봉상한액코드 $base_code;
    (적용기준: $cap, 해당직급: $g) isa 연봉상한;
    (대체규정: $b, 피대체대상: $cap) isa 규정_대체,
        has 대체사유 $reason,
        has 대체시행일 $start,
        has 대체만료일 $end;
'''.strip(),
            [
                {"name": "buchik_jo", "type": "integer"},
                {"name": "base_code", "type": "string"},
                {"name": "reason", "type": "string"},
                {"name": "start", "type": "datetime"},
                {"name": "end", "type": "datetime"},
            ],
        )
        combined_rows = _merge_override_end_rows(
            override_rows,
            override_end_rows,
            ["buchik_jo", "base_code", "reason", "start"],
        )
        resolution = resolve_active_overrides(
            combined_rows,
            effective_date=effective_date,
            dedupe_keys=["buchik_jo", "base_code", "reason"],
        )
        if not resolution.applied:
            return None
        rows = _execute_rows(
            f'''
match
    $g isa 직급, has 직급코드 "{grade}";
    $cap isa 연봉상한액기준, has 연봉상한액코드 $code, has 연봉상한액 $amount, has 연봉상한적용시작일 $start;
    (적용기준: $cap, 해당직급: $g) isa 연봉상한;
    $code contains "ACAP";
'''.strip(),
            [
                {"name": "code", "type": "string"},
                {"name": "amount", "type": "double"},
                {"name": "start", "type": "datetime"},
            ],
        )
        row = select_effective_row(rows, effective_date=effective_date, dedupe_keys=["code", "start"])
        return float(row["amount"]) if row and row.get("amount") is not None else None

    def _get_position_pay_override_amount(self, grade: str, position: str, effective_date: Optional[str]) -> Optional[float]:
        if not effective_date:
            return None
        override_rows = _execute_rows(
            f'''
match
    $b isa 부칙, has 부칙조번호 $buchik_jo, has 우선순위 $priority;
    $g isa 직급, has 직급코드 "{grade}";
    $pos isa 직위, has 직위명 $posname;
    {{ $posname == "{position}"; }};
    $pp isa 직책급기준, has 직책급코드 $base_code;
    (적용기준: $pp, 해당직급: $g, 해당직위: $pos) isa 직책급결정;
    (대체규정: $b, 피대체대상: $pp) isa 규정_대체,
        has 대체사유 $reason,
        has 대체시행일 $start;
'''.strip(),
            [
                {"name": "buchik_jo", "type": "integer"},
                {"name": "priority", "type": "integer"},
                {"name": "base_code", "type": "string"},
                {"name": "reason", "type": "string"},
                {"name": "start", "type": "datetime"},
            ],
        )
        override_end_rows = _execute_rows(
            f'''
match
    $b isa 부칙, has 부칙조번호 $buchik_jo;
    $g isa 직급, has 직급코드 "{grade}";
    $pos isa 직위, has 직위명 $posname;
    {{ $posname == "{position}"; }};
    $pp isa 직책급기준, has 직책급코드 $base_code;
    (적용기준: $pp, 해당직급: $g, 해당직위: $pos) isa 직책급결정;
    (대체규정: $b, 피대체대상: $pp) isa 규정_대체,
        has 대체사유 $reason,
        has 대체시행일 $start,
        has 대체만료일 $end;
'''.strip(),
            [
                {"name": "buchik_jo", "type": "integer"},
                {"name": "base_code", "type": "string"},
                {"name": "reason", "type": "string"},
                {"name": "start", "type": "datetime"},
                {"name": "end", "type": "datetime"},
            ],
        )
        combined_rows = _merge_override_end_rows(
            override_rows,
            override_end_rows,
            ["buchik_jo", "base_code", "reason", "start"],
        )
        resolution = resolve_active_overrides(
            combined_rows,
            effective_date=effective_date,
            dedupe_keys=["buchik_jo", "base_code", "reason"],
        )
        if not resolution.applied:
            return None
        rows = _execute_rows(
            f'''
match
    $g isa 직급, has 직급코드 "{grade}";
    $pos isa 직위, has 직위명 $posname;
    {{ $posname == "{position}"; }};
    $pp isa 직책급기준, has 직책급코드 $code, has 직책급액 $amount, has 직책급적용시작일 $start;
    (적용기준: $pp, 해당직급: $g, 해당직위: $pos) isa 직책급결정;
    $code contains "APP-";
'''.strip(),
            [
                {"name": "code", "type": "string"},
                {"name": "amount", "type": "double"},
                {"name": "start", "type": "datetime"},
            ],
        )
        row = select_effective_row(rows, effective_date=effective_date, dedupe_keys=["code", "start"])
        return float(row["amount"]) if row and row.get("amount") is not None else None

    def _get_bonus_rate_override_value(self, position: str, eval_grade: str, effective_date: Optional[str]) -> Optional[float]:
        if not effective_date:
            return None
        override_rows = _execute_rows(
            f'''
match
    $b isa 부칙, has 부칙조번호 $buchik_jo, has 우선순위 $priority;
    $pos isa 직위, has 직위명 $posname;
    {{ $posname == "{position}"; }};
    $ev isa 평가결과, has 평가등급 "{eval_grade}";
    $bonus isa 상여금기준, has 상여금코드 $base_code;
    (적용기준: $bonus, 해당직책구분: $pos, 해당등급: $ev) isa 상여금결정;
    (대체규정: $b, 피대체대상: $bonus) isa 규정_대체,
        has 대체사유 $reason,
        has 대체시행일 $start;
'''.strip(),
            [
                {"name": "buchik_jo", "type": "integer"},
                {"name": "priority", "type": "integer"},
                {"name": "base_code", "type": "string"},
                {"name": "reason", "type": "string"},
                {"name": "start", "type": "datetime"},
            ],
        )
        override_end_rows = _execute_rows(
            f'''
match
    $b isa 부칙, has 부칙조번호 $buchik_jo;
    $pos isa 직위, has 직위명 $posname;
    {{ $posname == "{position}"; }};
    $ev isa 평가결과, has 평가등급 "{eval_grade}";
    $bonus isa 상여금기준, has 상여금코드 $base_code;
    (적용기준: $bonus, 해당직책구분: $pos, 해당등급: $ev) isa 상여금결정;
    (대체규정: $b, 피대체대상: $bonus) isa 규정_대체,
        has 대체사유 $reason,
        has 대체시행일 $start,
        has 대체만료일 $end;
'''.strip(),
            [
                {"name": "buchik_jo", "type": "integer"},
                {"name": "base_code", "type": "string"},
                {"name": "reason", "type": "string"},
                {"name": "start", "type": "datetime"},
                {"name": "end", "type": "datetime"},
            ],
        )
        combined_rows = _merge_override_end_rows(
            override_rows,
            override_end_rows,
            ["buchik_jo", "base_code", "reason", "start"],
        )
        resolution = resolve_active_overrides(
            combined_rows,
            effective_date=effective_date,
            dedupe_keys=["buchik_jo", "base_code", "reason"],
        )
        if not resolution.applied:
            return None
        rows = _execute_rows(
            f'''
match
    $pos isa 직위, has 직위명 $posname;
    {{ $posname == "{position}"; }};
    $ev isa 평가결과, has 평가등급 "{eval_grade}";
    $bonus isa 상여금기준, has 상여금코드 $code, has 상여금지급률 $rate, has 상여금적용시작일 $start;
    (적용기준: $bonus, 해당직책구분: $pos, 해당등급: $ev) isa 상여금결정;
    $code contains "ABONUS";
'''.strip(),
            [
                {"name": "code", "type": "string"},
                {"name": "rate", "type": "double"},
                {"name": "start", "type": "datetime"},
            ],
        )
        if not rows:
            rows = _execute_rows(
                f'''
match
    $pos isa 직위, has 직위명 $posname;
    {{ $posname == "{position}"; }};
    $ev isa 평가결과, has 평가등급 "{eval_grade}";
    $bonus isa 상여금기준, has 상여금코드 $code, has 상여금지급률 $rate;
    (적용기준: $bonus, 해당직책구분: $pos, 해당등급: $ev) isa 상여금결정;
    $code contains "ABONUS";
'''.strip(),
                [
                    {"name": "code", "type": "string"},
                    {"name": "rate", "type": "double"},
                ],
            )
        row = select_effective_row(rows, effective_date=effective_date, dedupe_keys=["code", "start"])
        return float(row["rate"]) if row and row.get("rate") is not None else None

    def get_salary_diff(self, grade: str, eval_grade: str, effective_date: Optional[str] = None) -> Optional[float]:
        override_amount = self._get_salary_diff_override_amount(grade, eval_grade, effective_date)
        if override_amount is not None:
            return override_amount
        rows = _execute_rows(
            f'''
match
    $g isa 직급, has 직급코드 "{grade}";
    $ev isa 평가결과, has 평가등급 "{eval_grade}";
    (적용기준: $d, 해당직급: $g, 해당등급: $ev) isa 연봉차등;
    $d has 차등액 $amount;
'''.strip(),
            [{"name": "amount", "type": "double"}],
        )
        return float(rows[0]["amount"]) if rows and rows[0].get("amount") is not None else None

    def list_salary_diffs(self, minimum_amount: Optional[float] = None, effective_date: Optional[str] = None) -> List[Dict[str, Any]]:
        threshold_clause = f'$amount >= {float(minimum_amount)};' if minimum_amount is not None else ''
        if effective_date:
            override_rows = _execute_rows(
                '''
match
    $b isa 부칙, has 부칙조번호 $buchik_jo, has 우선순위 $priority;
    $g isa 직급, has 직급코드 $grade;
    $ev isa 평가결과, has 평가등급 $eval;
    $d isa 연봉차등액기준, has 연봉차등액코드 $base_code;
    (적용기준: $d, 해당직급: $g, 해당등급: $ev) isa 연봉차등;
    (대체규정: $b, 피대체대상: $d) isa 규정_대체,
        has 대체사유 $reason,
        has 대체시행일 $start;
'''.strip(),
                [
                    {"name": "buchik_jo", "type": "integer"},
                    {"name": "priority", "type": "integer"},
                    {"name": "grade", "type": "string"},
                    {"name": "eval", "type": "string"},
                    {"name": "base_code", "type": "string"},
                    {"name": "reason", "type": "string"},
                    {"name": "start", "type": "datetime"},
                ],
            )
            override_end_rows = _execute_rows(
                '''
match
    $b isa 부칙, has 부칙조번호 $buchik_jo;
    $g isa 직급, has 직급코드 $grade;
    $ev isa 평가결과, has 평가등급 $eval;
    $d isa 연봉차등액기준, has 연봉차등액코드 $base_code;
    (적용기준: $d, 해당직급: $g, 해당등급: $ev) isa 연봉차등;
    (대체규정: $b, 피대체대상: $d) isa 규정_대체,
        has 대체사유 $reason,
        has 대체시행일 $start,
        has 대체만료일 $end;
'''.strip(),
                [
                    {"name": "buchik_jo", "type": "integer"},
                    {"name": "grade", "type": "string"},
                    {"name": "eval", "type": "string"},
                    {"name": "base_code", "type": "string"},
                    {"name": "reason", "type": "string"},
                    {"name": "start", "type": "datetime"},
                    {"name": "end", "type": "datetime"},
                ],
            )
            end_map = {
                (row["buchik_jo"], row["grade"], row["eval"], row["base_code"], row["reason"], row["start"]): row.get("end")
                for row in override_end_rows
            }
            combined_rows = []
            for row in override_rows:
                combined_rows.append({
                    **row,
                    "end": end_map.get((row["buchik_jo"], row["grade"], row["eval"], row["base_code"], row["reason"], row["start"])),
                })
            resolution = resolve_active_overrides(
                combined_rows,
                effective_date=effective_date,
                dedupe_keys=["buchik_jo", "grade", "eval", "base_code", "reason"],
            )
            if resolution.applied:
                override_threshold_clause = f'$amount >= {float(minimum_amount)};' if minimum_amount is not None else ''
                rows = _execute_rows(
                    f'''
match
    $g isa 직급, has 직급코드 $grade;
    $ev isa 평가결과, has 평가등급 $eval;
    $d isa 연봉차등액기준, has 연봉차등액코드 $code, has 차등액 $amount;
    (적용기준: $d, 해당직급: $g, 해당등급: $ev) isa 연봉차등;
    $code contains "ADIFF";
    {override_threshold_clause}
sort $amount desc;
'''.strip(),
                    [
                        {"name": "grade", "type": "string"},
                        {"name": "eval", "type": "string"},
                        {"name": "amount", "type": "double"},
                    ],
                )
                return [
                    {"grade": row["grade"], "eval": row["eval"], "amount": float(row["amount"])}
                    for row in rows
                    if row.get("grade") and row.get("eval") and row.get("amount") is not None
                ]
        rows = _execute_rows(
            f'''
match
    $g isa 직급, has 직급코드 $grade;
    $ev isa 평가결과, has 평가등급 $eval;
    (적용기준: $d, 해당직급: $g, 해당등급: $ev) isa 연봉차등;
    $d has 차등액 $amount, has 연봉차등액코드 $code;
    $code contains "ADIFF";
    {threshold_clause}
sort $amount desc;
'''.strip(),
            [
                {"name": "grade", "type": "string"},
                {"name": "eval", "type": "string"},
                {"name": "amount", "type": "double"},
            ],
        )
        return [
            {"grade": row["grade"], "eval": row["eval"], "amount": float(row["amount"])}
            for row in rows
            if row.get("grade") and row.get("eval") and row.get("amount") is not None
        ]

    def get_salary_cap(self, grade: str, effective_date: Optional[str] = None) -> Optional[float]:
        override_amount = self._get_salary_cap_override_amount(grade, effective_date)
        if override_amount is not None:
            return override_amount
        rows = _execute_rows(
            f'''
match
    $g isa 직급, has 직급코드 "{grade}";
    (적용기준: $cap, 해당직급: $g) isa 연봉상한;
    $cap has 연봉상한액 $amount, has 연봉상한액코드 $code, has 연봉상한적용시작일 $start;
'''.strip(),
            [
                {"name": "amount", "type": "double"},
                {"name": "code", "type": "string"},
                {"name": "start", "type": "datetime"},
            ],
        )
        row = select_effective_row(rows, effective_date=effective_date, dedupe_keys=["code", "start"])
        return float(row["amount"]) if row and row.get("amount") is not None else None

    def get_position_pay(self, grade: str, position: str, effective_date: Optional[str] = None) -> Optional[float]:
        override_amount = self._get_position_pay_override_amount(grade, position, effective_date)
        if override_amount is not None:
            return override_amount
        rows = _execute_rows(
            f'''
match
    $g isa 직급, has 직급코드 "{grade}";
    $pos isa 직위, has 직위명 $posname;
    {{ $posname == "{position}"; }};
    (적용기준: $pp, 해당직급: $g, 해당직위: $pos) isa 직책급결정;
    $pp has 직책급액 $amount, has 직책급코드 $code, has 직책급적용시작일 $start;
'''.strip(),
            [
                {"name": "amount", "type": "double"},
                {"name": "code", "type": "string"},
                {"name": "start", "type": "datetime"},
            ],
        )
        row = select_effective_row(rows, effective_date=effective_date, dedupe_keys=["code", "start"])
        return float(row["amount"]) if row and row.get("amount") is not None else None

    def get_bonus_rate(self, position: str, eval_grade: str, effective_date: Optional[str] = None) -> Optional[float]:
        override_rate = self._get_bonus_rate_override_value(position, eval_grade, effective_date)
        if override_rate is not None:
            return override_rate
        rows = _execute_rows(
            f'''
match
    $pos isa 직위, has 직위명 $posname;
    {{ $posname == "{position}"; }};
    $ev isa 평가결과, has 평가등급 "{eval_grade}";
    (적용기준: $bonus, 해당직책구분: $pos, 해당등급: $ev) isa 상여금결정;
    $bonus has 상여금지급률 $rate, has 상여금코드 $code, has 상여금적용시작일 $start;
'''.strip(),
            [
                {"name": "rate", "type": "double"},
                {"name": "code", "type": "string"},
                {"name": "start", "type": "datetime"},
            ],
        )
        if not rows:
            rows = _execute_rows(
            f'''
match
    $pos isa 직위, has 직위명 $posname;
    {{ $posname == "{position}"; }};
    $ev isa 평가결과, has 평가등급 "{eval_grade}";
    (적용기준: $bonus, 해당직책구분: $pos, 해당등급: $ev) isa 상여금결정;
    $bonus has 상여금지급률 $rate, has 상여금코드 $code;
'''.strip(),
                [{"name": "rate", "type": "double"}, {"name": "code", "type": "string"}],
            )
        row = select_effective_row(rows, effective_date=effective_date, dedupe_keys=["code", "start"])
        return float(row["rate"]) if row and row.get("rate") is not None else None

    def get_foreign_salary(self, country: str, grade: str) -> Optional[Dict[str, Any]]:
        rows = _execute_rows(
            f'''
match
    $g isa 직급, has 직급코드 "{grade}";
    (적용기준: $os, 해당직급: $g) isa 국외본봉결정;
    $os has 국가명 "{country}", has 국외기본급액 $amount, has 통화단위 $currency;
'''.strip(),
            [
                {"name": "amount", "type": "double"},
                {"name": "currency", "type": "string"},
            ],
        )
        if not rows or rows[0].get("amount") is None:
            return None
        return {"country": country, "grade": grade, "amount": float(rows[0]["amount"]), "currency": rows[0].get("currency") or ""}

    def get_exec_base(self, position: str) -> Optional[float]:
        aliases = {
            "총재": ["총재 본봉"],
            "위원": ["위원·부총재 본봉"],
            "부총재": ["위원·부총재 본봉"],
            "감사": ["감사 본봉"],
            "부총재보": ["부총재보 본봉"],
        }
        rows: List[Dict[str, Any]] = []
        for name in aliases.get(position, [f"{position} 본봉"]):
            rows = _execute_rows(
                f'''
match
    $b isa 보수기준,
        has 보수기준명 "{name}",
        has 보수기본급액 $amount;
'''.strip(),
                [{"name": "amount", "type": "double"}],
            )
            if rows:
                break
        return float(rows[0]["amount"]) if rows and rows[0].get("amount") is not None else None

    def get_wage_peak_rate(self, year: int) -> Optional[float]:
        rows = _execute_rows(
            f'''
match
    $w isa 임금피크제기준, has 적용연차 {int(year)}, has 임금피크지급률 $rate;
'''.strip(),
            [{"name": "rate", "type": "double"}],
        )
        return float(rows[0]["rate"]) if rows and rows[0].get("rate") is not None else None

    def get_wage_peak_rates(self) -> List[Dict[str, Any]]:
        rows = _execute_rows(
            '''
match
    $w isa 임금피크제기준, has 적용연차 $year, has 임금피크지급률 $rate;
sort $year;
'''.strip(),
            [
                {"name": "year", "type": "integer"},
                {"name": "rate", "type": "double"},
            ],
        )
        return [
            {"year": int(row["year"]), "rate": float(row["rate"])}
            for row in rows
            if row.get("year") is not None and row.get("rate") is not None
        ]


def get_rules_subgraph() -> str:
    rows = _execute_rows(
        """
match
    $article isa 조문, has 조번호 $id, has 조문내용 $text;
sort $id;
""".strip(),
        [{"name": "id", "type": "integer"}, {"name": "text", "type": "string"}],
    )
    return "\n".join(f"제{row['id']}조: {row['text']}" for row in rows)


def _get_source_rule_snippets(question: str, entities: Dict[str, Any]) -> List[str]:
    try:
        source_text = SOURCE_TEXT_PATH.read_text(encoding="utf-8")
    except OSError:
        return []

    snippets: List[str] = []
    topics = set(entities.get("topics") or [])
    if "임금피크제" in topics or "임금피크" in question or "피크제" in question:
        for pattern in (
            r"제4조\([^\n]*본봉[^\n]*?⑥임금피크제본봉은잔여근무기간이3년이하인직원을대상으로한다\.",
            r"⑥임금피크제본봉은잔여근무기간이3년이하인직원을대상으로한다\."
        ):
            match = re.search(pattern, re.sub(r"\s+", "", source_text))
            if match:
                cleaned = match.group(0)
                cleaned = cleaned.replace("⑥", "제4조 ⑥ ") if cleaned.startswith("⑥") else cleaned
                snippets.append(cleaned)
                break
        if snippets:
            snippets = ["제4조 ⑥ 임금피크제본봉은 잔여근무기간이 3년 이하인 직원을 대상으로 한다."]

    return snippets


def fetch_relevant_rules(question: str, entities: Dict[str, Any], limit: int = 8) -> str:
    all_rules = get_rules_subgraph().splitlines()
    article_no = entities.get("article_no")
    if article_no is not None:
        matched = [line for line in all_rules if line.startswith(f"제{article_no}조:")]
        effective_date = entities.get("effective_date") or resolve_effective_date(question).isoformat()
        override_rows = _execute_rows(
            f'''
match
    $b isa 부칙, has 부칙조번호 $buchik_jo, has 부칙내용 $content, has 우선순위 $priority;
    $article isa 조문, has 조번호 {article_no};
    (대체규정: $b, 피대체대상: $article) isa 규정_대체,
        has 대체사유 $reason,
        has 대체시행일 $start;
'''.strip(),
            [
                {"name": "buchik_jo", "type": "integer"},
                {"name": "content", "type": "string"},
                {"name": "priority", "type": "integer"},
                {"name": "reason", "type": "string"},
                {"name": "start", "type": "datetime"},
            ],
        )
        override_rows_with_end = _execute_rows(
            f'''
match
    $b isa 부칙, has 부칙조번호 $buchik_jo;
    $article isa 조문, has 조번호 {article_no};
    (대체규정: $b, 피대체대상: $article) isa 규정_대체,
        has 대체사유 $reason,
        has 대체시행일 $start,
        has 대체만료일 $end;
'''.strip(),
            [
                {"name": "buchik_jo", "type": "integer"},
                {"name": "reason", "type": "string"},
                {"name": "start", "type": "datetime"},
                {"name": "end", "type": "datetime"},
            ],
        )
        end_map = {
            (row["buchik_jo"], row["reason"], row["start"]): row.get("end")
            for row in override_rows_with_end
        }
        combined_rows = []
        for row in override_rows:
            end_value = end_map.get((row["buchik_jo"], row["reason"], row["start"]))
            combined_rows.append({**row, "end": end_value})
        resolution = resolve_active_overrides(
            combined_rows,
            effective_date=effective_date,
            dedupe_keys=["buchik_jo", "reason", "content"],
        )
        override_lines = render_article_override_lines(resolution.active_rows)
        return "\n".join(matched + override_lines)

    exec_positions = {"총재", "위원", "부총재", "부총재보", "감사"}
    is_exec_salary_question = entities.get("position") in exec_positions and any(token in question for token in ("본봉", "보수"))

    keywords = [token for token in re.findall(r"[0-9A-Za-z가-힣]+", question) if len(token) >= 2]
    topic_boosts = []
    if "연봉차등" in question or entities.get("amount_threshold") is not None:
        topic_boosts.extend(["연봉제본봉", "차등액", "평가등급"])
    if "연봉상한" in question:
        topic_boosts.extend(["상한액", "연봉제본봉"])
    if "직책급" in question:
        topic_boosts.extend(["직책급"])
    if "상여금" in question:
        topic_boosts.extend(["상여금", "지급률"])
    if "임금피크" in question or "피크제" in question:
        topic_boosts.extend(["임금피크제본봉", "잔여근무기간", "기본급지급률"])
    if "본봉" in question or "보수" in question:
        topic_boosts.extend(["본봉", "별표1", "연간총액"])

    scored: List[tuple[int, str]] = []
    for line in all_rules:
        score = sum(1 for keyword in keywords if keyword in line)
        score += 3 * sum(1 for keyword in topic_boosts if keyword in line)
        if is_exec_salary_question:
            score += 5 * sum(1 for keyword in ("집행간부", "별표1", "연간총액") if keyword in line)
            score -= 3 if "초임호봉" in line else 0
        if score > 0:
            scored.append((score, line))
    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [line for _, line in scored[:limit]]
    for snippet in _get_source_rule_snippets(question, entities):
        if snippet not in selected:
            selected.append(snippet)
    return "\n".join(selected)


def _fetch_override_sections_typedb(entities: Dict[str, Any]) -> List[str]:
    sections: List[str] = []
    article_no = entities.get("article_no")
    grade = entities.get("grade")
    eval_grade = entities.get("eval")
    threshold = entities.get("amount_threshold")
    topics = set(entities.get("topics") or [])
    effective_date = entities.get("effective_date")

    if article_no is not None:
        rows = _execute_rows(
            f'''
match
    $b isa 부칙, has 부칙조번호 $buchik_jo, has 부칙내용 $content, has 우선순위 $priority;
    $article isa 조문, has 조번호 {article_no};
    (대체규정: $b, 피대체대상: $article) isa 규정_대체,
        has 대체사유 $reason,
        has 대체시행일 $start;
sort $priority;
'''.strip(),
            [
                {"name": "buchik_jo", "type": "integer"},
                {"name": "content", "type": "string"},
                {"name": "reason", "type": "string"},
                {"name": "priority", "type": "integer"},
                {"name": "start", "type": "datetime"},
            ],
        )
        resolution = resolve_active_overrides(
            rows,
            effective_date=effective_date,
            dedupe_keys=["buchik_jo", "reason", "content"],
            end_key="end",
        )
        sections.append(_format_section("조문 오버라이드 3-hop", resolution.active_rows))

    if "연봉차등" in topics or threshold is not None:
        grade_clause = f'$g isa 직급, has 직급코드 "{grade}";' if grade else '$g isa 직급, has 직급코드 $grade;'
        eval_clause = f'$ev isa 평가결과, has 평가등급 "{eval_grade}";' if eval_grade else '$ev isa 평가결과, has 평가등급 $eval;'
        threshold_clause = f'$diff >= {threshold};' if threshold is not None else ''
        variables = [
            {"name": "buchik_jo", "type": "integer"},
            {"name": "reason", "type": "string"},
            {"name": "priority", "type": "integer"},
            {"name": "grade", "type": "string"},
            {"name": "eval", "type": "string"},
            {"name": "diff", "type": "double"},
            {"name": "code", "type": "string"},
        ]
        if grade:
            variables = [variable for variable in variables if variable["name"] != "grade"]
        if eval_grade:
            variables = [variable for variable in variables if variable["name"] != "eval"]
        rows = _execute_rows(
            f'''
match
    $b isa 부칙, has 부칙조번호 $buchik_jo, has 우선순위 $priority;
    {grade_clause}
    {eval_clause}
    $d isa 연봉차등액기준, has 연봉차등액코드 $code, has 차등액 $diff;
    (적용기준: $d, 해당직급: $g, 해당등급: $ev) isa 연봉차등;
    (대체규정: $b, 피대체대상: $d) isa 규정_대체,
        has 대체사유 $reason,
        has 대체시행일 $start;
    $code contains "ADIFF";
    {threshold_clause}
sort $diff desc;
'''.strip(),
            variables,
        )
        resolution = resolve_active_overrides(
            rows,
            effective_date=effective_date,
            dedupe_keys=["buchik_jo", "reason", "code"],
            end_key="end",
        )
        sections.append(_format_section("부칙 차등액 오버라이드 3-hop", resolution.active_rows))

    if "연봉상한" in topics and grade:
        rows = _execute_rows(
            f'''
match
    $b isa 부칙, has 부칙조번호 $buchik_jo, has 우선순위 $priority;
    $g isa 직급, has 직급코드 "{grade}";
    $cap isa 연봉상한액기준, has 연봉상한액코드 $code;
    (적용기준: $cap, 해당직급: $g) isa 연봉상한;
    (대체규정: $b, 피대체대상: $cap) isa 규정_대체,
        has 대체사유 $reason,
        has 대체시행일 $start;
'''.strip(),
            [
                {"name": "buchik_jo", "type": "integer"},
                {"name": "priority", "type": "integer"},
                {"name": "code", "type": "string"},
                {"name": "reason", "type": "string"},
                {"name": "start", "type": "datetime"},
            ],
        )
        end_rows = _execute_rows(
            f'''
match
    $b isa 부칙, has 부칙조번호 $buchik_jo;
    $g isa 직급, has 직급코드 "{grade}";
    $cap isa 연봉상한액기준, has 연봉상한액코드 $code;
    (적용기준: $cap, 해당직급: $g) isa 연봉상한;
    (대체규정: $b, 피대체대상: $cap) isa 규정_대체,
        has 대체사유 $reason,
        has 대체시행일 $start,
        has 대체만료일 $end;
'''.strip(),
            [
                {"name": "buchik_jo", "type": "integer"},
                {"name": "code", "type": "string"},
                {"name": "reason", "type": "string"},
                {"name": "start", "type": "datetime"},
                {"name": "end", "type": "datetime"},
            ],
        )
        resolution = resolve_active_overrides(
            _merge_override_end_rows(rows, end_rows, ["buchik_jo", "code", "reason", "start"]),
            effective_date=effective_date,
            dedupe_keys=["buchik_jo", "code", "reason"],
        )
        sections.append(_format_section("부칙 연봉상한 오버라이드 3-hop", resolution.active_rows))

    position = entities.get("position")
    if "직책급" in topics and grade and position:
        rows = _execute_rows(
            f'''
match
    $b isa 부칙, has 부칙조번호 $buchik_jo, has 우선순위 $priority;
    $g isa 직급, has 직급코드 "{grade}";
    $pos isa 직위, has 직위명 $posname;
    {{ $posname == "{position}"; }};
    $pp isa 직책급기준, has 직책급코드 $code;
    (적용기준: $pp, 해당직급: $g, 해당직위: $pos) isa 직책급결정;
    (대체규정: $b, 피대체대상: $pp) isa 규정_대체,
        has 대체사유 $reason,
        has 대체시행일 $start;
'''.strip(),
            [
                {"name": "buchik_jo", "type": "integer"},
                {"name": "priority", "type": "integer"},
                {"name": "code", "type": "string"},
                {"name": "reason", "type": "string"},
                {"name": "start", "type": "datetime"},
            ],
        )
        end_rows = _execute_rows(
            f'''
match
    $b isa 부칙, has 부칙조번호 $buchik_jo;
    $g isa 직급, has 직급코드 "{grade}";
    $pos isa 직위, has 직위명 $posname;
    {{ $posname == "{position}"; }};
    $pp isa 직책급기준, has 직책급코드 $code;
    (적용기준: $pp, 해당직급: $g, 해당직위: $pos) isa 직책급결정;
    (대체규정: $b, 피대체대상: $pp) isa 규정_대체,
        has 대체사유 $reason,
        has 대체시행일 $start,
        has 대체만료일 $end;
'''.strip(),
            [
                {"name": "buchik_jo", "type": "integer"},
                {"name": "code", "type": "string"},
                {"name": "reason", "type": "string"},
                {"name": "start", "type": "datetime"},
                {"name": "end", "type": "datetime"},
            ],
        )
        resolution = resolve_active_overrides(
            _merge_override_end_rows(rows, end_rows, ["buchik_jo", "code", "reason", "start"]),
            effective_date=effective_date,
            dedupe_keys=["buchik_jo", "code", "reason"],
        )
        sections.append(_format_section("부칙 직책급 오버라이드 3-hop", resolution.active_rows))

    if "상여금" in topics and position and eval_grade:
        rows = _execute_rows(
            f'''
match
    $b isa 부칙, has 부칙조번호 $buchik_jo, has 우선순위 $priority;
    $pos isa 직위, has 직위명 $posname;
    {{ $posname == "{position}"; }};
    $ev isa 평가결과, has 평가등급 "{eval_grade}";
    $bonus isa 상여금기준, has 상여금코드 $code;
    (적용기준: $bonus, 해당직책구분: $pos, 해당등급: $ev) isa 상여금결정;
    (대체규정: $b, 피대체대상: $bonus) isa 규정_대체,
        has 대체사유 $reason,
        has 대체시행일 $start;
'''.strip(),
            [
                {"name": "buchik_jo", "type": "integer"},
                {"name": "priority", "type": "integer"},
                {"name": "code", "type": "string"},
                {"name": "reason", "type": "string"},
                {"name": "start", "type": "datetime"},
            ],
        )
        end_rows = _execute_rows(
            f'''
match
    $b isa 부칙, has 부칙조번호 $buchik_jo;
    $pos isa 직위, has 직위명 $posname;
    {{ $posname == "{position}"; }};
    $ev isa 평가결과, has 평가등급 "{eval_grade}";
    $bonus isa 상여금기준, has 상여금코드 $code;
    (적용기준: $bonus, 해당직책구분: $pos, 해당등급: $ev) isa 상여금결정;
    (대체규정: $b, 피대체대상: $bonus) isa 규정_대체,
        has 대체사유 $reason,
        has 대체시행일 $start,
        has 대체만료일 $end;
'''.strip(),
            [
                {"name": "buchik_jo", "type": "integer"},
                {"name": "code", "type": "string"},
                {"name": "reason", "type": "string"},
                {"name": "start", "type": "datetime"},
                {"name": "end", "type": "datetime"},
            ],
        )
        resolution = resolve_active_overrides(
            _merge_override_end_rows(rows, end_rows, ["buchik_jo", "code", "reason", "start"]),
            effective_date=effective_date,
            dedupe_keys=["buchik_jo", "code", "reason"],
        )
        sections.append(_format_section("부칙 상여금 오버라이드 3-hop", resolution.active_rows))

    return [section for section in sections if section]


def _format_section(title: str, rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return ""
    lines = [f"[{title}]"]
    for row in rows:
        parts = [f"{key}={value}" for key, value in row.items() if value not in (None, "")]
        lines.append("- " + ", ".join(parts))
    return "\n".join(lines)


def _make_plan_item(
    name: str,
    *,
    executed: bool,
    reason: str,
    targets: Optional[Dict[str, Any]] = None,
    row_count: Optional[int] = None,
) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "name": name,
        "executed": executed,
        "reason": reason,
    }
    if targets:
        item["targets"] = targets
    if row_count is not None:
        item["row_count"] = row_count
    return item


def fetch_subgraph_typedb(entities: Dict[str, Any], question: Optional[str] = None) -> tuple[str, List[Dict[str, Any]]]:
    sections: List[str] = []
    plan: List[Dict[str, Any]] = []
    hop_depth = int(entities.get("hop_depth") or _determine_hop_depth(question or "", entities))
    topics = set(entities.get("topics") or [])
    grade = entities.get("grade")
    position = entities.get("position")
    eval_grade = entities.get("eval")
    country = entities.get("country")
    track = entities.get("track")

    if grade and "호봉" in topics:
        rows = _execute_rows(
            f'''
match
    $g isa 직급, has 직급코드 "{grade}";
    (소속직급: $g, 구성호봉: $h) isa 호봉체계구성;
    $h has 호봉번호 $n, has 호봉금액 $amt;
sort $n;
'''.strip(),
            [{"name": "n", "type": "integer"}, {"name": "amt", "type": "double"}],
        )
        sections.append(_format_section(f"호봉 {hop_depth}-hop", rows))
        plan.append(_make_plan_item("호봉 조회", executed=True, reason="grade와 호봉 topic이 모두 존재합니다.", targets={"grade": grade}, row_count=len(rows)))
    else:
        missing: List[str] = []
        if not grade:
            missing.append("grade")
        if "호봉" not in topics:
            missing.append("topic=호봉")
        plan.append(_make_plan_item("호봉 조회", executed=False, reason=f"필수 조건 부족: {', '.join(missing)}"))

    if track and "초임호봉" in topics:
        rows = _execute_rows(
            f'''
match
    $s isa 직렬, has 직렬명 "{track}";
    (대상직렬: $s, 적용기준: $std) isa 초임호봉결정;
    $std has 초임호봉번호 $n, has 초임호봉기준설명 $desc;
'''.strip(),
            [{"name": "n", "type": "integer"}, {"name": "desc", "type": "string"}],
        )
        sections.append(_format_section(f"초임호봉 {hop_depth}-hop", rows))
        plan.append(_make_plan_item("초임호봉 조회", executed=True, reason="track과 초임호봉 topic이 모두 존재합니다.", targets={"track": track}, row_count=len(rows)))
    else:
        missing = []
        if not track:
            missing.append("track")
        if "초임호봉" not in topics:
            missing.append("topic=초임호봉")
        plan.append(_make_plan_item("초임호봉 조회", executed=False, reason=f"필수 조건 부족: {', '.join(missing)}"))

    if ("연봉차등" in topics or entities.get("amount_threshold") is not None) and eval_grade and grade:
        rows = _execute_rows(
            f'''
match
    $g isa 직급, has 직급코드 "{grade}";
    $ev isa 평가결과, has 평가등급 "{eval_grade}";
    (적용기준: $d, 해당직급: $g, 해당등급: $ev) isa 연봉차등;
    $d has 차등액 $diff, has 연봉차등액코드 $code;
    $code contains "ADIFF";
'''.strip(),
            [{"name": "diff", "type": "double"}, {"name": "code", "type": "string"}],
        )
        sections.append(_format_section(f"연봉차등 {hop_depth}-hop", rows))
        plan.append(_make_plan_item("연봉차등 조회", executed=True, reason="연봉차등 topic과 grade/eval이 모두 존재합니다.", targets={"grade": grade, "eval": eval_grade}, row_count=len(rows)))
    elif "연봉차등" in topics or entities.get("amount_threshold") is not None:
        rows = _execute_rows(
            '''
match
    $g isa 직급, has 직급코드 $grade;
    $ev isa 평가결과, has 평가등급 $eval;
    (적용기준: $d, 해당직급: $g, 해당등급: $ev) isa 연봉차등;
    $d has 차등액 $diff, has 연봉차등액코드 $code;
    $code contains "ADIFF";
sort $diff desc;
'''.strip(),
            [
                {"name": "grade", "type": "string"},
                {"name": "eval", "type": "string"},
                {"name": "diff", "type": "double"},
                {"name": "code", "type": "string"},
            ],
        )
        sections.append(_format_section(f"연봉차등 {hop_depth}-hop", rows))
        plan.append(_make_plan_item("연봉차등 조회", executed=True, reason="연봉차등 topic은 있으나 grade/eval 일부가 없어 전체 후보를 조회합니다.", targets={"amount_threshold": entities.get("amount_threshold")}, row_count=len(rows)))
    else:
        plan.append(_make_plan_item("연봉차등 조회", executed=False, reason="topic=연봉차등 또는 amount_threshold가 없습니다."))

    if "연봉상한" in topics and grade:
        rows = _execute_rows(
            f'''
match
    $g isa 직급, has 직급코드 "{grade}";
    (적용기준: $cap, 해당직급: $g) isa 연봉상한;
    $cap has 연봉상한액 $cap_amt, has 연봉상한액코드 $code;
'''.strip(),
            [{"name": "cap_amt", "type": "double"}, {"name": "code", "type": "string"}],
        )
        sections.append(_format_section(f"연봉상한 {hop_depth}-hop", rows))
        plan.append(_make_plan_item("연봉상한 조회", executed=True, reason="연봉상한 topic과 grade가 존재합니다.", targets={"grade": grade}, row_count=len(rows)))
    else:
        missing = []
        if "연봉상한" not in topics:
            missing.append("topic=연봉상한")
        if not grade:
            missing.append("grade")
        plan.append(_make_plan_item("연봉상한 조회", executed=False, reason=f"필수 조건 부족: {', '.join(missing)}"))

    if "직책급" in topics and grade and position:
        rows = _execute_rows(
            f'''
match
    $g isa 직급, has 직급코드 "{grade}";
    $pos isa 직위, has 직위명 $posname;
    {{ $posname == "{position}"; }};
    (적용기준: $pp, 해당직급: $g, 해당직위: $pos) isa 직책급결정;
    $pp has 직책급액 $amount, has 직책급코드 $code;
'''.strip(),
            [
                {"name": "posname", "type": "string"},
                {"name": "amount", "type": "double"},
                {"name": "code", "type": "string"},
            ],
        )
        sections.append(_format_section(f"직책급 {hop_depth}-hop", rows))
        plan.append(_make_plan_item("직책급 조회", executed=True, reason="직책급 topic과 grade/position이 존재합니다.", targets={"grade": grade, "position": position}, row_count=len(rows)))
    else:
        missing = []
        if "직책급" not in topics:
            missing.append("topic=직책급")
        if not grade:
            missing.append("grade")
        if not position:
            missing.append("position")
        plan.append(_make_plan_item("직책급 조회", executed=False, reason=f"필수 조건 부족: {', '.join(missing)}"))

    if "상여금" in topics and position and eval_grade:
        rows = _execute_rows(
            f'''
match
    $pos isa 직위, has 직위명 $posname;
    {{ $posname == "{position}"; }};
    $ev isa 평가결과, has 평가등급 "{eval_grade}";
    (적용기준: $bonus, 해당직책구분: $pos, 해당등급: $ev) isa 상여금결정;
    $bonus has 상여금지급률 $rate, has 상여금코드 $code;
'''.strip(),
            [
                {"name": "posname", "type": "string"},
                {"name": "rate", "type": "double"},
                {"name": "code", "type": "string"},
            ],
        )
        sections.append(_format_section(f"상여금 {hop_depth}-hop", rows))
        plan.append(_make_plan_item("상여금 조회", executed=True, reason="상여금 topic과 position/eval이 존재합니다.", targets={"position": position, "eval": eval_grade}, row_count=len(rows)))
    else:
        missing = []
        if "상여금" not in topics:
            missing.append("topic=상여금")
        if not position:
            missing.append("position")
        if not eval_grade:
            missing.append("eval")
        plan.append(_make_plan_item("상여금 조회", executed=False, reason=f"필수 조건 부족: {', '.join(missing)}"))

    if "국외본봉" in topics and country and grade:
        rows = _execute_rows(
            f'''
match
    $g isa 직급, has 직급코드 "{grade}";
    (적용기준: $os, 해당직급: $g) isa 국외본봉결정;
    $os has 국가명 "{country}", has 국외기본급액 $amt, has 통화단위 $cur;
'''.strip(),
            [{"name": "amt", "type": "double"}, {"name": "cur", "type": "string"}],
        )
        sections.append(_format_section(f"국외본봉 {hop_depth}-hop", rows))
        plan.append(_make_plan_item("국외본봉 조회", executed=True, reason="국외본봉 topic과 country/grade가 존재합니다.", targets={"country": country, "grade": grade}, row_count=len(rows)))
    else:
        missing = []
        if "국외본봉" not in topics:
            missing.append("topic=국외본봉")
        if not country:
            missing.append("country")
        if not grade:
            missing.append("grade")
        plan.append(_make_plan_item("국외본봉 조회", executed=False, reason=f"필수 조건 부족: {', '.join(missing)}"))

    if "임금피크제" in topics:
        rows = _execute_rows(
            '''
match
    $w isa 임금피크제기준,
        has 적용연차 $year,
        has 임금피크지급률 $rate,
        has 임금피크제설명 $desc;
sort $year;
'''.strip(),
            [
                {"name": "year", "type": "integer"},
                {"name": "rate", "type": "double"},
                {"name": "desc", "type": "string"},
            ],
        )
        sections.append(_format_section(f"임금피크제 {hop_depth}-hop", rows))
        plan.append(_make_plan_item("임금피크제 조회", executed=True, reason="임금피크제 topic이 존재합니다.", row_count=len(rows)))
    else:
        plan.append(_make_plan_item("임금피크제 조회", executed=False, reason="topic=임금피크제 가 없습니다."))

    if position and ("본봉" in topics or "보수" in topics or "본봉" in (question or "")):
        position_aliases = {
            "총재": ["총재 본봉"],
            "위원": ["위원·부총재 본봉"],
            "부총재": ["위원·부총재 본봉"],
            "감사": ["감사 본봉"],
            "부총재보": ["부총재보 본봉"],
        }
        target_name = position_aliases.get(position, [f"{position} 본봉"])[0]
        rows = _execute_rows(
            f'''
match
    $b isa 보수기준,
        has 보수기준명 $name,
        has 보수기준명 "{target_name}",
        has 보수기본급액 $amount,
        has 보수기준설명 $desc;
'''.strip(),
            [
                {"name": "name", "type": "string"},
                {"name": "amount", "type": "double"},
                {"name": "desc", "type": "string"},
            ],
        )
        sections.append(_format_section(f"집행간부 본봉 {hop_depth}-hop", rows))
        plan.append(_make_plan_item("집행간부 본봉 조회", executed=True, reason="position과 본봉/보수 단서가 존재합니다.", targets={"position": position}, row_count=len(rows)))
    else:
        missing = []
        if not position:
            missing.append("position")
        if not (("본봉" in topics) or ("보수" in topics) or ("본봉" in (question or ""))):
            missing.append("topic=본봉|보수")
        plan.append(_make_plan_item("집행간부 본봉 조회", executed=False, reason=f"필수 조건 부족: {', '.join(missing)}"))

    if hop_depth >= 3:
        override_sections = _fetch_override_sections_typedb(entities)
        sections.extend(override_sections)
        plan.append(_make_plan_item("부칙 오버라이드 조회", executed=True, reason="hop_depth >= 3 이므로 부칙 오버라이드 조회를 수행합니다.", row_count=len([section for section in override_sections if section])))
    else:
        plan.append(_make_plan_item("부칙 오버라이드 조회", executed=False, reason=f"hop_depth={hop_depth} 이므로 3-hop 오버라이드 조회를 생략합니다."))

    return "\n\n".join(section for section in sections if section), plan


def generate_answer(question: str, entities: Dict[str, Any], rules_context: str, graph_context: str) -> str:
    prompt = f"""당신은 한국은행 보수규정 Graph RAG 답변 모델입니다.
반드시 아래의 서브쿼리 결과만 근거로 추론하세요.

규칙:
1. 주요 엔티티와 규정, adaptive 1~3-hop 그래프 조회 결과를 함께 보고 답하세요.
2. 질문이 비교/필터를 요구하면 후보 행을 하나씩 끝까지 검토하세요.
3. 숫자는 서브쿼리 결과에 있는 값만 사용하세요.
4. 값이 없으면 추정하지 말고 조회 결과가 없다고 말하세요.
5. 부칙 또는 대체 규정이 보이면 본문보다 우선 적용 여부를 먼저 판단하세요.
6. 답변은 너무 짧게 끝내지 말고, 필요하면 근거 규정과 조회된 엔티티를 짧게 설명하세요.

[질문]
{question}

[추출된 주요 엔티티]
{json.dumps(entities, ensure_ascii=False)}

[관련 규정 서브쿼리 결과]
{rules_context or '없음'}

[Adaptive hop 그래프 서브쿼리 결과]
{graph_context or '없음'}

최종 답변:
"""
    return _invoke_text(prompt)


def run_with_trace(question: str) -> Dict[str, Any]:
    entities = extract_entities(question)
    entities["hop_depth"] = _determine_hop_depth(question, entities)
    rules_plan = {
        "mode": "scored-rule-search",
        "article_direct_lookup": entities.get("article_no") is not None,
        "topics": entities.get("topics") or [],
        "keyword": entities.get("keyword") or question,
    }
    validation = validate_question(question, entities)
    if validation is not None:
        return {
            "answer": validation["message"],
            "trace": {
                "question": question,
                "query_language": "TypeQL",
                "entities": entities,
                "validation": validation,
                "retrieval_plan": {
                    "rules": rules_plan,
                    "graph": [],
                },
                "rules_context": "",
                "graph_context": "",
            },
        }

    rules_context = fetch_relevant_rules(question, entities)
    graph_context, graph_plan = fetch_subgraph_typedb(entities, question)
    deterministic_result = try_execute_regulation(question, entities)
    if deterministic_result is None:
        deterministic_result = try_execute(question, entities, _TypeDBDeterministicProvider())
    if deterministic_result is not None:
        answer = deterministic_result.answer
    else:
        answer = generate_answer(question, entities, rules_context, graph_context)
    return {
        "answer": answer,
        "trace": {
            "question": question,
            "query_language": "TypeQL",
            "entities": entities,
            "retrieval_plan": {
                "rules": rules_plan,
                "graph": graph_plan,
            },
            "deterministic_execution": None if deterministic_result is None else {
                "kind": deterministic_result.kind,
                "steps": deterministic_result.steps,
                "values": deterministic_result.values,
            },
            "rules_context": rules_context,
            "graph_context": graph_context,
        },
    }


def run(question: str) -> str:
    return run_with_trace(question)["answer"]


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]).strip() or "일반사무직원의 초봉은?"
    print(run(query))