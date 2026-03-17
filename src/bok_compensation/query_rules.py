"""Schema-aware query templates and repair helpers for NL query generation."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from bok_compensation.query_retrieval import build_retrieval_context


def _has_all(text: str, *terms: str) -> bool:
    return all(term in text for term in terms)


def _extract_grade_code(text: str) -> Optional[str]:
    match = re.search(r"([1-5]급)", text)
    return match.group(1) if match else None


def _normalize_variables(variables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized = []
    for variable in variables:
        item = dict(variable)
        name = str(item.get("name", "")).replace("$", "").strip()
        if not name:
            continue
        item["name"] = name
        normalized.append(item)
    return normalized


def _entry_metadata(entry: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if entry is None:
        return {}
    metadata = getattr(entry, "metadata", None)
    if isinstance(metadata, dict):
        return metadata
    return {}


def normalize_planner_outputs(
    original_question: str,
    semantic_queries: List[str],
    data_queries: List[str],
) -> Dict[str, List[str]]:
    quantitative_markers = (
        "얼마",
        "금액",
        "지급률",
        "호봉",
        "초봉",
        "국외본봉",
        "연봉상한액",
        "연봉차등액",
        "직책급",
    )

    normalized_semantic: List[str] = []
    normalized_data = list(data_queries)

    for query in semantic_queries:
        if any(marker in query for marker in quantitative_markers):
            normalized_data.append(query)
        else:
            normalized_semantic.append(query)

    if not normalized_semantic and not normalized_data:
        normalized_data.append(original_question)

    return {
        "semantic_queries": normalized_semantic,
        "data_queries": normalized_data,
    }


def typedb_rule_based_plan(question: str) -> Optional[Dict[str, Any]]:
    if _has_all(question, "4급", "호봉"):
        return {
            "typeql": """
match
    $g isa 직급, has 직급코드 \"4급\";
    (소속직급: $g, 구성호봉: $h) isa 호봉체계구성;
    $h has 호봉번호 $n, has 호봉금액 $amt;
sort $n;
""".strip(),
            "variables": [{"name": "n", "type": "integer"}, {"name": "amt", "type": "double"}],
            "explanation": "4급 호봉 목록과 금액을 조회합니다.",
        }

    if _has_all(question, "G5", "초봉"):
        return {
            "typeql": """
match
    $s isa 직렬, has 직렬명 \"종합기획직원\";
    (대상직렬: $s, 적용기준: $std) isa 초임호봉결정;
    $std has 초임호봉번호 $n, has 초임호봉기준설명 $desc;
    $desc contains \"5급\";
    $g isa 직급, has 직급코드 \"5급\";
    (소속직급: $g, 구성호봉: $step) isa 호봉체계구성;
    $step has 호봉번호 $sn, has 호봉금액 $salary;
    $sn == $n;
""".strip(),
            "variables": [{"name": "n", "type": "integer"}, {"name": "salary", "type": "double"}],
            "explanation": "G5 초임호봉과 해당 본봉 금액을 조회합니다.",
        }

    if _has_all(question, "임금피크제", "지급률"):
        return {
            "typeql": """
match
    $w isa 임금피크제기준, has 적용연차 $year, has 임금피크지급률 $rate;
sort $year;
""".strip(),
            "variables": [{"name": "year", "type": "integer"}, {"name": "rate", "type": "double"}],
            "explanation": "임금피크제 연차별 지급률을 조회합니다.",
        }

    grade_code = _extract_grade_code(question)
    if grade_code and _has_all(question, "미국", "국외본봉"):
        return {
            "typeql": """
match
    $g isa 직급, has 직급코드 \"GRADE_CODE\";
    (적용기준: $os, 해당직급: $g) isa 국외본봉결정;
    $os has 국가명 \"미국\", has 국외기본급액 $amt, has 통화단위 $cur;
""".replace("GRADE_CODE", grade_code).strip(),
            "variables": [{"name": "amt", "type": "double"}, {"name": "cur", "type": "string"}],
            "explanation": f"미국 주재 {grade_code} 직원의 국외본봉을 조회합니다.",
        }

    if _has_all(question, "개정이력"):
        return {
            "typeql": """
match
    $h isa 개정이력, has 개정이력설명 $desc, has 개정일 $rev_date;
sort $rev_date;
""".strip(),
            "variables": [{"name": "desc", "type": "string"}, {"name": "rev_date", "type": "datetime"}],
            "explanation": "개정이력 설명과 개정일을 조회합니다.",
        }

    if _has_all(question, "3급", "팀장", "EX"):
        return {
            "typeql": """
match
    $g isa 직급, has 직급코드 \"3급\";
    $pos isa 직위, has 직위명 $posname;
    { $posname == \"팀장\"; };
    $ev isa 평가결과, has 평가등급 \"EX\";
    (적용기준: $pp, 해당직급: $g, 해당직위: $pos) isa 직책급결정;
    $pp has 직책급액 $ppay;
    (적용기준: $diffstd, 해당직급: $g, 해당등급: $ev) isa 연봉차등;
    $diffstd has 연봉차등액코드 $dc; $dc contains \"ADIFF\";
    $diffstd has 차등액 $diff;
    (적용기준: $capstd, 해당직급: $g) isa 연봉상한;
    $capstd has 연봉상한액 $cap;
""".strip(),
            "variables": [
                {"name": "ppay", "type": "double"},
                {"name": "diff", "type": "double"},
                {"name": "cap", "type": "double"},
            ],
            "explanation": "3급 팀장 EX 기준의 직책급, 연봉차등액, 연봉상한액을 조회합니다.",
        }

    if any(term in question for term in ("이상인", "넘는", "초과")) and "차등액" in question:
        import re as _re
        _m = _re.search(r"(\d+)\s*만\s*원", question)
        threshold = float(_m.group(1)) * 10000 if _m else 2000000.0
        return {
            "typeql": f'''
match
    $g isa 직급, has 직급코드 $gc;
    $ev isa 평가결과, has 평가등급 $eg;
    (적용기준: $d, 해당직급: $g, 해당등급: $ev) isa 연봉차등;
    $d has 연봉차등액코드 $dc; $dc contains "ADIFF";
    $d has 차등액 $diff;
    $diff >= {threshold};
sort $diff desc;
'''.strip(),
            "variables": [
                {"name": "gc", "type": "string"},
                {"name": "eg", "type": "string"},
                {"name": "diff", "type": "double"},
            ],
            "explanation": f"연봉차등액이 {int(threshold):,}원 이상인 직급-평가등급 조합을 조회합니다.",
        }

    grade_code = _extract_grade_code(question)
    if grade_code and any(term in question for term in ("본봉 산정", "본봉을 산정", "연봉 산정", "연봉제 본봉")):
        eval_code = None
        for code in ("EX", "EE", "ME", "BE"):
            if code in question.upper():
                eval_code = code
                break
        if eval_code:
            return {
                "typeql": f'''
match
    $g isa 직급, has 직급코드 "{grade_code}";
    $ev isa 평가결과, has 평가등급 "{eval_code}";
    (적용기준: $diffstd, 해당직급: $g, 해당등급: $ev) isa 연봉차등;
    $diffstd has 연봉차등액코드 $dc; $dc contains "ADIFF";
    $diffstd has 차등액 $diff;
'''.strip(),
                "variables": [{"name": "diff", "type": "double"}],
                "explanation": f"{grade_code} {eval_code} 기준 연봉차등액을 조회합니다. 직전 본봉에 차등액(단위: 원)을 더하면 새 본봉입니다.",
            }

    retrieval_plan = retrieval_guided_typedb_plan(question)
    if retrieval_plan is not None:
        return retrieval_plan

    return None


def neo4j_rule_based_plan(question: str) -> Optional[Dict[str, Any]]:
    if _has_all(question, "4급", "호봉"):
        return {
            "cypher": """
MATCH (g:직급 {직급코드: '4급'})-[:호봉체계구성]->(h:호봉)
RETURN h.호봉번호 AS n, h.호봉금액 AS amt
ORDER BY n
""".strip(),
            "explanation": "4급 호봉 목록과 금액을 조회합니다.",
        }

    if _has_all(question, "G5", "초봉"):
        return {
            "cypher": """
MATCH (s:초임호봉기준)-[:대상직렬]->(ct:직렬 {직렬명: '종합기획직원'})
WHERE s.설명 CONTAINS '5급'
WITH s.초임호봉번호 AS n, s.설명 AS desc
MATCH (g:직급 {직급코드: '5급'})-[:호봉체계구성]->(h:호봉 {호봉번호: n})
RETURN n, desc, h.호봉금액 AS salary
""".strip(),
            "explanation": "G5 초임호봉과 해당 본봉 금액을 조회합니다.",
        }

    if _has_all(question, "임금피크제", "지급률"):
        return {
            "cypher": """
MATCH (w:임금피크제기준)
RETURN w.적용연차 AS year, w.임금피크지급률 AS rate
ORDER BY year
""".strip(),
            "explanation": "임금피크제 연차별 지급률을 조회합니다.",
        }

    grade_code = _extract_grade_code(question)
    if grade_code and _has_all(question, "미국", "국외본봉"):
        return {
            "cypher": """
MATCH (o:국외본봉기준 {국가명: '미국'})-[:해당직급]->(g:직급 {직급코드: 'GRADE_CODE'})
RETURN o.국외기본급액 AS amt, o.통화단위 AS cur
""".replace("GRADE_CODE", grade_code).strip(),
            "explanation": f"미국 주재 {grade_code} 직원의 국외본봉을 조회합니다.",
        }

    if _has_all(question, "개정이력"):
        return {
            "cypher": """
MATCH (h:개정이력)
RETURN h.설명 AS desc, h.개정일 AS rev_date
ORDER BY rev_date
""".strip(),
            "explanation": "개정이력 설명과 개정일을 조회합니다.",
        }

    if _has_all(question, "3급", "팀장", "EX"):
        return {
            "cypher": """
MATCH (pp:직책급기준)-[:해당직위]->(:직위 {직위명: '팀장'})
MATCH (pp)-[:해당직급]->(g:직급 {직급코드: '3급'})
MATCH (d:연봉차등액기준)-[:해당직급]->(g)
MATCH (d)-[:해당등급]->(:평가결과 {평가등급: 'EX'})
MATCH (cap:연봉상한액기준)-[:해당직급]->(g)
RETURN pp.직책급액 AS ppay, d.차등액 AS diff, cap.연봉상한액 AS cap
""".strip(),
            "explanation": "3급 팀장 EX 기준의 직책급, 연봉차등액, 연봉상한액을 조회합니다.",
        }

    if any(term in question for term in ("이상인", "넘는", "초과")) and "차등액" in question:
        import re as _re
        _m = _re.search(r"(\d+)\s*만\s*원", question)
        threshold = float(_m.group(1)) * 10000 if _m else 2000000.0
        return {
            "cypher": f'''
MATCH (d:연봉차등액기준)-[:해당직급]->(g:직급)
MATCH (d)-[:해당등급]->(e:평가결과)
WHERE d.차등액 >= {threshold}
RETURN g.직급코드 AS grade, e.평가등급 AS eval, d.차등액 AS diff
ORDER BY diff DESC
'''.strip(),
            "explanation": f"연봉차등액이 {int(threshold):,}원 이상인 직급-평가등급 조합을 조회합니다.",
        }

    grade_code = _extract_grade_code(question)
    if grade_code and any(term in question for term in ("본봉 산정", "본봉을 산정", "연봉 산정", "연봉제 본봉")):
        eval_code = None
        for code in ("EX", "EE", "ME", "BE"):
            if code in question.upper():
                eval_code = code
                break
        if eval_code:
            return {
                "cypher": f'''
MATCH (d:연봉차등액기준)-[:해당직급]->(g:직급 {{직급코드: '{grade_code}'}})
MATCH (d)-[:해당등급]->(:평가결과 {{평가등급: '{eval_code}'}})
RETURN d.차등액 AS diff
LIMIT 1
'''.strip(),
                "explanation": f"{grade_code} {eval_code} 기준 연봉차등액을 조회합니다. 직전 본봉에 차등액(단위: 원)을 더하면 새 본봉입니다.",
            }

    retrieval_plan = retrieval_guided_neo4j_plan(question)
    if retrieval_plan is not None:
        return retrieval_plan

    return None


def retrieval_guided_typedb_plan(question: str) -> Optional[Dict[str, Any]]:
    context = build_retrieval_context(question, backend="typedb")
    intent = str(context.get("intent") or "")
    grade_code = context.get("grade_code")
    eval_grade = context.get("eval_grade")
    country_name = context.get("country_name")
    position_name = context.get("position_name")
    key_binding_enabled = bool(context.get("key_binding_enabled"))

    starting_rule_metadata = _entry_metadata(context.get("starting_rule_entry"))
    position_pay_metadata = _entry_metadata(context.get("position_pay_rule_entry"))
    bonus_rule_metadata = _entry_metadata(context.get("bonus_rule_entry"))

    if intent == "salary_step_table" and grade_code:
        return {
            "typeql": f'''
match
    $g isa 직급, has 직급코드 "{grade_code}";
    (소속직급: $g, 구성호봉: $h) isa 호봉체계구성;
    $h has 호봉번호 $n, has 호봉금액 $amt;
sort $n;
'''.strip(),
            "variables": [{"name": "n", "type": "integer"}, {"name": "amt", "type": "double"}],
            "explanation": f"{grade_code} 호봉 목록과 금액을 조회합니다.",
        }

    if intent == "starting_salary" and grade_code in {"G5", "5급"}:
        return {
            "typeql": '''
match
    $s isa 직렬, has 직렬명 "종합기획직원";
    (대상직렬: $s, 적용기준: $std) isa 초임호봉결정;
    $std has 초임호봉번호 $n, has 초임호봉기준설명 $desc;
    $desc contains "5급";
    $g isa 직급, has 직급코드 "5급";
    (소속직급: $g, 구성호봉: $step) isa 호봉체계구성;
    $step has 호봉번호 $sn, has 호봉금액 $salary;
    $sn == $n;
'''.strip(),
            "variables": [{"name": "n", "type": "integer"}, {"name": "salary", "type": "double"}],
            "explanation": "종합기획직 G5 초임호봉과 해당 본봉 금액을 조회합니다.",
        }

    if intent == "starting_salary" and key_binding_enabled and starting_rule_metadata:
        salary_grade_code = starting_rule_metadata.get("salary_grade_code")
        step_no = starting_rule_metadata.get("initial_step_no")
        track_code = starting_rule_metadata.get("track_code")
        if salary_grade_code and step_no is not None and track_code:
            return {
                "typeql": f'''
match
    $track isa 직렬, has 직렬코드 "{track_code}";
    (대상직렬: $track, 적용기준: $std) isa 초임호봉결정;
    $std has 초임호봉번호 $n;
    {{ $n == {int(step_no)}; }};
    $grade isa 직급, has 직급코드 "{salary_grade_code}";
    (소속직급: $grade, 구성호봉: $step) isa 호봉체계구성;
    $step has 호봉번호 $step_no, has 호봉금액 $salary;
    {{ $step_no == $n; }};
'''.strip(),
                "variables": [{"name": "n", "type": "integer"}, {"name": "salary", "type": "double"}],
                "explanation": f"{starting_rule_metadata.get('track_name')} 초임호봉과 해당 본봉 금액을 조회합니다.",
            }

    if intent == "wage_peak":
        return {
            "typeql": '''
match
    $w isa 임금피크제기준, has 적용연차 $year, has 임금피크지급률 $rate;
sort $year;
'''.strip(),
            "variables": [{"name": "year", "type": "integer"}, {"name": "rate", "type": "double"}],
            "explanation": "임금피크제 연차별 지급률을 조회합니다.",
        }

    if intent == "overseas_salary" and grade_code and country_name:
        return {
            "typeql": f'''
match
    $g isa 직급, has 직급코드 "{grade_code}";
    (적용기준: $os, 해당직급: $g) isa 국외본봉결정;
    $os has 국가명 "{country_name}", has 국외기본급액 $amt, has 통화단위 $cur;
'''.strip(),
            "variables": [{"name": "amt", "type": "double"}, {"name": "cur", "type": "string"}],
            "explanation": f"{country_name} 주재 {grade_code} 직원의 국외본봉을 조회합니다.",
        }

    if intent == "revision_history":
        return {
            "typeql": '''
match
    $h isa 개정이력, has 개정이력설명 $desc, has 개정일 $rev_date;
sort $rev_date;
'''.strip(),
            "variables": [{"name": "desc", "type": "string"}, {"name": "rev_date", "type": "datetime"}],
            "explanation": "개정이력 목록을 조회합니다.",
        }

    if intent == "grade_position_eval_package" and grade_code and position_name and eval_grade:
        include_bonus = any(term in question for term in ("상여금", "지급률"))
        typeql = f'''
match
    $g isa 직급, has 직급코드 "{grade_code}";
    $pos isa 직위, has 직위명 $posname;
    {{ $posname == "{position_name}"; }};
    $ev isa 평가결과, has 평가등급 "{eval_grade}";
    (적용기준: $pp, 해당직급: $g, 해당직위: $pos) isa 직책급결정;
    $pp has 직책급액 $ppay;
    (적용기준: $diffstd, 해당직급: $g, 해당등급: $ev) isa 연봉차등;
    $diffstd has 차등액 $diff;
    (적용기준: $capstd, 해당직급: $g) isa 연봉상한;
    $capstd has 연봉상한액 $cap;
'''.strip()
        variables = [
            {"name": "ppay", "type": "double"},
            {"name": "diff", "type": "double"},
            {"name": "cap", "type": "double"},
        ]
        if include_bonus:
            typeql += '\n    (적용기준: $bonus, 해당직책구분: $pos, 해당등급: $ev) isa 상여금결정;\n    $bonus has 상여금지급률 $bonus_rate;'
            variables.append({"name": "bonus_rate", "type": "double"})
        return {
            "typeql": typeql,
            "variables": variables,
            "explanation": f"{grade_code} {position_name} {eval_grade} 조건의 보수 관련 기준을 조회합니다.",
        }

    if intent == "salary_calculation" and grade_code and eval_grade:
        return {
            "typeql": f'''
match
    $g isa 직급, has 직급코드 "{grade_code}";
    $ev isa 평가결과, has 평가등급 "{eval_grade}";
    (적용기준: $diffstd, 해당직급: $g, 해당등급: $ev) isa 연봉차등;
    $diffstd has 차등액 $diff;
limit 1;
'''.strip(),
            "variables": [{"name": "diff", "type": "double"}],
            "explanation": f"{grade_code} {eval_grade} 기준 연봉차등액을 조회합니다. 직전 본봉에 차등액(단위: 원)을 더하면 새 본봉입니다.",
        }

    if intent == "position_pay_lookup" and key_binding_enabled and position_pay_metadata:
        return {
            "typeql": f'''
match
    $position isa 직위, has 직위코드 "{position_pay_metadata['position_code']}", has 직위명 $position_name;
    $grade isa 직급, has 직급코드 "{position_pay_metadata['grade_code']}";
    (적용기준: $rule, 해당직급: $grade, 해당직위: $position) isa 직책급결정;
    $rule has 직책급액 $amount;
'''.strip(),
            "variables": [{"name": "position_name", "type": "string"}, {"name": "amount", "type": "double"}],
            "explanation": f"{position_pay_metadata['grade_code']} {position_pay_metadata['position_name']} 직책급을 조회합니다.",
        }

    if intent == "bonus_rate_lookup" and key_binding_enabled and bonus_rule_metadata:
        return {
            "typeql": f'''
match
    $position isa 직위, has 직위코드 "{bonus_rule_metadata['position_code']}", has 직위명 $position_name;
    $evaluation isa 평가결과, has 평가등급 "{bonus_rule_metadata['eval_grade']}";
    (적용기준: $rule, 해당직책구분: $position, 해당등급: $evaluation) isa 상여금결정;
    $rule has 상여금지급률 $rate;
'''.strip(),
            "variables": [{"name": "position_name", "type": "string"}, {"name": "rate", "type": "double"}],
            "explanation": f"{bonus_rule_metadata['position_name']} {bonus_rule_metadata['eval_grade']} 상여금 지급률을 조회합니다.",
        }

    return None


def retrieval_guided_neo4j_plan(question: str) -> Optional[Dict[str, Any]]:
    context = build_retrieval_context(question, backend="neo4j")
    intent = str(context.get("intent") or "")
    grade_code = context.get("grade_code")
    eval_grade = context.get("eval_grade")
    country_name = context.get("country_name")
    position_name = context.get("position_name")
    key_binding_enabled = bool(context.get("key_binding_enabled"))

    starting_rule_metadata = _entry_metadata(context.get("starting_rule_entry"))
    position_pay_metadata = _entry_metadata(context.get("position_pay_rule_entry"))
    bonus_rule_metadata = _entry_metadata(context.get("bonus_rule_entry"))

    if intent == "salary_step_table" and grade_code:
        return {
            "cypher": f'''
MATCH (g:직급 {{직급코드: '{grade_code}'}})-[:호봉체계구성]->(h:호봉)
RETURN h.호봉번호 AS n, h.호봉금액 AS amt
ORDER BY n
'''.strip(),
            "explanation": f"{grade_code} 호봉 목록과 금액을 조회합니다.",
        }

    if intent == "starting_salary" and grade_code in {"G5", "5급"}:
        return {
            "cypher": '''
MATCH (s:초임호봉기준)-[:대상직렬]->(:직렬 {직렬명: '종합기획직원'})
WHERE s.설명 CONTAINS '5급'
WITH s.초임호봉번호 AS n, s.설명 AS desc
MATCH (g:직급 {직급코드: '5급'})-[:호봉체계구성]->(h:호봉 {호봉번호: n})
RETURN n, desc, h.호봉금액 AS salary
'''.strip(),
            "explanation": "종합기획직 G5 초임호봉과 해당 본봉 금액을 조회합니다.",
        }

    if intent == "starting_salary" and key_binding_enabled and starting_rule_metadata:
        salary_grade_code = starting_rule_metadata.get("salary_grade_code")
        step_no = starting_rule_metadata.get("initial_step_no")
        track_code = starting_rule_metadata.get("track_code")
        if salary_grade_code and step_no is not None and track_code:
            return {
                "cypher": f'''
MATCH (rule:초임호봉기준)-[:대상직렬]->(track:직렬 {{직렬코드: '{track_code}'}})
WHERE rule.초임호봉번호 = {int(step_no)}
MATCH (grade:직급 {{직급코드: '{salary_grade_code}'}})-[:호봉체계구성]->(step:호봉 {{호봉번호: rule.초임호봉번호}})
RETURN rule.초임호봉번호 AS n, step.호봉금액 AS salary
'''.strip(),
                "explanation": f"{starting_rule_metadata.get('track_name')} 초임호봉과 해당 본봉 금액을 조회합니다.",
            }

    if intent == "wage_peak":
        return {
            "cypher": '''
MATCH (w:임금피크제기준)
RETURN w.적용연차 AS year, w.임금피크지급률 AS rate
ORDER BY year
'''.strip(),
            "explanation": "임금피크제 연차별 지급률을 조회합니다.",
        }

    if intent == "overseas_salary" and grade_code and country_name:
        return {
            "cypher": f'''
MATCH (o:국외본봉기준 {{국가명: '{country_name}'}})-[:해당직급]->(g:직급 {{직급코드: '{grade_code}'}})
RETURN o.국외기본급액 AS amt, o.통화단위 AS cur
'''.strip(),
            "explanation": f"{country_name} 주재 {grade_code} 직원의 국외본봉을 조회합니다.",
        }

    if intent == "revision_history":
        return {
            "cypher": '''
MATCH (h:개정이력)
RETURN h.설명 AS desc, h.개정일 AS rev_date
ORDER BY rev_date
'''.strip(),
            "explanation": "개정이력 목록을 조회합니다.",
        }

    if intent == "grade_position_eval_package" and grade_code and position_name and eval_grade:
        include_bonus = any(term in question for term in ("상여금", "지급률"))
        cypher = f'''
MATCH (pp:직책급기준)-[:해당직위]->(:직위 {{직위명: '{position_name}'}})
MATCH (pp)-[:해당직급]->(g:직급 {{직급코드: '{grade_code}'}})
MATCH (d:연봉차등액기준)-[:해당직급]->(g)
MATCH (d)-[:해당등급]->(:평가결과 {{평가등급: '{eval_grade}'}})
MATCH (cap:연봉상한액기준)-[:해당직급]->(g)
'''.strip()
        returns = ["pp.직책급액 AS ppay", "d.차등액 AS diff", "cap.연봉상한액 AS cap"]
        if include_bonus:
            cypher += f"\nMATCH (b:상여금기준)-[:해당직책구분]->(:직위 {{직위명: '{position_name}'}})"
            cypher += f"\nMATCH (b)-[:해당등급]->(:평가결과 {{평가등급: '{eval_grade}'}})"
            returns.append("b.상여금지급률 AS bonus_rate")
        cypher += "\nRETURN " + ", ".join(returns)
        return {
            "cypher": cypher,
            "explanation": f"{grade_code} {position_name} {eval_grade} 조건의 보수 관련 기준을 조회합니다.",
        }

    if intent == "salary_calculation" and grade_code and eval_grade:
        return {
            "cypher": f'''
MATCH (d:연봉차등액기준)-[:해당직급]->(g:직급 {{직급코드: '{grade_code}'}})
MATCH (d)-[:해당등급]->(:평가결과 {{평가등급: '{eval_grade}'}})
RETURN d.차등액 AS diff
LIMIT 1
'''.strip(),
            "explanation": f"{grade_code} {eval_grade} 기준 연봉차등액을 조회합니다. 직전 본봉에 차등액(단위: 원)을 더하면 새 본봉입니다.",
        }

    if intent == "position_pay_lookup" and key_binding_enabled and position_pay_metadata:
        return {
            "cypher": f'''
MATCH (rule:직책급기준)-[:해당직위]->(:직위 {{직위코드: '{position_pay_metadata['position_code']}'}})
MATCH (rule)-[:해당직급]->(:직급 {{직급코드: '{position_pay_metadata['grade_code']}'}})
RETURN rule.직책급액 AS amount
'''.strip(),
            "explanation": f"{position_pay_metadata['grade_code']} {position_pay_metadata['position_name']} 직책급을 조회합니다.",
        }

    if intent == "bonus_rate_lookup" and key_binding_enabled and bonus_rule_metadata:
        return {
            "cypher": f'''
MATCH (rule:상여금기준)-[:해당직책구분]->(:직위 {{직위코드: '{bonus_rule_metadata['position_code']}'}})
MATCH (rule)-[:해당등급]->(:평가결과 {{평가등급: '{bonus_rule_metadata['eval_grade']}'}})
RETURN rule.상여금지급률 AS rate
'''.strip(),
            "explanation": f"{bonus_rule_metadata['position_name']} {bonus_rule_metadata['eval_grade']} 상여금 지급률을 조회합니다.",
        }

    return None


def repair_typedb_plan(question: str, plan: Dict[str, Any]) -> Dict[str, Any]:
    fallback = typedb_rule_based_plan(question)
    if fallback is not None:
        return fallback

    repaired = dict(plan)
    typeql = str(repaired.get("typeql", "")).strip()
    typeql = re.sub(r"'([^']*)'", r'"\1"', typeql)

    variables = _normalize_variables(repaired.get("variables", []))
    repaired["variables"] = variables
    repaired["typeql"] = typeql

    invalid_markers = (" owns ", " plays ", ".", " relates ")
    if any(marker in typeql for marker in invalid_markers):
        return typedb_rule_based_plan(question) or repaired

    return repaired


def repair_neo4j_plan(question: str, plan: Dict[str, Any]) -> Dict[str, Any]:
    fallback = neo4j_rule_based_plan(question)
    if fallback is not None:
        return fallback

    repaired = dict(plan)
    cypher = str(repaired.get("cypher", "")).strip()
    replacements = {
        "직급 {등급:": "직급 {직급코드:",
        "직급 {이름:": "직급 {직급코드:",
        "평가결과 {등급:": "평가결과 {평가등급:",
        "RETURN b.name": "RETURN b.국외기본급액",
        "MATCH (e:개정이력)-[:규정개정]->(r:규정)": "MATCH (h:개정이력)",
    }
    for old, new in replacements.items():
        cypher = cypher.replace(old, new)

    repaired["cypher"] = cypher
    return repaired