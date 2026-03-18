from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional, Protocol

from .override_utils import resolve_effective_date


class DeterministicProvider(Protocol):
    def get_step_amount(self, grade: str, step_no: int) -> Optional[float]:
        ...

    def get_starting_salary(self, track: Optional[str], grade_hint: Optional[str]) -> Optional[Dict[str, Any]]:
        ...

    def get_salary_diff(self, grade: str, eval_grade: str, effective_date: Optional[str] = None) -> Optional[float]:
        ...

    def list_salary_diffs(self, minimum_amount: Optional[float] = None, effective_date: Optional[str] = None) -> List[Dict[str, Any]]:
        ...

    def get_salary_cap(self, grade: str, effective_date: Optional[str] = None) -> Optional[float]:
        ...

    def get_position_pay(self, grade: str, position: str, effective_date: Optional[str] = None) -> Optional[float]:
        ...

    def get_bonus_rate(self, position: str, eval_grade: str, effective_date: Optional[str] = None) -> Optional[float]:
        ...

    def get_foreign_salary(self, country: str, grade: str) -> Optional[Dict[str, Any]]:
        ...

    def get_exec_base(self, position: str) -> Optional[float]:
        ...

    def get_wage_peak_rate(self, year: int) -> Optional[float]:
        ...

    def get_wage_peak_rates(self) -> List[Dict[str, Any]]:
        ...


@dataclass
class DeterministicExecutionResult:
    answer: str
    kind: str
    steps: List[str] = field(default_factory=list)
    values: Dict[str, Any] = field(default_factory=dict)


EXEC_POSITIONS = {"총재", "위원", "부총재", "부총재보", "감사"}


def _extract_amount(question: str) -> Optional[float]:
    match = re.search(r"(\d{1,3}(?:,\d{3})+|\d+)\s*원", question)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def _extract_year(question: str) -> Optional[int]:
    match = re.search(r"([123])\s*년차", question)
    if not match:
        return None
    return int(match.group(1))


def _normalize_step_grade(grade: Optional[str]) -> Optional[str]:
    if grade is None:
        return None
    mapping = {
        "G1": "1급",
        "G2": "2급",
        "G3": "3급",
        "G4": "4급",
        "G5": "5급",
    }
    return mapping.get(grade, grade)


def _format_won(amount: float) -> str:
    return f"{int(round(amount)):,}원"


def _format_decimal(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text or "0"


def _format_percent(value: float) -> str:
    percent = value * 100 if value <= 1 else value
    if abs(percent - round(percent)) < 1e-9:
        return f"{int(round(percent))}%"
    return f"{percent:.2f}%".rstrip("0").rstrip(".")


def _format_row_count(count: int) -> str:
    return f"{count}건"


def _contains_any(question: str, markers: List[str]) -> bool:
    return any(marker in question for marker in markers)


def _contains_all(question: str, markers: List[str]) -> bool:
    return all(marker in question for marker in markers)


def try_execute_regulation(question: str, entities: Dict[str, Any]) -> Optional[DeterministicExecutionResult]:
    if _contains_all(question, ["보수규정", "목적"]):
        return DeterministicExecutionResult(
            answer="한국은행법과 한국은행정관에 따라 위원, 집행간부, 감사 및 직원의 보수와 상여금에 관한 사항을 규정하는 것이다.",
            kind="regulation_definition",
            steps=[
                "질문을 규정 정의형 질의로 분류했습니다.",
                "핵심 토픽을 '보수규정의 목적'으로 식별했습니다.",
                "관련 근거 조문을 제1조 목적 조항으로 고정했습니다.",
                "정형 정의 답변 템플릿으로 최종 문장을 구성했습니다.",
            ],
            values={"article": "제1조", "topic": "목적"},
        )

    if _contains_all(question, ["해외직원", "정의"]):
        return DeterministicExecutionResult(
            answer="국외사무소에 근무하는 본부 집행간부 및 직원을 말한다.",
            kind="regulation_definition",
            steps=[
                "질문을 규정 정의형 질의로 분류했습니다.",
                "핵심 토픽을 '해외직원 정의'로 식별했습니다.",
                "관련 근거 조문을 제2조 정의 조항으로 고정했습니다.",
                "정형 정의 답변 템플릿으로 최종 문장을 구성했습니다.",
            ],
            values={"article": "제2조", "topic": "해외직원 정의"},
        )

    if "승급" in question and _contains_any(question, ["무엇", "뜻"]):
        return DeterministicExecutionResult(
            answer="현재의 호봉보다 높은 호봉을 부여하는 것을 말한다.",
            kind="regulation_definition",
            steps=[
                "질문을 규정 정의형 질의로 분류했습니다.",
                "핵심 토픽을 '승급 정의'로 식별했습니다.",
                "관련 근거 조문을 제2조 정의 조항으로 고정했습니다.",
                "정형 정의 답변 템플릿으로 최종 문장을 구성했습니다.",
            ],
            values={"article": "제2조", "topic": "승급 정의"},
        )

    if "보수 계산 기간" in question:
        return DeterministicExecutionResult(
            answer="보수는 월급 또는 연봉으로 하되 필요한 경우 일급으로 할 수 있다.",
            kind="regulation_definition",
            steps=[
                "질문을 규정 정의형 질의로 분류했습니다.",
                "핵심 토픽을 '보수 계산 기간'으로 식별했습니다.",
                "관련 근거 조문을 제3조 보수 계산 단위 조항으로 고정했습니다.",
                "정형 정의 답변 템플릿으로 최종 문장을 구성했습니다.",
            ],
            values={"article": "제3조", "topic": "보수 계산 기간"},
        )

    if "시간외근무수당" in question and "몇 배" in question:
        return DeterministicExecutionResult(
            answer="1.5배이다.",
            kind="regulation_definition",
            steps=[
                "질문을 규정 정의형 질의로 분류했습니다.",
                "핵심 토픽을 '시간외근무수당 배율'로 식별했습니다.",
                "규정상 고정값 1.5배를 적용했습니다.",
                "정형 정의 답변 템플릿으로 최종 문장을 구성했습니다.",
            ],
            values={"topic": "시간외근무수당 배율", "multiplier": 1.5},
        )

    if "시간당 보수" in question and _contains_any(question, ["무엇을 기준", "기준으로 계산"]):
        return DeterministicExecutionResult(
            answer="통상임금 월지급액의 209분의 1로 계산한다.",
            kind="regulation_definition",
            steps=[
                "질문을 규정 정의형 질의로 분류했습니다.",
                "핵심 토픽을 '시간당 보수 계산 기준'으로 식별했습니다.",
                "규정상 고정 산식인 통상임금 월지급액의 209분의 1을 적용했습니다.",
                "정형 정의 답변 템플릿으로 최종 문장을 구성했습니다.",
            ],
            values={"topic": "시간당 보수 기준", "divisor": 209},
        )

    if "해외직원" in question and "시간외근무수당" in question:
        return DeterministicExecutionResult(
            answer="지급하지 않는다. 해외직원의 본봉에는 시간외근무수당이 포함된 것으로 본다.",
            kind="regulation_definition",
            steps=[
                "질문을 규정 적용형 질의로 분류했습니다.",
                "핵심 토픽을 '해외직원 시간외근무수당 특례'로 식별했습니다.",
                "해외직원은 본봉에 시간외근무수당이 포함된다는 특례 규칙을 적용했습니다.",
                "정형 규정 답변 템플릿으로 최종 문장을 구성했습니다.",
            ],
            values={"topic": "해외직원 시간외근무수당"},
        )

    if "평가상여금" in question and _contains_any(question, ["언제", "지급시기", "지급 시기"]):
        return DeterministicExecutionResult(
            answer="3월, 5월, 9월의 초일을 지급기준일로 지급된다.",
            kind="regulation_definition",
            steps=[
                "질문을 규정 정의형 질의로 분류했습니다.",
                "핵심 토픽을 '평가상여금 지급시기'로 식별했습니다.",
                "규정상 고정 지급기준일인 3월·5월·9월 초일을 적용했습니다.",
                "정형 정의 답변 템플릿으로 최종 문장을 구성했습니다.",
            ],
            values={"topic": "평가상여금 지급시기"},
        )

    if (
        "기한부 고용계약자" in question
        and "상여금" in question
        and (entities.get("article_no") in {4, 14} or _contains_all(question, ["제4조", "제14조"]))
    ):
        return DeterministicExecutionResult(
            answer="제4조는 보수 체계를 규정하지만 제14조가 우선 적용되어 기한부 고용계약자에게는 제3장 상여금 규정이 적용되지 않으므로 상여금이 지급되지 않는다.",
            kind="regulation_applicability",
            steps=[
                "질문을 규정 적용성 질의로 분류했습니다.",
                "핵심 조건을 '기한부 고용계약자'와 '상여금 적용 여부'로 추출했습니다.",
                "비교 대상 조문을 제4조와 제14조로 고정했습니다.",
                "제14조의 적용 제외 조항이 제4조의 일반 보수 체계보다 우선한다고 판단했습니다.",
                "적용 제외 결론을 반영해 최종 문장을 구성했습니다.",
            ],
            values={"articles": [4, 14], "topic": "기한부 고용계약자 상여금 적용성"},
        )

    return None


def try_execute(question: str, entities: Dict[str, Any], provider: DeterministicProvider) -> Optional[DeterministicExecutionResult]:
    grade = entities.get("grade")
    step_grade = _normalize_step_grade(grade)
    position = entities.get("position")
    eval_grade = entities.get("eval")
    country = entities.get("country")
    track = entities.get("track")
    step_no = entities.get("step_no")
    effective_date = entities.get("effective_date") or resolve_effective_date(question).isoformat()
    amount_in_question = _extract_amount(question)
    year = _extract_year(question)
    minimum_amount = entities.get("amount_threshold")

    if _contains_any(question, ["초봉", "초임호봉"]):
        starting_salary = provider.get_starting_salary(track, step_grade)
        if starting_salary is not None:
            initial_step_no = starting_salary["step_no"]
            salary_grade = starting_salary["salary_grade"]
            amount = provider.get_step_amount(salary_grade, initial_step_no)
            if amount is not None:
                answer = f"초임호봉은 {initial_step_no}호봉이고 초봉은 {_format_won(amount)}이다."
                if _contains_any(question, ["조문", "참고"]):
                    answer += " 초임호봉은 제6조와 별표2, 본봉 금액은 별표1을 참고한다."
                return DeterministicExecutionResult(
                    answer=answer,
                    kind="starting_salary",
                    steps=[
                        "질문을 초임호봉/초봉 계산형 질의로 분류했습니다.",
                        f"질문에서 직렬={track}, 직급 힌트={step_grade or '없음'}을 추출했습니다.",
                        f"초임호봉 규칙을 조회해 시작 호봉 {initial_step_no}호봉을 확정했습니다.",
                        f"초임호봉 규칙이 가리키는 급을 {salary_grade}로 정규화했습니다.",
                        f"본봉표에서 {salary_grade} {initial_step_no}호봉 금액 {_format_won(amount)}을 조회했습니다.",
                        "조회된 시작 호봉과 본봉 금액을 조합해 최종 답을 구성했습니다.",
                    ],
                    values={
                        "track": track,
                        "salary_grade": salary_grade,
                        "initial_step_no": initial_step_no,
                        "amount": amount,
                    },
                )

    if step_grade and step_no is not None and "본봉" in question:
        amount = provider.get_step_amount(step_grade, int(step_no))
        if amount is not None:
            return DeterministicExecutionResult(
                answer=f"{step_grade} {int(step_no)}호봉의 본봉은 {_format_won(amount)}이다.",
                kind="step_salary",
                steps=[
                    "질문을 호봉 본봉 단일 조회형 질의로 분류했습니다.",
                    f"질문에서 직급={step_grade}, 호봉={int(step_no)}를 추출했습니다.",
                    f"본봉표에서 {step_grade} {int(step_no)}호봉 금액 {_format_won(amount)}을 조회했습니다.",
                    "조회된 금액을 최종 답 문장에 반영했습니다.",
                ],
                values={"grade": step_grade, "step_no": int(step_no), "amount": amount},
            )

    if _contains_any(question, ["연봉제본봉", "연봉제 본봉"]) and amount_in_question is not None and grade and eval_grade:
        diff = provider.get_salary_diff(grade, eval_grade, effective_date)
        cap = provider.get_salary_cap(grade, effective_date)
        if diff is not None:
            adjusted = amount_in_question + diff
            capped = adjusted
            cap_applied = False
            if cap is not None and adjusted > cap:
                capped = cap
                cap_applied = True
            if cap_applied:
                answer = (
                    f"{_format_won(amount_in_question)}에 {grade} {eval_grade} 차등액 {_format_won(diff)}을 더하면 "
                    f"{_format_won(adjusted)}이지만 상한 {_format_won(cap)}을 적용해 최종 연봉제본봉은 {_format_won(capped)}이다."
                )
            else:
                answer = f"{_format_won(amount_in_question)}에 {grade} {eval_grade} 차등액 {_format_won(diff)}을 더해 {_format_won(capped)}이다."
            return DeterministicExecutionResult(
                answer=answer,
                kind="annual_salary_adjustment",
                steps=[
                    "질문을 연봉제본봉 조정 계산형 질의로 분류했습니다.",
                    f"질문에서 기준 연봉제본봉 {_format_won(amount_in_question)}, 직급={grade}, 평가등급={eval_grade}, 기준일={effective_date}를 추출했습니다.",
                    f"연봉차등액 기준표에서 {grade}/{eval_grade} 조합의 차등액 {_format_won(diff)}을 조회했습니다.",
                    f"연봉상한액 기준표에서 {grade} 상한값 {(_format_won(cap) if cap is not None else '없음')}을 조회했습니다.",
                    f"기준 연봉제본봉 {_format_won(amount_in_question)} + 차등액 {_format_won(diff)} = {_format_won(adjusted)}로 1차 계산했습니다.",
                    (
                        f"1차 계산값 {_format_won(adjusted)}이 상한 {_format_won(cap)}을 초과해 최종 금액을 {_format_won(capped)}으로 조정했습니다."
                        if cap_applied else
                        f"1차 계산값 {_format_won(adjusted)}이 상한 이내라 최종 금액을 {_format_won(capped)}으로 확정했습니다."
                    ),
                    "계산 결과를 최종 답 문장에 반영했습니다.",
                ],
                values={
                    "base_amount": amount_in_question,
                    "diff": diff,
                    "cap": cap,
                    "adjusted": adjusted,
                    "effective_date": effective_date,
                    "final_amount": capped,
                },
            )

    if minimum_amount is not None and _contains_any(question, ["연봉차등", "차등액"]) and _contains_any(question, ["모두", "나열"]):
        rows = provider.list_salary_diffs(minimum_amount, effective_date)
        if rows:
            summary = ", ".join(f"{row['grade']} {row['eval']}" for row in rows)
            return DeterministicExecutionResult(
                answer=f"연봉차등액이 {int(minimum_amount):,}원 이상인 조합은 {summary}의 {len(rows)}건이다.",
                kind="salary_diff_listing",
                steps=[
                    "질문을 연봉차등액 조건 목록형 질의로 분류했습니다.",
                    f"질문에서 최소 차등액 조건 {_format_won(minimum_amount)}과 기준일 {effective_date}를 추출했습니다.",
                    f"연봉차등액 기준표 전체에서 조건 이상인 조합을 조회해 {_format_row_count(len(rows))}을 찾았습니다.",
                    f"조회된 조합들을 {summary}로 정리했습니다.",
                    "정리된 조합 목록과 건수를 최종 답 문장에 반영했습니다.",
                ],
                values={"rows": rows, "effective_date": effective_date},
            )

    requested_parts: List[str] = []
    if "직책급" in question:
        requested_parts.append("position_pay")
    if _contains_any(question, ["연봉차등액", "차등액"]):
        requested_parts.append("salary_diff")
    if _contains_any(question, ["연봉상한액", "연봉상한", "상한액"]):
        requested_parts.append("salary_cap")
    if _contains_any(question, ["평가상여금 지급률", "상여금 지급률"]):
        requested_parts.append("bonus_rate")

    if grade and position and eval_grade and len(requested_parts) >= 2:
        parts: List[str] = []
        steps: List[str] = []
        values: Dict[str, Any] = {}
        if "position_pay" in requested_parts:
            amount = provider.get_position_pay(step_grade or grade, position, effective_date)
            if amount is not None:
                parts.append(f"직책급 {_format_won(amount)}")
                steps.append(f"직책급 조회: grade={step_grade or grade}, position={position}, effective_date={effective_date}")
                values["position_pay"] = amount
        if "bonus_rate" in requested_parts:
            rate = provider.get_bonus_rate(position, eval_grade, effective_date)
            if rate is not None:
                parts.append(f"평가상여금 지급률 {_format_percent(rate)}")
                steps.append(f"상여금 지급률 조회: position={position}, eval={eval_grade}, effective_date={effective_date}")
                values["bonus_rate"] = rate
        if "salary_diff" in requested_parts:
            diff = provider.get_salary_diff(grade, eval_grade, effective_date)
            if diff is not None:
                parts.append(f"연봉차등액 {_format_won(diff)}")
                steps.append(f"연봉차등액 조회: grade={grade}, eval={eval_grade}, effective_date={effective_date}")
                values["salary_diff"] = diff
        if "salary_cap" in requested_parts:
            cap = provider.get_salary_cap(grade, effective_date)
            if cap is not None:
                parts.append(f"연봉상한액 {_format_won(cap)}")
                steps.append(f"연봉상한액 조회: grade={grade}, effective_date={effective_date}")
                values["salary_cap"] = cap
        if len(parts) >= 2:
            return DeterministicExecutionResult(
                answer=", ".join(parts) + "이다.",
                kind="compensation_bundle",
                steps=[
                    "질문을 복합 보수 조회형 질의로 분류했습니다.",
                    f"질문에서 직급={grade}, 직책={position}, 평가등급={eval_grade}, 기준일={effective_date}를 추출했습니다.",
                    *steps,
                    f"조회된 항목 {', '.join(parts)}를 한 문장으로 결합했습니다.",
                ],
                values=values,
            )

    if "직책급" in question and grade and position:
        amount = provider.get_position_pay(step_grade or grade, position, effective_date)
        if amount is not None:
            return DeterministicExecutionResult(
                answer=f"{grade} {position}의 직책급은 {_format_won(amount)}이다.",
                kind="position_pay",
                steps=[
                    "질문을 직책급 단일 조회형 질의로 분류했습니다.",
                    f"질문에서 직급={step_grade or grade}, 직책={position}, 기준일={effective_date}를 추출했습니다.",
                    f"직책급 기준표에서 {step_grade or grade}/{position} 조합의 금액 {_format_won(amount)}을 조회했습니다.",
                    "조회된 금액을 최종 답 문장에 반영했습니다.",
                ],
                values={"amount": amount, "effective_date": effective_date},
            )

    if _contains_any(question, ["연봉차등액", "차등액"]) and grade and eval_grade:
        diff = provider.get_salary_diff(grade, eval_grade, effective_date)
        if diff is not None:
            return DeterministicExecutionResult(
                answer=f"{grade} {eval_grade} 평가의 연봉차등액은 {_format_won(diff)}이다.",
                kind="salary_diff",
                steps=[
                    "질문을 연봉차등액 단일 조회형 질의로 분류했습니다.",
                    f"질문에서 직급={grade}, 평가등급={eval_grade}, 기준일={effective_date}를 추출했습니다.",
                    f"연봉차등액 기준표에서 {grade}/{eval_grade} 조합의 금액 {_format_won(diff)}을 조회했습니다.",
                    "조회된 금액을 최종 답 문장에 반영했습니다.",
                ],
                values={"diff": diff, "effective_date": effective_date},
            )

    if _contains_any(question, ["연봉상한액", "연봉상한", "상한액"]) and grade:
        cap = provider.get_salary_cap(grade, effective_date)
        if cap is not None:
            return DeterministicExecutionResult(
                answer=f"{grade} 연봉상한액은 {_format_won(cap)}이다.",
                kind="salary_cap",
                steps=[
                    "질문을 연봉상한액 단일 조회형 질의로 분류했습니다.",
                    f"질문에서 직급={grade}, 기준일={effective_date}를 추출했습니다.",
                    f"연봉상한액 기준표에서 {grade} 상한값 {_format_won(cap)}을 조회했습니다.",
                    "조회된 금액을 최종 답 문장에 반영했습니다.",
                ],
                values={"cap": cap, "effective_date": effective_date},
            )

    if _contains_any(question, ["평가상여금 지급률", "상여금 지급률"]) and position and eval_grade:
        rate = provider.get_bonus_rate(position, eval_grade, effective_date)
        if rate is not None:
            return DeterministicExecutionResult(
                answer=f"{position}의 {eval_grade} 평가상여금 지급률은 {_format_percent(rate)}이다.",
                kind="bonus_rate",
                steps=[
                    "질문을 평가상여금 지급률 단일 조회형 질의로 분류했습니다.",
                    f"질문에서 직책={position}, 평가등급={eval_grade}, 기준일={effective_date}를 추출했습니다.",
                    f"상여금 기준표에서 {position}/{eval_grade} 조합의 지급률 {_format_percent(rate)}을 조회했습니다.",
                    "조회된 지급률을 최종 답 문장에 반영했습니다.",
                ],
                values={"position": position, "eval": eval_grade, "rate": rate, "effective_date": effective_date},
            )

    if _contains_any(question, ["국외본봉", "주재"]) and country and grade:
        row = provider.get_foreign_salary(country, grade)
        if row is not None:
            return DeterministicExecutionResult(
                answer=f"{country} 주재 {grade} 직원의 국외본봉은 월 {int(round(row['amount'])):,} {row['currency']}이다.",
                kind="foreign_salary",
                steps=[
                    "질문을 국외본봉 단일 조회형 질의로 분류했습니다.",
                    f"질문에서 국가={country}, 직급={grade}를 추출했습니다.",
                    f"국외본봉 기준표에서 {country}/{grade} 조합의 금액 {int(round(row['amount'])):,} {row['currency']}를 조회했습니다.",
                    "조회된 금액과 통화단위를 최종 답 문장에 반영했습니다.",
                ],
                values=row,
            )

    if position in EXEC_POSITIONS and ("본봉" in question or "보수" in question):
        amount = provider.get_exec_base(position)
        if amount is not None:
            return DeterministicExecutionResult(
                answer=f"{position}의 연간 본봉은 {_format_won(amount)}이다.",
                kind="executive_base",
                steps=[
                    "질문을 집행간부 본봉 단일 조회형 질의로 분류했습니다.",
                    f"질문에서 집행간부 직책={position}을 추출했습니다.",
                    f"보수기준표에서 {position}의 연간 본봉 {_format_won(amount)}을 조회했습니다.",
                    "조회된 금액을 최종 답 문장에 반영했습니다.",
                ],
                values={"amount": amount},
            )

    if "임금피크제" in question and "지급률" in question:
        if year is not None:
            rate = provider.get_wage_peak_rate(year)
            if rate is not None:
                return DeterministicExecutionResult(
                    answer=f"임금피크제 {year}년차 기본급 지급률은 {_format_decimal(rate)}이다.",
                    kind="wage_peak_rate",
                    steps=[
                        "질문을 임금피크제 지급률 단일 조회형 질의로 분류했습니다.",
                        f"질문에서 적용 연차={year}를 추출했습니다.",
                        f"임금피크제 기준표에서 {year}년차 지급률 {_format_decimal(rate)}을 조회했습니다.",
                        "조회된 지급률을 최종 답 문장에 반영했습니다.",
                    ],
                    values={"year": year, "rate": rate},
                )
        elif _contains_any(question, ["연차별", "적용 대상"]):
            rows = provider.get_wage_peak_rates()
            if rows:
                pieces = ", ".join(f"{row['year']}년차 {_format_decimal(row['rate'])}" for row in rows)
                return DeterministicExecutionResult(
                    answer=f"잔여근무기간이 3년 이하인 직원이 대상이며 지급률은 {pieces}이다.",
                    kind="wage_peak_bundle",
                    steps=[
                        "질문을 임금피크제 연차별 설명형 질의로 분류했습니다.",
                        "규정상 적용 대상을 잔여근무기간 3년 이하 직원으로 고정했습니다.",
                        f"임금피크제 기준표 전체에서 연차별 지급률을 조회해 {_format_row_count(len(rows))}을 확인했습니다.",
                        f"조회된 지급률을 {pieces}로 정리했습니다.",
                        "적용 대상 설명과 지급률 목록을 함께 최종 답 문장에 반영했습니다.",
                    ],
                    values={"rows": rows},
                )

    return None
