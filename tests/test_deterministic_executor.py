from bok_compensation.deterministic_executor import try_execute, try_execute_regulation


class FakeProvider:
    def __init__(self):
        self.calls = []

    def get_step_amount(self, grade, step_no):
        data = {("5급", 11): 1554000.0}
        return data.get((grade, step_no))

    def get_starting_salary(self, track, grade_hint):
        if track == "종합기획직원" and grade_hint == "5급":
            return {"step_no": 11, "salary_grade": "5급", "desc": "종합기획직원 5급 초임호봉"}
        return None

    def get_salary_diff(self, grade, eval_grade, effective_date=None):
        self.calls.append(("salary_diff", grade, eval_grade, effective_date))
        data = {
            ("1급", "EX"): 3672000.0,
            ("3급", "EX"): 3024000.0,
        }
        return data.get((grade, eval_grade))

    def list_salary_diffs(self, minimum_amount=None, effective_date=None):
        self.calls.append(("list_salary_diffs", minimum_amount, effective_date))
        rows = [
            {"grade": "1급", "eval": "EX", "amount": 3672000.0},
            {"grade": "1급", "eval": "EE", "amount": 2448000.0},
        ]
        if minimum_amount is None:
            return rows
        return [row for row in rows if row["amount"] >= minimum_amount]

    def get_salary_cap(self, grade, effective_date=None):
        self.calls.append(("salary_cap", grade, effective_date))
        data = {"1급": 85728000.0, "3급": 77724000.0}
        return data.get(grade)

    def get_position_pay(self, grade, position, effective_date=None):
        self.calls.append(("position_pay", grade, position, effective_date))
        data = {("3급", "팀장"): 1956000.0}
        return data.get((grade, position))

    def get_bonus_rate(self, position, eval_grade, effective_date=None):
        self.calls.append(("bonus_rate", position, eval_grade, effective_date))
        data = {("팀장", "EX"): 0.85}
        return data.get((position, eval_grade))

    def get_foreign_salary(self, country, grade):
        data = {("미국", "2급"): {"country": country, "grade": grade, "amount": 9760.0, "currency": "USD"}}
        return data.get((country, grade))

    def get_exec_base(self, position):
        data = {"총재": 336710000.0}
        return data.get(position)

    def get_wage_peak_rate(self, year):
        data = {1: 0.9, 2: 0.8, 3: 0.7}
        return data.get(year)

    def get_wage_peak_rates(self):
        return [{"year": 1, "rate": 0.9}, {"year": 2, "rate": 0.8}, {"year": 3, "rate": 0.7}]


def test_executes_starting_salary_question():
    result = try_execute(
        "G5 직원의 초임호봉과 초봉은 얼마인가?",
        {"grade": "G5", "track": "종합기획직원"},
        FakeProvider(),
    )

    assert result is not None
    assert "11호봉" in result.answer
    assert "1,554,000원" in result.answer


def test_executes_step_salary_with_basic_pay_phrase():
    result = try_execute(
        "5급 11호봉 기본급은 얼마인가?",
        {"grade": "5급", "step_no": 11, "topics": ["본봉", "호봉"]},
        FakeProvider(),
    )

    assert result is not None
    assert result.kind == "step_salary"
    assert "1,554,000원" in result.answer


def test_executes_step_salary_from_intent_without_pay_keyword():
    result = try_execute(
        "5급 11호봉 얼마야?",
        {"grade": "5급", "step_no": 11, "intent": "step_salary"},
        FakeProvider(),
    )

    assert result is not None
    assert result.kind == "step_salary"
    assert "1,554,000원" in result.answer


def test_executes_annual_salary_adjustment_with_cap():
    result = try_execute(
        "현재 연봉제본봉이 84,000,000원인 1급 EX 직원의 조정 후 연봉제본봉은 상한 적용 시 얼마인가?",
        {"grade": "1급", "eval": "EX"},
        FakeProvider(),
    )

    assert result is not None
    assert "85,728,000원" in result.answer
    assert "상한" in result.answer


def test_executes_annual_salary_adjustment_with_spaced_phrase():
    provider = FakeProvider()

    result = try_execute(
        "3급 G3 종합기획직원 A가 다음 조건을 모두 충족할 때, 2025년 5월 1일 기준으로 적용되는 연봉제 본봉을 산정하시오.\n"
        "조건:\n"
        "1. 2024년 12월 31일 기준 직전 연봉제 본봉: 60,000,000원\n"
        "2. 2024년도 성과평가 등급: 'EX'",
        {"grade": "3급", "eval": "EX", "effective_date": "2025-05-01"},
        provider,
    )

    assert result is not None
    assert result.kind == "annual_salary_adjustment"
    assert "63,024,000원" in result.answer
    assert len(result.steps) >= 6
    assert any("질문을 연봉제본봉 조정 계산형 질의로 분류" in step for step in result.steps)
    assert any("연봉차등액 기준표" in step for step in result.steps)
    assert any("최종 금액" in step for step in result.steps)
    assert ("salary_diff", "3급", "EX", "2025-05-01") in provider.calls
    assert ("salary_cap", "3급", "2025-05-01") in provider.calls


def test_executes_compensation_bundle_question():
    provider = FakeProvider()
    result = try_execute(
        "3급 팀장이 EX 평가를 받았을 때 직책급, 평가상여금 지급률, 연봉차등액, 연봉상한액을 함께 답하시오.",
        {"grade": "3급", "position": "팀장", "eval": "EX", "effective_date": "2025-06-01"},
        provider,
    )

    assert result is not None
    assert "1,956,000원" in result.answer
    assert "85%" in result.answer
    assert "3,024,000원" in result.answer
    assert "77,724,000원" in result.answer
    assert len(result.steps) >= 5
    assert result.steps[0] == "질문을 복합 보수 조회형 질의로 분류했습니다."
    assert any("직책급 조회" in step for step in result.steps)
    assert any("상여금 지급률 조회" in step for step in result.steps)
    assert any("한 문장으로 결합" in step for step in result.steps)
    assert ("position_pay", "3급", "팀장", "2025-06-01") in provider.calls
    assert ("bonus_rate", "팀장", "EX", "2025-06-01") in provider.calls
    assert ("salary_diff", "3급", "EX", "2025-06-01") in provider.calls
    assert ("salary_cap", "3급", "2025-06-01") in provider.calls


def test_explicit_intent_blocks_regulation_fallback_for_bundle_question():
    question = "3급 팀장 EX 기준 보수 패키지에서 직책급과 연봉차등액, 연봉상한액을 알려줘"

    regulation_result = try_execute_regulation(
        question,
        {"intent": "compensation_bundle", "grade": "3급", "position": "팀장", "eval": "EX"},
    )

    bundle_result = try_execute(
        question,
        {"intent": "compensation_bundle", "grade": "3급", "position": "팀장", "eval": "EX", "effective_date": "2025-06-01"},
        FakeProvider(),
    )

    assert regulation_result is None
    assert bundle_result is not None
    assert bundle_result.kind == "compensation_bundle"
    assert "직책급 1,956,000원" in bundle_result.answer


def test_passes_effective_date_to_single_value_queries():
    provider = FakeProvider()

    position_result = try_execute(
        "2025년 기준 3급 팀장의 직책급은 얼마인가?",
        {"grade": "3급", "position": "팀장", "effective_date": "2025-06-01"},
        provider,
    )
    cap_result = try_execute(
        "2025년 기준 1급 연봉상한액은 얼마인가?",
        {"grade": "1급", "effective_date": "2025-06-01"},
        provider,
    )

    assert position_result is not None
    assert cap_result is not None
    assert ("position_pay", "3급", "팀장", "2025-06-01") in provider.calls
    assert ("salary_cap", "1급", "2025-06-01") in provider.calls


def test_executes_bonus_rate_single_query():
    provider = FakeProvider()

    result = try_execute(
        "2025년 기준 팀장의 EX 평가상여금 지급률은 몇 %인가?",
        {"position": "팀장", "eval": "EX", "effective_date": "2025-06-01"},
        provider,
    )

    assert result is not None
    assert result.kind == "bonus_rate"
    assert "85%" in result.answer
    assert ("bonus_rate", "팀장", "EX", "2025-06-01") in provider.calls


def test_executes_bonus_rate_with_ratio_phrase():
    provider = FakeProvider()

    result = try_execute(
        "2025년 기준 팀장 EX 평가상여금 비율은 얼마인가?",
        {"position": "팀장", "eval": "EX", "effective_date": "2025-06-01", "topics": ["상여금"]},
        provider,
    )

    assert result is not None
    assert result.kind == "bonus_rate"
    assert "85%" in result.answer
    assert ("bonus_rate", "팀장", "EX", "2025-06-01") in provider.calls


def test_executes_salary_diff_listing_with_list_phrase():
    provider = FakeProvider()

    result = try_execute(
        "연봉차등액이 2,000,000원 이상인 조합 목록을 보여줘.",
        {"amount_threshold": 2000000.0, "topics": ["연봉차등"], "effective_date": "2025-06-01"},
        provider,
    )

    assert result is not None
    assert result.kind == "salary_diff_listing"
    assert "1급 EX" in result.answer
    assert "1급 EE" in result.answer
    assert ("list_salary_diffs", 2000000.0, "2025-06-01") in provider.calls


def test_executes_regulation_definition_question():
    result = try_execute_regulation(
        "보수규정의 목적은 무엇인가?",
        {},
    )

    assert result is not None
    assert "위원, 집행간부, 감사 및 직원의 보수와 상여금" in result.answer


def test_executes_regulation_definition_with_variant_phrases():
    purpose_result = try_execute_regulation(
        "보수 규정의 취지는 무엇인가?",
        {},
    )
    overseas_result = try_execute_regulation(
        "해외직원은 누구를 말하나?",
        {},
    )

    assert purpose_result is not None
    assert purpose_result.kind == "regulation_definition"
    assert "보수와 상여금에 관한 사항" in purpose_result.answer
    assert overseas_result is not None
    assert overseas_result.kind == "regulation_definition"
    assert "국외사무소에 근무하는 본부 집행간부 및 직원" in overseas_result.answer


def test_executes_regulation_definition_from_intent_without_definition_marker():
    result = try_execute_regulation(
        "해외직원이란?",
        {"intent": "regulation_definition"},
    )

    assert result is not None
    assert result.kind == "regulation_definition"
    assert "국외사무소에 근무하는 본부 집행간부 및 직원" in result.answer


def test_executes_overseas_overtime_rule_question():
    result = try_execute_regulation(
        "해외직원에게 시간외근무수당을 별도로 지급하는가?",
        {},
    )

    assert result is not None
    assert "지급하지 않는다" in result.answer
    assert "본봉에는 시간외근무수당이 포함된 것으로 본다" in result.answer


def test_executes_article_applicability_question():
    result = try_execute_regulation(
        "제4조와 제14조를 기준으로 기한부 고용계약자에게 상여금이 적용되는지 설명하시오.",
        {"article_no": 4},
    )

    assert result is not None
    assert "제14조가 우선 적용" in result.answer
    assert "상여금이 지급되지 않는다" in result.answer


def test_executes_article_applicability_without_explicit_article_numbers():
    result = try_execute_regulation(
        "기한부 고용계약자도 상여금 대상인가?",
        {},
    )

    assert result is not None
    assert result.kind == "regulation_applicability"
    assert "상여금이 지급되지 않는다" in result.answer
