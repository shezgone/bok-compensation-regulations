"""Question-level validation for regulation queries."""

import re
from typing import Any, Dict, List, Optional


ANNUAL_SALARY_GRADES = {"1급", "2급", "G1", "G2"}


def extract_step_no(question: str) -> Optional[int]:
    match = re.search(r"(\d+)\s*호봉", question)
    return int(match.group(1)) if match else None


def validate_question(question: str, entities: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    issues: List[str] = []
    grade = entities.get("grade")
    step_no = entities.get("step_no")
    position = entities.get("position")

    if step_no is None:
        step_no = extract_step_no(question)
        if step_no is not None:
            entities["step_no"] = step_no

    if step_no is not None and grade in ANNUAL_SALARY_GRADES:
        issues.append(
            f"{grade}은(는) 연봉제본봉 적용 대상이라 {step_no}호봉 본봉표로 직접 계산할 수 없습니다."
        )

    if step_no is not None and grade is None:
        issues.append(
            f"{step_no}호봉만으로는 금액을 확정할 수 없고 직급 정보가 필요합니다."
        )
        if position is not None:
            issues.append(
                f"{position} 직책은 직급에 따라 직책급이 달라 {position} 정보만으로는 연봉을 계산할 수 없습니다."
            )

    if not issues:
        return None

    message = (
        "질문 조건이 현재 규정 체계와 맞지 않아 금액을 확정할 수 없습니다. "
        + " ".join(issues)
        + " 직전 연봉제본봉 또는 현재 연봉제본봉을 함께 주면 계산할 수 있습니다."
    )
    return {
        "message": message,
        "issues": issues,
    }
