"""
NL 파이프라인 테스트 스위트 — DB 쿼리 정확성 + E2E 검증

두 가지 레벨 테스트:
    1. 직접 쿼리 테스트 (Direct): 알려진 올바른 쿼리를 DB에 실행 → 기대값 비교
    2. E2E 파이프라인 테스트 (NL): 자연어 → LLM 쿼리 생성 → DB 실행 → 결과 검증
         (LLM provider 설정 필요)

사용법:
    PYTHONPATH=src python tests/test_nl_pipeline.py direct neo4j
    PYTHONPATH=src python tests/test_nl_pipeline.py direct typedb
    PYTHONPATH=src python tests/test_nl_pipeline.py e2e neo4j
    PYTHONPATH=src python tests/test_nl_pipeline.py e2e typedb
    PYTHONPATH=src python tests/test_nl_pipeline.py langgraph neo4j
    PYTHONPATH=src python tests/test_nl_pipeline.py langgraph typedb
    PYTHONPATH=src python tests/test_nl_pipeline.py langgraph context
    PYTHONPATH=src python tests/test_nl_pipeline.py compare
    PYTHONPATH=src python tests/test_nl_pipeline.py all
"""

import os
import sys
import json
from pathlib import Path
import traceback
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

# ============================================================
# 테스트 케이스 정의
# ============================================================

@dataclass
class DirectQueryTest:
    """알려진 올바른 쿼리 → 기대값 비교"""
    name: str
    description: str
    cypher: str                          # Neo4j 쿼리
    typeql: str                          # TypeDB 쿼리
    typeql_vars: List[Dict[str, str]]    # TypeDB 변수 추출 설정
    expected_check: str                  # 검증 함수명
    expected_values: Dict[str, Any]      # 기대 값


@dataclass
class E2ETest:
    """자연어 질문 → LLM → DB → 결과 검증"""
    name: str
    question: str
    expected_check: str
    expected_values: Dict[str, Any]


@dataclass
class LangGraphSmokeTest:
    name: str
    question: str
    expected_fragments: List[str] = field(default_factory=list)


@dataclass
class ComparisonRow:
    name: str
    question: str
    neo4j: "TestResult"
    typedb: "TestResult"
    context: "TestResult"


# ---- 직접 쿼리 테스트 ----

DIRECT_TESTS = [
    DirectQueryTest(
        name="5급_11호봉_본봉",
        description="5급 11호봉 본봉금액 확인",
        cypher="""
            MATCH (g:직급 {직급코드: '5급'})-[:호봉체계구성]->(h:호봉 {호봉번호: 11})
            RETURN h.호봉금액 AS amt
        """,
        typeql="""
            match
                $g isa 직급, has 직급코드 "5급";
                (소속직급: $g, 구성호봉: $h) isa 호봉체계구성;
                $h has 호봉번호 11, has 호봉금액 $amt;
        """,
        typeql_vars=[{"name": "amt", "type": "double"}],
        expected_check="exact_value",
        expected_values={"amt": 1554000.0},
    ),
    DirectQueryTest(
        name="3급_50호봉_본봉",
        description="3급 최고호봉(50호봉) 본봉금액",
        cypher="""
            MATCH (g:직급 {직급코드: '3급'})-[:호봉체계구성]->(h:호봉 {호봉번호: 50})
            RETURN h.호봉금액 AS amt
        """,
        typeql="""
            match
                $g isa 직급, has 직급코드 "3급";
                (소속직급: $g, 구성호봉: $h) isa 호봉체계구성;
                $h has 호봉번호 50, has 호봉금액 $amt;
        """,
        typeql_vars=[{"name": "amt", "type": "double"}],
        expected_check="exact_value",
        expected_values={"amt": 6890000.0},
    ),
    DirectQueryTest(
        name="팀장_3급_직책급",
        description="팀장+3급 직책급액 확인",
        cypher="""
            MATCH (pp:직책급기준)-[:해당직위]->(pos:직위 {직위명: '팀장'})
            MATCH (pp)-[:해당직급]->(g:직급 {직급코드: '3급'})
            RETURN pp.직책급액 AS amt
        """,
        typeql="""
            match
                $pos isa 직위, has 직위명 $posname;
                { $posname == "팀장"; };
                $g isa 직급, has 직급코드 "3급";
                (적용기준: $pp, 해당직급: $g, 해당직위: $pos) isa 직책급결정;
                $pp has 직책급액 $amt;
        """,
        typeql_vars=[{"name": "amt", "type": "double"}],
        expected_check="exact_value",
        expected_values={"amt": 1956000.0},
    ),
    DirectQueryTest(
        name="G5_초봉_조회",
        description="G5(종합기획 5급) 초임호봉번호 + 호봉금액",
        cypher="""
            MATCH (s:초임호봉기준)-[:대상직렬]->(ct:직렬 {직렬명: '종합기획직원'})
            WHERE s.설명 CONTAINS '5급'
            WITH s.초임호봉번호 AS n, s.설명 AS desc
            MATCH (g:직급 {직급코드: '5급'})-[:호봉체계구성]->(h:호봉 {호봉번호: n})
            RETURN n, desc, h.호봉금액 AS salary
        """,
        typeql="""
            match
                $s isa 직렬, has 직렬명 "종합기획직원";
                (대상직렬: $s, 적용기준: $std) isa 초임호봉결정;
                $std has 초임호봉번호 $n, has 초임호봉기준설명 $desc;
                $desc contains "5급";
                $g isa 직급, has 직급코드 "5급";
                (소속직급: $g, 구성호봉: $step) isa 호봉체계구성;
                $step has 호봉번호 $sn, has 호봉금액 $salary;
                $sn == $n;
        """,
        typeql_vars=[
            {"name": "n", "type": "integer"},
            {"name": "salary", "type": "double"},
        ],
        expected_check="multi_value",
        expected_values={"n": 11, "salary": 1554000.0},
    ),
    DirectQueryTest(
        name="1급_EX_연봉차등액",
        description="1급+EX 연봉차등액 확인",
        cypher="""
            MATCH (d:연봉차등액기준)-[:해당직급]->(g:직급 {직급코드: '1급'})
            MATCH (d)-[:해당등급]->(ev:평가결과 {평가등급: 'EX'})
            RETURN d.차등액 AS diff
        """,
        typeql="""
            match
                $g isa 직급, has 직급코드 "1급";
                $ev isa 평가결과, has 평가등급 "EX";
                (적용기준: $d, 해당직급: $g, 해당등급: $ev) isa 연봉차등;
                $d has 차등액 $diff;
        """,
        typeql_vars=[{"name": "diff", "type": "double"}],
        expected_check="exact_value",
        expected_values={"diff": 3672000.0},
    ),
    DirectQueryTest(
        name="미국_1급_국외본봉",
        description="미국 주재 1급 국외본봉 확인",
        cypher="""
            MATCH (o:국외본봉기준 {국가명: '미국'})-[:해당직급]->(g:직급 {직급코드: '1급'})
            RETURN o.국외기본급액 AS amt, o.통화단위 AS cur
        """,
        typeql="""
            match
                $g isa 직급, has 직급코드 "1급";
                (적용기준: $os, 해당직급: $g) isa 국외본봉결정;
                $os has 국가명 "미국", has 국외기본급액 $amt, has 통화단위 $cur;
        """,
        typeql_vars=[
            {"name": "amt", "type": "double"},
            {"name": "cur", "type": "string"},
        ],
        expected_check="multi_value",
        expected_values={"amt": 10780.0, "cur": "USD"},
    ),
    DirectQueryTest(
        name="부서장가_EX_상여금지급률",
        description="부서장(가)+EX 평가상여금 지급률 확인",
        cypher="""
            MATCH (b:상여금기준)-[:해당직책구분]->(pos:직위 {직위명: '부서장(가)'})
            MATCH (b)-[:해당등급]->(ev:평가결과 {평가등급: 'EX'})
            RETURN b.상여금지급률 AS rate
        """,
        typeql="""
            match
                $pos isa 직위, has 직위명 $posname;
                { $posname == "부서장(가)"; };
                $ev isa 평가결과, has 평가등급 "EX";
                (적용기준: $b, 해당직책구분: $pos, 해당등급: $ev) isa 상여금결정;
                $b has 상여금지급률 $rate;
        """,
        typeql_vars=[{"name": "rate", "type": "double"}],
        expected_check="exact_value",
        expected_values={"rate": 1.0},
    ),
    DirectQueryTest(
        name="임금피크제_2년차",
        description="임금피크제 2년차 지급률 확인",
        cypher="""
            MATCH (w:임금피크제기준 {적용연차: 2})
            RETURN w.임금피크지급률 AS rate
        """,
        typeql="""
            match
                $w isa 임금피크제기준, has 적용연차 2, has 임금피크지급률 $rate;
        """,
        typeql_vars=[{"name": "rate", "type": "double"}],
        expected_check="exact_value",
        expected_values={"rate": 0.8},
    ),
    DirectQueryTest(
        name="3급_호봉수",
        description="3급 호봉 수 = 30 (21~50)",
        cypher="""
            MATCH (g:직급 {직급코드: '3급'})-[:호봉체계구성]->(h:호봉)
            RETURN h.호봉번호 AS n
        """,
        typeql="""
            match
                $g isa 직급, has 직급코드 "3급";
                (소속직급: $g, 구성호봉: $h) isa 호봉체계구성;
        """,
        typeql_vars=[],
        expected_check="row_count",
        expected_values={"count": 30},
    ),
    DirectQueryTest(
        name="개정이력_건수",
        description="개정이력 9건",
        cypher="""
            MATCH (h:개정이력)
            RETURN h.설명 AS desc
        """,
        typeql="""
            match
                $h isa 개정이력;
        """,
        typeql_vars=[],
        expected_check="row_count",
        expected_values={"count": 9},
    ),
    DirectQueryTest(
        name="총재_보수기준",
        description="총재 본봉 연간 총액 확인",
        cypher="""
            MATCH (b:보수기준 {보수기준명: '총재 본봉'})
            RETURN b.보수기본급액 AS amt
        """,
        typeql="""
            match
                $b isa 보수기준, has 보수기준명 "총재 본봉", has 보수기본급액 $amt;
        """,
        typeql_vars=[{"name": "amt", "type": "double"}],
        expected_check="exact_value",
        expected_values={"amt": 336710000.0},
    ),
    DirectQueryTest(
        name="5급_호봉_범위",
        description="5급 최소/최대 호봉번호 (1~50)",
        cypher="""
            MATCH (g:직급 {직급코드: '5급'})-[:호봉체계구성]->(h:호봉)
            RETURN min(h.호봉번호) AS min_n, max(h.호봉번호) AS max_n
        """,
        typeql="""
            match
                $g isa 직급, has 직급코드 "5급";
                (소속직급: $g, 구성호봉: $h) isa 호봉체계구성;
                $h has 호봉번호 $n;
        """,
        typeql_vars=[{"name": "n", "type": "integer"}],
        expected_check="minmax",
        expected_values={"min": 1, "max": 50},
    ),
]


# ---- E2E 테스트 (LLM 필요) ----

E2E_TESTS = [
    E2ETest(
        name="4급_호봉_목록",
        question="4급의 호봉 목록을 보여줘",
        expected_check="row_count_gte",
        expected_values={"min_count": 35},
    ),
    E2ETest(
        name="G5_초봉_질문",
        question="G5 직원의 초봉은?",
        expected_check="contains_value",
        expected_values={"expected_in_results": [11, 1554000]},
    ),
    E2ETest(
        name="임금피크제_질문",
        question="임금피크제 기본급 지급률은?",
        expected_check="row_count_gte",
        expected_values={"min_count": 3},
    ),
    E2ETest(
        name="미국_2급_국외본봉",
        question="미국 주재 2급 직원의 국외본봉은?",
        expected_check="contains_value",
        expected_values={"expected_in_results": [9760]},
    ),
    E2ETest(
        name="개정이력_질문",
        question="보수규정 개정이력을 알려줘",
        expected_check="row_count_gte",
        expected_values={"min_count": 9},
    ),
    E2ETest(
        name="3급_팀장_EX_종합",
        question="3급 직원이 팀장 직책을 맡고 EX 평가를 받은 경우, 본봉·직책급·상여금지급률·연봉차등액·연봉상한액은?",
        expected_check="contains_value",
        expected_values={"expected_in_results": [1956000, 3024000, 77724000]},
    ),
]


LANGGRAPH_SMOKE_TESTS = [
    LangGraphSmokeTest(
        name="초봉_데이터_질문",
        question="G5 직원의 초봉은?",
        expected_fragments=["1554000", "11"],
    ),
    LangGraphSmokeTest(
        name="규정_해석_질문",
        question="기한부 고용계약자는 상여금을 받을 수 있어?",
    ),
]


LANGGRAPH_COMPLEX_TESTS = [
    LangGraphSmokeTest(
        name="복합_기한부_미국1급",
        question="기한부 고용계약자가 상여금을 받을 수 있는지와, 미국 주재 1급 직원의 국외본봉은 얼마인지 함께 알려줘.",
        expected_fragments=["받을 수 없", "10780", "USD"],
    ),
    LangGraphSmokeTest(
        name="복합_G5_미국2급",
        question="G5 직원의 초봉과 미국 주재 2급 직원의 국외본봉을 함께 알려줘.",
        expected_fragments=["11", "1554000", "9760", "USD"],
    ),
    LangGraphSmokeTest(
        name="복합_기한부_G5",
        question="기한부 고용계약자가 상여금을 받을 수 있는지와 G5 직원의 초봉을 함께 알려줘.",
        expected_fragments=["받을 수 없", "11", "1554000"],
    ),
    LangGraphSmokeTest(
        name="복합_개정이력_임금피크",
        question="보수규정 개정이력과 임금피크제 2년차 지급률을 함께 알려줘.",
        expected_fragments=["개정", "0.8"],
    ),
]


# ============================================================
# 테스트 실행 엔진
# ============================================================

@dataclass
class TestResult:
    name: str
    passed: bool
    detail: str = ""


def check_result(check_type: str, expected: dict, rows: list, var_name: str = None) -> tuple[bool, str]:
    """결과 검증"""
    if check_type == "exact_value":
        if not rows:
            return False, "결과 없음"
        row = rows[0]
        for key, exp_val in expected.items():
            actual = row.get(key)
            if actual is None:
                return False, f"{key}: 값 없음"
            if isinstance(exp_val, float):
                if abs(actual - exp_val) > 0.01:
                    return False, f"{key}: 기대={exp_val:,.0f}, 실제={actual:,.0f}"
            elif actual != exp_val:
                return False, f"{key}: 기대={exp_val}, 실제={actual}"
        return True, ""

    elif check_type == "multi_value":
        if not rows:
            return False, "결과 없음"
        row = rows[0]
        for key, exp_val in expected.items():
            actual = row.get(key)
            if actual is None:
                return False, f"{key}: 값 없음"
            if isinstance(exp_val, float):
                if abs(actual - exp_val) > 0.01:
                    return False, f"{key}: 기대={exp_val:,.0f}, 실제={actual:,.0f}"
            elif isinstance(exp_val, int):
                if int(actual) != exp_val:
                    return False, f"{key}: 기대={exp_val}, 실제={actual}"
            elif str(actual) != str(exp_val):
                return False, f"{key}: 기대={exp_val}, 실제={actual}"
        return True, ""

    elif check_type == "row_count":
        expected_cnt = expected["count"]
        actual = len(rows)
        if actual == expected_cnt:
            return True, ""
        return False, f"기대={expected_cnt}건, 실제={actual}건"

    elif check_type == "row_count_gte":
        min_cnt = expected["min_count"]
        actual = len(rows)
        if actual >= min_cnt:
            return True, ""
        return False, f"최소={min_cnt}건, 실제={actual}건"

    elif check_type == "minmax":
        if not rows:
            return False, "결과 없음"
        vals = [row.get("n") or row.get("min_n") or row.get("cnt") for row in rows]
        # For Cypher (aggregated result)
        if len(rows) == 1 and "min_n" in rows[0]:
            actual_min = rows[0]["min_n"]
            actual_max = rows[0]["max_n"]
        else:
            # For TypeDB (individual rows)
            actual_min = min(v for v in vals if v is not None)
            actual_max = max(v for v in vals if v is not None)
        ok = actual_min == expected["min"] and actual_max == expected["max"]
        if ok:
            return True, ""
        return False, f"기대={expected['min']}~{expected['max']}, 실제={actual_min}~{actual_max}"

    elif check_type == "contains_value":
        if not rows:
            return False, "결과 없음"
        # Flatten all values from all rows
        all_vals = []
        for row in rows:
            for val in row.values():
                if isinstance(val, (int, float)):
                    all_vals.append(val)
        for exp_val in expected["expected_in_results"]:
            found = any(abs(v - exp_val) < 1 for v in all_vals)
            if not found:
                return False, f"값 {exp_val} 을 결과에서 찾을 수 없음"
        return True, ""

    return False, f"알 수 없는 검증 유형: {check_type}"


def save_failure_artifact(
    backend: str,
    test_name: str,
    question: str,
    *,
    plan: Optional[Dict[str, Any]] = None,
    rows: Optional[List[Dict[str, Any]]] = None,
    error: Optional[str] = None,
) -> str:
    output_root = os.getenv("BOK_FAILURE_TRACE_DIR", "").strip()
    if output_root:
        base_dir = Path(output_root)
    else:
        base_dir = Path(__file__).resolve().parents[1] / "artifacts" / "query_failures"

    base_dir.mkdir(parents=True, exist_ok=True)
    slug = "".join(ch if ch.isalnum() else "_" for ch in test_name).strip("_")[:60] or backend
    file_path = base_dir / f"{backend}_{slug}.json"
    payload = {
        "backend": backend,
        "test_name": test_name,
        "question": question,
        "plan": plan,
        "rows": rows,
        "error": error,
    }
    file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(file_path)


# ============================================================
# Neo4j 직접 쿼리 테스트
# ============================================================

def run_neo4j_direct_tests() -> List[TestResult]:
    from bok_compensation_neo4j.config import Neo4jConfig
    from bok_compensation_neo4j.connection import get_driver

    config = Neo4jConfig()
    driver = get_driver(config)
    results = []

    with driver.session(database=config.database) as session:
        for test in DIRECT_TESTS:
            try:
                result = session.run(test.cypher)
                rows = [dict(r) for r in result]
                ok, detail = check_result(test.expected_check, test.expected_values, rows)
                results.append(TestResult(test.name, ok, detail))
            except Exception as e:
                results.append(TestResult(test.name, False, f"오류: {e}"))

    driver.close()
    return results


# ============================================================
# TypeDB 직접 쿼리 테스트
# ============================================================

def run_typedb_direct_tests() -> List[TestResult]:
    from typedb.driver import TransactionType
    from bok_compensation.config import TypeDBConfig
    from bok_compensation.connection import get_driver

    config = TypeDBConfig()
    driver = get_driver()
    results = []

    for test in DIRECT_TESTS:
        try:
            tx = driver.transaction(config.database, TransactionType.READ)
            result = tx.query(test.typeql).resolve()
            raw_rows = list(result)
            tx.close()

            # TypeDB 결과 → dict 변환
            if test.expected_check == "row_count":
                rows = raw_rows  # len() 으로 검증
                ok, detail = check_result(test.expected_check, test.expected_values, rows)
            elif test.expected_check == "minmax":
                rows = []
                for row in raw_rows:
                    rec = {}
                    for var in test.typeql_vars:
                        name = var["name"]
                        vtype = var["type"]
                        concept = row.get(name)
                        if concept is not None:
                            if vtype == "integer":
                                rec[name] = concept.get_integer()
                            elif vtype == "double":
                                rec[name] = concept.get_double()
                            else:
                                rec[name] = concept.get_value()
                    rows.append(rec)
                ok, detail = check_result(test.expected_check, test.expected_values, rows)
            else:
                rows = []
                for row in raw_rows:
                    rec = {}
                    for var in test.typeql_vars:
                        name = var["name"]
                        vtype = var["type"]
                        concept = row.get(name)
                        if concept is not None:
                            if vtype == "integer":
                                rec[name] = concept.get_integer()
                            elif vtype == "double":
                                rec[name] = concept.get_double()
                            else:
                                rec[name] = concept.get_value()
                    rows.append(rec)
                ok, detail = check_result(test.expected_check, test.expected_values, rows)

            results.append(TestResult(test.name, ok, detail))
        except Exception as e:
            results.append(TestResult(test.name, False, f"오류: {e}"))

    driver.close()
    return results


# ============================================================
# E2E 테스트 (LLM 필요)
# ============================================================

def describe_llm_backend() -> str:
    provider = os.getenv("LLM_PROVIDER", "openai-compatible")
    if provider == "ollama":
        model = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:14b-instruct")
        base_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    else:
        model = os.getenv("OPENAI_MODEL", "HCX-GOV-THINK-V1-32B")
        base_url = os.getenv("OPENAI_BASE_URL", "http://211.188.81.250:30402/v1")
    return f"provider={provider}, model={model}, endpoint={base_url}"

def run_neo4j_e2e_tests() -> List[TestResult]:
    from bok_compensation_neo4j.nl_query import nl_to_cypher, execute_cypher
    results = []

    for test in E2E_TESTS:
        parsed = None
        try:
            print(f"\n  ▶ [{test.name}] {test.question}")
            parsed = nl_to_cypher(test.question)
            cypher = parsed["cypher"]
            print(f"    Cypher: {cypher.strip()[:100]}...")
            rows = execute_cypher(cypher)
            print(f"    결과: {len(rows)}건")
            ok, detail = check_result(test.expected_check, test.expected_values, rows)
            results.append(TestResult(test.name, ok, detail))
            if ok:
                print(f"    ✅ 통과")
            else:
                artifact = save_failure_artifact("neo4j", test.name, test.question, plan=parsed, rows=rows, error=detail)
                print(f"    ❌ {detail} (artifact: {artifact})")
        except Exception as e:
            results.append(TestResult(test.name, False, f"오류: {e}"))
            artifact = save_failure_artifact("neo4j", test.name, test.question, plan=parsed, error=str(e))
            print(f"    ❌ 오류: {e} (artifact: {artifact})")

    return results


def run_typedb_e2e_tests() -> List[TestResult]:
    from bok_compensation.nl_query import nl_to_typeql, execute_typeql
    results = []

    for test in E2E_TESTS:
        parsed = None
        try:
            print(f"\n  ▶ [{test.name}] {test.question}")
            parsed = nl_to_typeql(test.question)
            typeql = parsed["typeql"]
            variables = parsed["variables"]
            print(f"    TypeQL: {typeql.strip()[:100]}...")
            rows = execute_typeql(typeql, variables)
            print(f"    결과: {len(rows)}건")
            ok, detail = check_result(test.expected_check, test.expected_values, rows)
            results.append(TestResult(test.name, ok, detail))
            if ok:
                print(f"    ✅ 통과")
            else:
                artifact = save_failure_artifact("typedb", test.name, test.question, plan=parsed, rows=rows, error=detail)
                print(f"    ❌ {detail} (artifact: {artifact})")
        except Exception as e:
            results.append(TestResult(test.name, False, f"오류: {e}"))
            artifact = save_failure_artifact("typedb", test.name, test.question, plan=parsed, error=str(e))
            print(f"    ❌ 오류: {e} (artifact: {artifact})")

    return results


def _run_langgraph_smoke_test(app, test: LangGraphSmokeTest) -> TestResult:
    try:
        final_state = app.invoke(
            {
                "query": test.question,
                "semantic_queries": [],
                "data_queries": [],
                "semantic_results": [],
                "data_results": [],
            }
        )
        final_answer = str(final_state.get("final_answer", "")).strip()
        semantic_results = "\n".join(final_state.get("semantic_results", []))
        data_results = "\n".join(final_state.get("data_results", []))
        combined = "\n".join([final_answer, semantic_results, data_results])

        if not final_answer:
            return TestResult(test.name, False, "최종 응답이 비어 있음")
        if "조회 실패" in combined:
            return TestResult(test.name, False, "LangGraph 내부 데이터 조회 실패")

        normalized_combined = combined.replace(",", "").replace(" ", "")
        for fragment in test.expected_fragments:
            normalized_fragment = fragment.replace(",", "").replace(" ", "")
            if normalized_fragment not in normalized_combined:
                return TestResult(test.name, False, f"기대 조각 `{fragment}` 누락")
        return TestResult(test.name, True, "")
    except Exception as exc:
        return TestResult(test.name, False, f"오류: {exc}")


def run_neo4j_langgraph_smoke_tests() -> List[TestResult]:
    from bok_compensation_neo4j.langgraph_query import create_langgraph

    app = create_langgraph()
    return [_run_langgraph_smoke_test(app, test) for test in LANGGRAPH_SMOKE_TESTS]


def run_typedb_langgraph_smoke_tests() -> List[TestResult]:
    from bok_compensation.langgraph_query import create_langgraph

    app = create_langgraph()
    return [_run_langgraph_smoke_test(app, test) for test in LANGGRAPH_SMOKE_TESTS]


def run_neo4j_langgraph_complex_tests() -> List[TestResult]:
    from bok_compensation_neo4j.langgraph_query import create_langgraph

    app = create_langgraph()
    return [_run_langgraph_smoke_test(app, test) for test in LANGGRAPH_COMPLEX_TESTS]


def run_typedb_langgraph_complex_tests() -> List[TestResult]:
    from bok_compensation.langgraph_query import create_langgraph

    app = create_langgraph()
    return [_run_langgraph_smoke_test(app, test) for test in LANGGRAPH_COMPLEX_TESTS]


def run_context_langgraph_smoke_tests() -> List[TestResult]:
    from bok_compensation_context.langgraph_query import create_langgraph

    app = create_langgraph()
    return [_run_langgraph_smoke_test(app, test) for test in LANGGRAPH_SMOKE_TESTS]


def run_context_langgraph_complex_tests() -> List[TestResult]:
    from bok_compensation_context.langgraph_query import create_langgraph

    app = create_langgraph()
    return [_run_langgraph_smoke_test(app, test) for test in LANGGRAPH_COMPLEX_TESTS]


# ============================================================
# 출력
# ============================================================

def print_results(title: str, results: List[TestResult]):
    passed = sum(1 for r in results if r.passed)
    total = len(results)

    print(f"\n{'='*60}")
    print(f"  {title}: {passed}/{total} 통과")
    print(f"{'='*60}")

    for r in results:
        status = "✅" if r.passed else "❌"
        msg = f"  {status} {r.name}"
        if not r.passed and r.detail:
            msg += f"  → {r.detail}"
        print(msg)

    if passed == total:
        print(f"\n  ✅ 모든 테스트 통과!")
    else:
        print(f"\n  ⚠️  {total - passed}건 실패")
    print()


def print_comparison_table(title: str, rows: List[ComparisonRow]):
    print(f"\n{'='*100}")
    print(f"  {title}")
    print(f"{'='*100}")
    print("| 테스트 | Neo4j | TypeDB | Context | 질문 |")
    print("| --- | --- | --- | --- | --- |")
    for row in rows:
        neo4j_cell = "PASS" if row.neo4j.passed else f"FAIL ({row.neo4j.detail})"
        typedb_cell = "PASS" if row.typedb.passed else f"FAIL ({row.typedb.detail})"
        context_cell = "PASS" if row.context.passed else f"FAIL ({row.context.detail})"
        print(f"| {row.name} | {neo4j_cell} | {typedb_cell} | {context_cell} | {row.question} |")
    print()


def build_comparison_rows() -> List[ComparisonRow]:
    neo4j_results = run_neo4j_langgraph_complex_tests()
    typedb_results = run_typedb_langgraph_complex_tests()
    context_results = run_context_langgraph_complex_tests()
    rows = []
    for test, neo4j_result, typedb_result, context_result in zip(LANGGRAPH_COMPLEX_TESTS, neo4j_results, typedb_results, context_results):
        rows.append(
            ComparisonRow(
                name=test.name,
                question=test.question,
                neo4j=neo4j_result,
                typedb=typedb_result,
                context=context_result,
            )
        )
    return rows


# ============================================================
# 메인
# ============================================================

def main():
    args = sys.argv[1:]
    mode = args[0] if args else "direct"
    target = args[1] if len(args) > 1 else "all"

    if mode == "direct":
        if target in ("neo4j", "all"):
            try:
                results = run_neo4j_direct_tests()
                print_results("Neo4j 직접 쿼리 테스트", results)
            except Exception as e:
                print(f"Neo4j 테스트 실패: {e}")
                traceback.print_exc()

        if target in ("typedb", "all"):
            try:
                results = run_typedb_direct_tests()
                print_results("TypeDB 직접 쿼리 테스트", results)
            except Exception as e:
                print(f"TypeDB 테스트 실패: {e}")
                traceback.print_exc()

    elif mode == "e2e":
        print("\n⚠️  E2E 테스트는 설정된 LLM provider와 DB 연결이 필요합니다.")
        print(f"   {describe_llm_backend()}\n")

        if target in ("neo4j", "all"):
            try:
                results = run_neo4j_e2e_tests()
                print_results("Neo4j E2E 파이프라인 테스트", results)
            except Exception as e:
                print(f"Neo4j E2E 테스트 실패: {e}")
                traceback.print_exc()

        if target in ("typedb", "all"):
            try:
                results = run_typedb_e2e_tests()
                print_results("TypeDB E2E 파이프라인 테스트", results)
            except Exception as e:
                print(f"TypeDB E2E 테스트 실패: {e}")
                traceback.print_exc()

    elif mode == "langgraph":
        print("\n⚠️  LangGraph 스모크 테스트는 설정된 LLM provider와 DB 연결이 필요합니다.")
        print(f"   {describe_llm_backend()}\n")

        if target in ("neo4j", "all"):
            try:
                results = run_neo4j_langgraph_smoke_tests()
                print_results("Neo4j LangGraph 스모크 테스트", results)
            except Exception as e:
                print(f"Neo4j LangGraph 테스트 실패: {e}")
                traceback.print_exc()

        if target in ("typedb", "all"):
            try:
                results = run_typedb_langgraph_smoke_tests()
                print_results("TypeDB LangGraph 스모크 테스트", results)
            except Exception as e:
                print(f"TypeDB LangGraph 테스트 실패: {e}")
                traceback.print_exc()

        if target in ("context", "all"):
            try:
                results = run_context_langgraph_smoke_tests()
                print_results("Context LangGraph 스모크 테스트", results)
            except Exception as e:
                print(f"Context LangGraph 테스트 실패: {e}")
                traceback.print_exc()

    elif mode == "compare":
        print("\n⚠️  복합질문 LangGraph 비교는 설정된 LLM provider와 DB 연결이 필요합니다.")
        print(f"   {describe_llm_backend()}\n")
        try:
            rows = build_comparison_rows()
            print_comparison_table("복합질문 LangGraph 비교표", rows)
        except Exception as e:
            print(f"복합질문 비교 실행 실패: {e}")
            traceback.print_exc()

    elif mode == "all":
        # 직접 쿼리 테스트
        for db in (["neo4j", "typedb"] if target == "all" else [target]):
            if db == "neo4j":
                try:
                    results = run_neo4j_direct_tests()
                    print_results("Neo4j 직접 쿼리 테스트", results)
                except Exception as e:
                    print(f"Neo4j 직접 테스트 실패: {e}")
            elif db == "typedb":
                try:
                    results = run_typedb_direct_tests()
                    print_results("TypeDB 직접 쿼리 테스트", results)
                except Exception as e:
                    print(f"TypeDB 직접 테스트 실패: {e}")

        # E2E 테스트
        print("\n⚠️  E2E 테스트는 설정된 LLM provider와 DB 연결이 필요합니다.\n")
        print(f"   {describe_llm_backend()}\n")
        for db in (["neo4j", "typedb"] if target == "all" else [target]):
            if db == "neo4j":
                try:
                    results = run_neo4j_e2e_tests()
                    print_results("Neo4j E2E 파이프라인 테스트", results)
                except Exception as e:
                    print(f"Neo4j E2E 테스트 실패: {e}")
            elif db == "typedb":
                try:
                    results = run_typedb_e2e_tests()
                    print_results("TypeDB E2E 파이프라인 테스트", results)
                except Exception as e:
                    print(f"TypeDB E2E 테스트 실패: {e}")

        print("\n⚠️  LangGraph 스모크 테스트를 이어서 실행합니다.\n")
        print(f"   {describe_llm_backend()}\n")
        for db in (["neo4j", "typedb"] if target == "all" else [target]):
            if db == "neo4j":
                try:
                    results = run_neo4j_langgraph_smoke_tests()
                    print_results("Neo4j LangGraph 스모크 테스트", results)
                except Exception as e:
                    print(f"Neo4j LangGraph 테스트 실패: {e}")
            elif db == "typedb":
                try:
                    results = run_typedb_langgraph_smoke_tests()
                    print_results("TypeDB LangGraph 스모크 테스트", results)
                except Exception as e:
                    print(f"TypeDB LangGraph 테스트 실패: {e}")

        if target in ("context", "all"):
            try:
                results = run_context_langgraph_smoke_tests()
                print_results("Context LangGraph 스모크 테스트", results)
            except Exception as e:
                print(f"Context LangGraph 테스트 실패: {e}")

        print("\n⚠️  복합질문 LangGraph 비교표를 이어서 출력합니다.\n")
        print(f"   {describe_llm_backend()}\n")
        try:
            rows = build_comparison_rows()
            print_comparison_table("복합질문 LangGraph 비교표", rows)
        except Exception as e:
            print(f"복합질문 비교 실행 실패: {e}")
    else:
        print(f"사용법: python tests/test_nl_pipeline.py [direct|e2e|langgraph|compare|all] [neo4j|typedb|context|all]")


if __name__ == "__main__":
    main()
