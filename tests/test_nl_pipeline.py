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
    PYTHONPATH=src python tests/test_nl_pipeline.py catalog
    PYTHONPATH=src python tests/test_nl_pipeline.py live neo4j
    PYTHONPATH=src python tests/test_nl_pipeline.py live typedb
    PYTHONPATH=src python tests/test_nl_pipeline.py live context
    PYTHONPATH=src python tests/test_nl_pipeline.py compare
    PYTHONPATH=src python tests/test_nl_pipeline.py all
"""

import os
import sys
import json
import re
from pathlib import Path
import traceback
from collections import Counter
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


@dataclass
class CuratedQuestionCase:
    """질문 카탈로그: Copilot이 예상한 답변과 난이도/유형 메타데이터를 함께 저장."""

    case_id: str
    category: str
    difficulty: str
    question: str
    copilot_expected_answer: str


CURATED_QUESTION_CASES = [
    CuratedQuestionCase("Q01", "규정검색", "하", "보수규정의 목적은 무엇인가?", "한국은행법과 한국은행정관에 따라 위원, 집행간부, 감사 및 직원의 보수와 상여금에 관한 사항을 규정하는 것이다."),
    CuratedQuestionCase("Q02", "규정검색", "하", "직원에게서 말하는 보수는 무엇을 뜻하는가?", "직원에게서 보수는 기본급과 제수당을 뜻한다."),
    CuratedQuestionCase("Q03", "규정검색", "하", "기본급은 무엇으로 구성되는가?", "기본급은 본봉과 직책급으로 구성된다."),
    CuratedQuestionCase("Q04", "규정검색", "하", "해외직원의 정의는 무엇인가?", "국외사무소에 근무하는 본부 집행간부 및 직원을 말한다."),
    CuratedQuestionCase("Q05", "규정검색", "하", "승급이란 무엇인가?", "현재의 호봉보다 높은 호봉을 부여하는 것을 말한다."),
    CuratedQuestionCase("Q06", "규정검색", "하", "보수 계산 기간은 어떻게 정해지는가?", "보수는 월급 또는 연봉으로 하되 필요한 경우 일급으로 할 수 있다."),
    CuratedQuestionCase("Q07", "규정검색", "중", "연봉제본봉 적용 대상은 누구인가?", "1급 및 G1, 2급 및 G2, 반장 이상의 직책을 담당하는 3급 및 G3 종합기획직원이다."),
    CuratedQuestionCase("Q08", "규정검색", "중", "임금피크제본봉 적용 대상은 누구인가?", "잔여근무기간이 3년 이하인 직원이다."),
    CuratedQuestionCase("Q09", "규정검색", "중", "기한부 고용계약자에게 제2장 보수와 제3장 상여금 규정이 적용되는가?", "적용되지 않는다."),
    CuratedQuestionCase("Q10", "규정검색", "하", "직원은 다른 직원의 보수를 알려고 해도 되는가?", "안 된다. 자신의 보수를 알리거나 다른 직원의 보수를 알려는 행위를 해서는 안 된다."),
    CuratedQuestionCase("Q11", "규정검색", "하", "파견자, 휴직자 등의 보수 세부사항은 누가 정하는가?", "총재가 정한다."),
    CuratedQuestionCase("Q12", "규정검색", "하", "시간외근무수당은 시간당 보수의 몇 배인가?", "1.5배이다."),
    CuratedQuestionCase("Q13", "규정검색", "중", "시간당 보수는 무엇을 기준으로 계산하는가?", "통상임금 월지급액의 209분의 1로 계산한다."),
    CuratedQuestionCase("Q14", "규정검색", "중", "해외직원에게 시간외근무수당을 별도로 지급하는가?", "지급하지 않는다. 해외직원의 본봉에는 시간외근무수당이 포함된 것으로 본다."),
    CuratedQuestionCase("Q15", "규정검색", "중", "정기상여금의 연간 지급률과 지급 시기는 어떻게 되는가?", "연간 380%이며 6월과 12월 초일에 각 150%, 설·추석 연휴 시작 2영업일 전일에 각 40%를 지급한다."),
    CuratedQuestionCase("Q16", "규정검색", "중", "평가상여금은 언제 지급되는가?", "3월, 5월, 9월의 초일을 지급기준일로 지급된다."),
    CuratedQuestionCase("Q17", "규정검색", "중", "퇴직자에게 퇴직 후 도래하는 설·추석 정기상여금을 지급하는가?", "지급하지 않는다."),
    CuratedQuestionCase("Q18", "규정검색", "중", "조정수당은 어떤 경우 지급할 수 있는가?", "해외직원이 국내외에서 납부하는 소득세가 국내 근무 시 납세액을 초과할 때 그 초과분 범위에서 지급할 수 있다."),
    CuratedQuestionCase("Q19", "계산", "하", "G5 직원의 초임호봉과 초봉은 얼마인가?", "초임호봉은 11호봉이고 초봉은 1,554,000원이다."),
    CuratedQuestionCase("Q20", "계산", "하", "5급 11호봉의 본봉은 얼마인가?", "1,554,000원이다."),
    CuratedQuestionCase("Q21", "계산", "하", "3급 50호봉의 본봉은 얼마인가?", "6,890,000원이다."),
    CuratedQuestionCase("Q22", "계산", "하", "3급 팀장의 직책급은 얼마인가?", "연간 직책급은 1,956,000원이다."),
    CuratedQuestionCase("Q23", "계산", "하", "1급 부서장(가)의 연간 직책급은 얼마인가?", "18,192,000원이다."),
    CuratedQuestionCase("Q24", "계산", "하", "1급 EX 평가의 연봉차등액은 얼마인가?", "3,672,000원이다."),
    CuratedQuestionCase("Q25", "계산", "하", "2급 EE 평가의 연봉차등액은 얼마인가?", "2,232,000원이다."),
    CuratedQuestionCase("Q26", "계산", "하", "3급 EE 평가의 연봉차등액은 얼마인가?", "2,016,000원이다."),
    CuratedQuestionCase("Q27", "계산", "하", "1급 연봉상한액은 얼마인가?", "85,728,000원이다."),
    CuratedQuestionCase("Q28", "계산", "하", "3급 연봉상한액은 얼마인가?", "77,724,000원이다."),
    CuratedQuestionCase("Q29", "계산", "중", "미국 주재 1급 직원의 국외본봉은 얼마인가?", "월 10,780 USD이다."),
    CuratedQuestionCase("Q30", "계산", "중", "미국 주재 2급 직원의 국외본봉은 얼마인가?", "월 9,760 USD이다."),
    CuratedQuestionCase("Q31", "계산", "하", "총재의 연간 본봉은 얼마인가?", "336,710,000원이다."),
    CuratedQuestionCase("Q32", "계산", "하", "감사의 연간 본봉은 얼마인가?", "296,310,000원이다."),
    CuratedQuestionCase("Q33", "계산", "하", "부총재보의 연간 본봉은 얼마인가?", "249,190,000원이다."),
    CuratedQuestionCase("Q34", "계산", "하", "임금피크제 1년차 기본급 지급률은 얼마인가?", "0.9이다."),
    CuratedQuestionCase("Q35", "계산", "하", "임금피크제 2년차 기본급 지급률은 얼마인가?", "0.8이다."),
    CuratedQuestionCase("Q36", "계산", "하", "임금피크제 3년차 기본급 지급률은 얼마인가?", "0.7이다."),
    CuratedQuestionCase("Q37", "계산", "중", "직전 연봉제본봉이 60,000,000원인 3급 EX 직원의 조정 후 연봉제본봉은 얼마인가?", "60,000,000원에 3급 EX 차등액 3,024,000원을 더해 63,024,000원이다."),
    CuratedQuestionCase("Q38", "계산", "중", "직전 연봉제본봉이 70,000,000원인 3급 EE 직원의 조정 후 연봉제본봉은 얼마인가?", "70,000,000원에 3급 EE 차등액 2,016,000원을 더해 72,016,000원이다."),
    CuratedQuestionCase("Q39", "계산", "중", "현재 연봉제본봉이 80,000,000원인 1급 EX 직원의 조정 후 연봉제본봉은 얼마인가?", "80,000,000원에 1급 EX 차등액 3,672,000원을 더한 83,672,000원이다."),
    CuratedQuestionCase("Q40", "계산", "상", "현재 연봉제본봉이 84,000,000원인 1급 EX 직원의 조정 후 연봉제본봉은 상한 적용 시 얼마인가?", "84,000,000원에 3,672,000원을 더하면 87,672,000원이지만 상한 85,728,000원을 적용해 최종 연봉제본봉은 85,728,000원이다."),
    CuratedQuestionCase("Q41", "복합", "중", "연봉차등액이 200만원 이상인 직급과 평가등급 조합을 모두 나열하시오.", "1급 EX, 1급 EE, 2급 EX, 2급 EE, 3급 EX, 3급 EE의 6건이다."),
    CuratedQuestionCase("Q42", "복합", "중", "3급 팀장이 EX 평가를 받았을 때 직책급, 연봉차등액, 연봉상한액은 얼마인가?", "직책급 1,956,000원, 연봉차등액 3,024,000원, 연봉상한액 77,724,000원이다."),
    CuratedQuestionCase("Q43", "복합", "중", "임금피크제 적용 대상과 연차별 지급률은 무엇인가?", "잔여근무기간이 3년 이하인 직원이 대상이며 지급률은 1년차 0.9, 2년차 0.8, 3년차 0.7이다."),
    CuratedQuestionCase("Q44", "복합", "중", "기한부 고용계약자는 상여금을 받을 수 있는가? 근거도 함께 답하시오.", "받을 수 없다. 제14조에 따라 기한부 고용계약자에게는 제2장 보수와 제3장 상여금 규정을 적용하지 않는다."),
    CuratedQuestionCase("Q45", "복합", "중", "G5 직원의 초봉은 얼마이며 어떤 조문을 참고해야 하는가?", "초봉은 11호봉 1,554,000원이며 초임호봉은 제6조와 별표2, 본봉 금액은 별표1을 참고한다."),
    CuratedQuestionCase("Q46", "복합", "중", "미국 주재 2급 직원의 국외본봉은 얼마이며 통화단위는 무엇인가?", "월 9,760 USD이다."),
    CuratedQuestionCase("Q47", "복합", "상", "정기상여금의 연간 지급률과 지급시기를 정리하시오.", "연간 380%이며 6월 초일 150%, 12월 초일 150%, 설 연휴 시작 2영업일 전 40%, 추석 연휴 시작 2영업일 전 40%이다."),
    CuratedQuestionCase("Q48", "복합", "상", "1급 49호봉 팀장의 연봉은? 평가는 EX", "질문 조건이 규정 체계와 맞지 않아 금액을 확정할 수 없다. 1급은 연봉제본봉 적용 대상이라 49호봉 본봉표로 직접 계산할 수 없고 직전 또는 현재 연봉제본봉이 추가로 필요하다."),
    CuratedQuestionCase("Q49", "복합", "상", "3급 팀장이 EX 평가를 받았을 때 직책급, 평가상여금 지급률, 연봉차등액, 연봉상한액을 함께 답하시오.", "직책급 1,956,000원, 평가상여금 지급률 85%, 연봉차등액 3,024,000원, 연봉상한액 77,724,000원이다."),
    CuratedQuestionCase("Q50", "복합", "상", "제4조와 제14조를 기준으로 기한부 고용계약자에게 상여금이 적용되는지 설명하시오.", "제4조는 보수 체계를 규정하지만 제14조가 우선 적용되어 기한부 고용계약자에게는 제3장 상여금 규정이 적용되지 않으므로 상여금이 지급되지 않는다."),
]


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
    __test__ = False

    name: str
    passed: bool
    detail: str = ""


@dataclass
class LiveEvalRecord:
    __test__ = False

    backend: str
    case_id: str
    category: str
    difficulty: str
    question: str
    expected_answer: str
    actual_answer: str
    passed: bool
    detail: str
    numeric_match_ratio: float
    keyword_recall: float
    query_language: str


def run_curated_question_catalog_tests() -> List[TestResult]:
    results: List[TestResult] = []

    if len(CURATED_QUESTION_CASES) == 50:
        results.append(TestResult("카탈로그_문항수", True, "50문항"))
    else:
        results.append(TestResult("카탈로그_문항수", False, f"기대=50, 실제={len(CURATED_QUESTION_CASES)}"))

    category_counts = Counter(case.category for case in CURATED_QUESTION_CASES)
    expected_categories = {"규정검색", "계산", "복합"}
    if set(category_counts) == expected_categories:
        results.append(TestResult("카탈로그_질문유형", True, str(dict(category_counts))))
    else:
        results.append(TestResult("카탈로그_질문유형", False, f"실제 유형={sorted(category_counts)}"))

    difficulty_counts = Counter(case.difficulty for case in CURATED_QUESTION_CASES)
    expected_difficulties = {"하", "중", "상"}
    if set(difficulty_counts) == expected_difficulties:
        results.append(TestResult("카탈로그_난이도", True, str(dict(difficulty_counts))))
    else:
        results.append(TestResult("카탈로그_난이도", False, f"실제 난이도={sorted(difficulty_counts)}"))

    ids = [case.case_id for case in CURATED_QUESTION_CASES]
    if len(ids) == len(set(ids)):
        results.append(TestResult("카탈로그_ID_중복", True, "중복 없음"))
    else:
        results.append(TestResult("카탈로그_ID_중복", False, "ID 중복 존재"))

    questions = [case.question for case in CURATED_QUESTION_CASES]
    if len(questions) == len(set(questions)):
        results.append(TestResult("카탈로그_질문_중복", True, "중복 없음"))
    else:
        results.append(TestResult("카탈로그_질문_중복", False, "질문 중복 존재"))

    empty_expected = [case.case_id for case in CURATED_QUESTION_CASES if not case.copilot_expected_answer.strip()]
    if not empty_expected:
        results.append(TestResult("카탈로그_예상답변", True, "모든 문항에 예상 답변 존재"))
    else:
        results.append(TestResult("카탈로그_예상답변", False, f"예상 답변 누락: {empty_expected}"))

    return results


def _normalize_eval_text(text: str) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]+", "", text).lower()


def _extract_numeric_tokens(text: str) -> List[str]:
    normalized = text.replace(",", "")
    return re.findall(r"\d+(?:\.\d+)?", normalized)


def _canonicalize_numeric_token(token: str) -> str:
    normalized = token.replace(",", "").strip()
    if not normalized:
        return normalized
    try:
        value = float(normalized)
    except ValueError:
        return normalized
    if value.is_integer():
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _expand_numeric_equivalents(token: str) -> List[str]:
    variants = {token}
    try:
        value = float(token)
    except ValueError:
        return sorted(variants)

    if value.is_integer():
        variants.add(str(int(value)))
    if 0 < value < 1:
        percent_value = value * 100
        variants.add(str(int(percent_value)) if percent_value.is_integer() else f"{percent_value:.2f}".rstrip("0").rstrip("."))
    if 1 <= value <= 100:
        decimal_value = value / 100
        variants.add(f"{decimal_value:.2f}".rstrip("0").rstrip("."))
    return sorted(variants)


def _stem_eval_token(token: str) -> str:
    suffixes = [
        "으로부터", "에게서는", "에게서", "에서는", "으로는", "입니다", "합니다", "하였다", "하였다", "한다", "된다",
        "되는", "이다", "였다", "라고", "라고도", "으로", "에서", "에게", "와", "과", "을", "를", "은", "는", "이", "가", "의", "도", "만",
    ]
    for suffix in suffixes:
        if token.endswith(suffix) and len(token) > len(suffix) + 1:
            return token[: -len(suffix)]
    return token


def _extract_keyword_tokens(text: str) -> List[str]:
    stopwords = {
        "이다", "있다", "없다", "한다", "되는가", "무엇인가", "얼마인가", "무엇을", "어떻게", "기준", "지급", "적용",
        "대상", "직원", "직급", "질문", "규정", "현재", "직전", "조정", "후", "연간", "월", "함께", "모두",
        "정리", "설명", "근거", "답하시오", "추가로", "필요하다", "직접", "계산", "최종", "적용해", "적용시", "경우",
        "대해", "같이", "있으며", "그리고", "또는", "으로", "에서", "에게", "이다.", "한다.",
    }
    tokens = re.findall(r"[0-9A-Za-z가-힣]+", text.lower())
    keywords: List[str] = []
    for token in tokens:
        token = _stem_eval_token(token)
        if token.isdigit():
            continue
        if len(token) < 2 and token not in {"g1", "g2", "g3", "g4", "g5", "ex", "ee", "me", "be", "ni"}:
            continue
        if token in stopwords:
            continue
        keywords.append(token)
    return sorted(set(keywords))


def _evaluate_live_answer(expected_answer: str, actual_answer: str) -> tuple[bool, str, float, float]:
    actual_normalized = _normalize_eval_text(actual_answer)
    actual_numbers = {_canonicalize_numeric_token(token) for token in _extract_numeric_tokens(actual_answer)}
    expected_numbers = _extract_numeric_tokens(expected_answer)
    expected_keywords = _extract_keyword_tokens(expected_answer)

    matched_numbers = 0
    for token in expected_numbers:
        variants = {
            _canonicalize_numeric_token(variant)
            for variant in _expand_numeric_equivalents(token)
            if variant
        }
        if variants & actual_numbers:
            matched_numbers += 1
    numeric_match_ratio = matched_numbers / len(expected_numbers) if expected_numbers else 1.0

    matched_keywords = sum(1 for token in expected_keywords if token in actual_normalized)
    keyword_recall = matched_keywords / len(expected_keywords) if expected_keywords else 1.0

    passed = False
    if expected_numbers:
        passed = numeric_match_ratio == 1.0 and (
            not expected_keywords or keyword_recall >= 0.2 or len(expected_numbers) == 1
        )
    else:
        passed = keyword_recall >= 0.4

    detail = f"num={matched_numbers}/{len(expected_numbers)} kw={matched_keywords}/{len(expected_keywords)}"
    return passed, detail, numeric_match_ratio, keyword_recall


def test_live_eval_matches_decimal_numbers_without_false_negative():
    passed, detail, numeric_match_ratio, keyword_recall = _evaluate_live_answer(
        "임금피크제 1년차 기본급 지급률은 0.9이다.",
        "임금피크제 1년차 기본급 지급률은 0.9이다.",
    )

    assert passed is True, detail
    assert numeric_match_ratio == 1.0
    assert keyword_recall == 1.0


def test_live_eval_accepts_percent_equivalent_for_decimal_rate():
    passed, detail, numeric_match_ratio, keyword_recall = _evaluate_live_answer(
        "평가상여금 지급률은 0.85이다.",
        "평가상여금 지급률은 85%이다.",
    )

    assert passed is True, detail
    assert numeric_match_ratio == 1.0


def _get_live_backend_runner(backend: str):
    if backend == "neo4j":
        from bok_compensation_neo4j.nl_query import run_with_trace

        return run_with_trace
    if backend == "typedb":
        from bok_compensation.nl_query import run_with_trace

        return run_with_trace
    if backend == "context":
        from bok_compensation_context.context_query import run_with_trace

        return run_with_trace
    raise ValueError(f"지원하지 않는 backend: {backend}")


def run_live_catalog_tests(backend: str, limit: Optional[int] = None) -> tuple[List[TestResult], List[LiveEvalRecord]]:
    runner = _get_live_backend_runner(backend)
    selected_cases = CURATED_QUESTION_CASES[: limit or len(CURATED_QUESTION_CASES)]
    results: List[TestResult] = []
    records: List[LiveEvalRecord] = []

    for index, case in enumerate(selected_cases, start=1):
        print(f"\n  ▶ [{backend}] {case.case_id} {case.question}")
        try:
            payload = runner(case.question)
            actual_answer = str(payload.get("answer", "")).strip()
            trace = payload.get("trace", {}) or {}
            passed, detail, numeric_match_ratio, keyword_recall = _evaluate_live_answer(
                case.copilot_expected_answer,
                actual_answer,
            )
            query_language = str(trace.get("query_language", ""))
            result_detail = f"{detail}; lang={query_language}"
            if not passed:
                snippet = actual_answer.replace("\n", " ")[:160]
                result_detail = f"{result_detail}; answer={snippet}"

            results.append(TestResult(f"{case.case_id}_{case.category}_{case.difficulty}", passed, result_detail))
            records.append(
                LiveEvalRecord(
                    backend=backend,
                    case_id=case.case_id,
                    category=case.category,
                    difficulty=case.difficulty,
                    question=case.question,
                    expected_answer=case.copilot_expected_answer,
                    actual_answer=actual_answer,
                    passed=passed,
                    detail=result_detail,
                    numeric_match_ratio=numeric_match_ratio,
                    keyword_recall=keyword_recall,
                    query_language=query_language,
                )
            )
            print(f"    {'✅' if passed else '❌'} {result_detail}")
        except Exception as exc:
            detail = f"오류: {exc}"
            results.append(TestResult(f"{case.case_id}_{case.category}_{case.difficulty}", False, detail))
            records.append(
                LiveEvalRecord(
                    backend=backend,
                    case_id=case.case_id,
                    category=case.category,
                    difficulty=case.difficulty,
                    question=case.question,
                    expected_answer=case.copilot_expected_answer,
                    actual_answer="",
                    passed=False,
                    detail=detail,
                    numeric_match_ratio=0.0,
                    keyword_recall=0.0,
                    query_language="",
                )
            )
            print(f"    ❌ {detail}")

        if index % 10 == 0:
            passed_count = sum(1 for record in records if record.passed)
            print(f"    진행률: {index}/{len(selected_cases)} (통과 {passed_count}건)")

    return results, records


def print_live_eval_summary(title: str, records: List[LiveEvalRecord]) -> None:
    total = len(records)
    passed = sum(1 for record in records if record.passed)
    print(f"\n{'='*100}")
    print(f"  {title}")
    print(f"{'='*100}")
    print(f"총 문항 수: {total}")
    print(f"통과 수: {passed}")
    print(f"통과율: {passed / total:.1%}" if total else "통과율: N/A")

    category_counts = Counter((record.category, record.passed) for record in records)
    print("\n[유형별 통과율]")
    for category in ["규정검색", "계산", "복합"]:
        category_total = sum(count for (name, _), count in category_counts.items() if name == category)
        category_passed = category_counts.get((category, True), 0)
        print(f"- {category}: {category_passed}/{category_total} ({(category_passed / category_total):.1%})" if category_total else f"- {category}: 0/0")

    difficulty_counts = Counter((record.difficulty, record.passed) for record in records)
    print("\n[난이도별 통과율]")
    for difficulty in ["하", "중", "상"]:
        difficulty_total = sum(count for (name, _), count in difficulty_counts.items() if name == difficulty)
        difficulty_passed = difficulty_counts.get((difficulty, True), 0)
        print(f"- {difficulty}: {difficulty_passed}/{difficulty_total} ({(difficulty_passed / difficulty_total):.1%})" if difficulty_total else f"- {difficulty}: 0/0")

    failures = [record for record in records if not record.passed]
    if failures:
        print("\n[대표 실패 사례]")
        for record in failures[:10]:
            answer_snippet = record.actual_answer.replace("\n", " ")[:140]
            print(f"- {record.case_id} {record.category}/{record.difficulty}: {record.detail}")
            print(f"  질문: {record.question}")
            print(f"  예상: {record.expected_answer}")
            print(f"  실제: {answer_snippet}")


def print_curated_question_catalog() -> None:
    category_counts = Counter(case.category for case in CURATED_QUESTION_CASES)
    difficulty_counts = Counter(case.difficulty for case in CURATED_QUESTION_CASES)

    print(f"\n{'='*100}")
    print("  Copilot 예상답변 기반 50문항 카탈로그")
    print(f"{'='*100}")
    print(f"총 문항 수: {len(CURATED_QUESTION_CASES)}")
    print(f"질문 유형 분포: {dict(category_counts)}")
    print(f"난이도 분포: {dict(difficulty_counts)}")
    print("\n| ID | 유형 | 난이도 | 질문 | Copilot 예상 답변 |")
    print("| --- | --- | --- | --- | --- |")
    for case in CURATED_QUESTION_CASES:
        print(f"| {case.case_id} | {case.category} | {case.difficulty} | {case.question} | {case.copilot_expected_answer} |")
    print()


def test_curated_question_catalog_integrity():
    results = run_curated_question_catalog_tests()
    failed = [result for result in results if not result.passed]
    assert not failed, "; ".join(f"{result.name}: {result.detail}" for result in failed)


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
        model = os.getenv("OPENAI_MODEL", "your-model-name")
        base_url = os.getenv("OPENAI_BASE_URL", "http://localhost:8000/v1")
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

    elif mode == "catalog":
        results = run_curated_question_catalog_tests()
        print_results("Copilot 예상답변 50문항 카탈로그 무결성 테스트", results)
        print_curated_question_catalog()

    elif mode == "live":
        print("\n⚠️  라이브 평가는 현재 run_with_trace 기반 그래프 퍼스트 런타임을 직접 호출합니다.")
        print(f"   {describe_llm_backend()}\n")

        if target not in ("neo4j", "typedb", "context"):
            print("live 모드는 neo4j, typedb, context 중 하나를 target으로 지정해야 합니다.")
            return

        limit = int(args[2]) if len(args) > 2 else None
        results, records = run_live_catalog_tests(target, limit=limit)
        print_results(f"{target} 라이브 50문항 검증", results)
        print_live_eval_summary(f"{target} 라이브 50문항 검증 요약", records)

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
        results = run_curated_question_catalog_tests()
        print_results("Copilot 예상답변 50문항 카탈로그 무결성 테스트", results)
    else:
        print(f"사용법: python tests/test_nl_pipeline.py [direct|e2e|langgraph|catalog|live|compare|all] [neo4j|typedb|context|all]")


if __name__ == "__main__":
    main()
