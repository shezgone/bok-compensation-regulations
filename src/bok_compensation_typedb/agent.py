"""TypeDB MoE Agent — HCX(감독) + Qwen(DB 쿼리) with custom StateGraph.

개선사항:
1. Qwen 쿼리 에러 시 구조화된 힌트 + 자동 재시도 (recursion_limit)
2. create_react_agent → 커스텀 StateGraph (reason → validate → finalize)
3. LLM 기반 구조화된 엔티티 추출
4. 규정 검색 + DB 조회 병렬 실행
5. Fallback 지원을 위한 구조화된 에러 반환
"""

import json
import logging
import operator
import re
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from langgraph.graph import StateGraph, START, END
from langchain_core.tools import tool

from src.bok_compensation_typedb.config import TypeDBConfig
from src.bok_compensation_typedb.connection import get_driver
from typedb.driver import TransactionType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 프롬프트
# ---------------------------------------------------------------------------
QWEN_SCHEMA_PROMPT = """당신은 한국은행 보수규정 전문 TypeDB 쿼리 에이전트(Qwen)입니다.
TypeDB 데이터베이스에서 기준표(수치, 금액, 한도 등)를 조회하는 역할만 담당합니다.
사용자의 질문을 분석하여 `execute_typeql` 도구를 호출하고 결과를 반환하세요.

[TypeDB 스키마 지식]
(Entities)
- 직급 (직급명) 예: "1급", "2급", "3급", "4급", "5급"
- 직위 (직위명) 예: "부서장(가)", "팀장", "반장"
- 평가결과 (평가등급) 예: "EX", "EE", "ME", "BE", "CE"
- 직책급기준 (직책급액)
- 연봉차등액기준 (차등액)
- 연봉상한액기준 (연봉상한액)
- 호봉 (호봉번호, 호봉금액)
- 국외근무지 (지역명) 예: "미국", "일본", "영국", "홍콩"
- 국외본봉기준 (국외본봉액, 통화)

(Relations)
- 직책급결정 (roles: 해당직위, 해당직급, 적용기준)
- 호봉체계구성 (roles: 소속직급, 구성호봉)
- 연봉차등 (roles: 해당등급, 해당직급, 적용기준)
- 연봉상한 (roles: 해당직급, 적용기준)
- 국외본봉결정 (roles: 파견직급, 파견지역, 적용기준)

[TypeQL 규칙 - 3.x 핵심]
1. TypeDB 3.x에서는 `get $var;`, `return $var;` 등의 키워드를 절대 사용하지 않습니다!! 오로지 `match` 블록 내의 변수 선언만으로 반환합니다.
2. 수치 필터링: `... has 연봉차등액 $amt; $amt >= 2000000;` 형식.

<정상 예시>
- 직책급 조회:
  `match $g isa 직급, has 직급명 "3급"; $v isa 직위, has 직위명 "팀장"; $rel (해당직급:$g, 해당직위:$v, 적용기준:$ref) isa 직책급결정; $ref isa 직책급기준, has 직책급액 $amt;`
- 연봉차등액 조회:
  `match $g isa 직급, has 직급명 $g_name; $eval isa 평가결과, has 평가등급 $eval_name; $rel (해당직급:$g, 해당등급:$eval, 적용기준:$ref) isa 연봉차등; $ref isa 연봉차등액기준, has 차등액 $amt; $amt >= 2000000;`

[에러 발생 시]
execute_typeql이 에러를 반환하면 에러 메시지의 hint를 참고하여 쿼리를 수정하고 **반드시** 재시도하세요.
최대 3회까지 시도할 수 있습니다.
"""

HCX_SYSTEM_PROMPT = """당신은 한국은행 보수규정 전문 [하이브리드 RAG 에이전트(Hybrid Reasoning Agent)] (HCX) 입니다.
당신은 두 가지 강력한 도구를 적절히 분업하여 복합적인 계산과 논리적 추론을 수행해야 합니다.

[사용 가능 도구 - 분업 체계]
1. `ask_db_expert`: 기본급, 직책급, 연봉차등액, 연봉상한액, 호봉 등 '기준표(Table)'에 명시된 순수 수치 팩트가 필요할 때 데이터베이스 전문 하위 에이전트(Qwen)에게 자연어로 질문을 던져 수치를 가져옵니다.
2. `search_regulations`: 수치가 아니라 "결근 감액 방식, 징계, 임금피크 지급률, 적용 기준일" 등 계산 공식과 텍스트 규정/예외가 필요할 때 텍스트에서 검색합니다.

[**필수 행동 지침 - 엄격히 준수할 것**]
1. 수식을 모를 경우 절대 임의로 식을 만들어내지 말고 무조건 `search_regulations` 도구를 호출하세요.
2. 기준이 되는 기본 수치(예: XX급 직책급 등)가 필요하면 **반드시 `ask_db_expert` 도구를 호출하여 수치를 얻으세요**.
3. [초강력 경고] 연봉이나 총보수를 계산하라는 질문에 "기본급(직전 연봉제 본봉)" 금액이 없다면, 절대 기타 수당이나 차등액만 더해서 연봉이라고 답하지 마세요. "현재 본봉 금액 정보가 없어 더할 수 없습니다" 라고 명시하세요.
4. 여러 단계가 필요한 질문(초임호봉 확인 후 금액 조회, 차등액 확인 후 상한 비교 등)은 단계별로 도구를 나눠 호출하세요. 한 도구의 결과를 다음 도구의 입력으로 사용하세요.
"""

VALIDATION_PROMPT = """당신은 한국은행 보수규정 답변 검증자입니다.
아래 [질문], [DB 조회 결과], [초안 답변]을 비교하여 검증하세요.

검증 기준:
1. 답변에 포함된 수치가 DB 조회 결과와 일치하는가?
2. 계산 과정이 올바른가? (덧셈/뺄셈/비율 등)
3. 질문에서 요구하지 않은 내용을 임의로 추가하지 않았는가?
4. "연봉제본봉" 없이 연봉 합계를 구한 것은 아닌가?

[질문]
{question}

[DB 조회 결과]
{db_results}

[규정 컨텍스트]
{rules_context}

[초안 답변]
{draft_answer}

검증 결과를 아래 형식으로 작성하세요:
- 판정: PASS 또는 FAIL
- 이유: (한 줄)
- 수정 지시: (FAIL인 경우만, 구체적인 수정 방향)
"""

ENTITY_EXTRACTION_PROMPT = """아래 질문에서 한국은행 보수규정 관련 엔티티를 추출하세요.
JSON 형식으로만 답하세요. 해당 없으면 null.

질문: {question}

추출할 항목:
- grade: 직급 (예: "1급", "2급", "3급", "4급", "5급", "G1"~"G5", null)
- position: 직위 (예: "팀장", "부장", "부서장(가)", "반장", null)
- step_no: 호봉 번호 (정수 또는 null)
- eval_grade: 평가등급 (예: "EX", "EE", "ME", "BE", "CE", "S", "A", "M", null)
- country: 국가 (예: "미국", "일본", null)
- intent: 질문 의도 ("salary_lookup", "salary_calc", "rule_lookup", "comparison", "eligibility")
- current_salary: 질문에 명시된 현재 본봉/연봉 금액 (정수 또는 null)

반드시 JSON만 출력:"""

# ---------------------------------------------------------------------------
# 도구: TypeQL 실행 (에러 힌트 포함)
# ---------------------------------------------------------------------------
TYPEQL_FORBIDDEN = ["get ", "get;", "return ", "fetch ", "limit "]

@tool
def execute_typeql(query: str) -> str:
    """TypeDB 3.x TypeQL 쿼리를 실행하여 기준표 수치를 JSON으로 반환합니다."""
    # 사전 검증: 금지 키워드 체크
    query_lower = query.lower().strip()
    for kw in TYPEQL_FORBIDDEN:
        if kw in query_lower:
            return json.dumps({
                "error": f"TypeQL 3.x 문법 오류: '{kw.strip()}'는 사용 불가",
                "failed_query": query,
                "hint": "TypeDB 3.x에서는 match 블록만 사용합니다. get/return/fetch/limit 키워드를 제거하고 match 블록 안에서 변수를 선언하면 자동 반환됩니다.",
            }, ensure_ascii=False)

    if not query_lower.startswith("match"):
        return json.dumps({
            "error": "쿼리가 'match'로 시작하지 않습니다",
            "failed_query": query,
            "hint": "TypeQL 3.x 쿼리는 반드시 'match'로 시작해야 합니다.",
        }, ensure_ascii=False)

    config = TypeDBConfig()
    driver = get_driver(config)
    try:
        with driver.transaction(config.database, TransactionType.READ) as tx:
            result_iterator = tx.query(query).resolve()
            results = []
            for row in result_iterator:
                row_dict = {}
                for col in row.column_names():
                    concept = row.get(col)
                    if concept.is_attribute():
                        row_dict[col] = concept.get_value()
                    else:
                        row_dict[col] = str(concept)
                results.append(row_dict)

        if not results:
            return json.dumps({
                "status": "empty",
                "message": "쿼리 실행 성공, 결과 0건",
                "hint": "조건(직급명, 직위명 등)의 값이 DB에 존재하는지 확인하세요. 예: '3급'이 아니라 '3급'으로 정확히 매치해야 합니다.",
            }, ensure_ascii=False)
        return json.dumps({"status": "ok", "data": results}, ensure_ascii=False)
    except Exception as e:
        error_msg = str(e)
        hint = "쿼리 문법을 확인하세요."
        if "get" in error_msg.lower() or "return" in error_msg.lower():
            hint = "get/return 키워드를 제거하세요. match 블록만 사용합니다."
        elif "unknown" in error_msg.lower() or "does not exist" in error_msg.lower():
            hint = "엔티티/속성명을 확인하세요. 한국어명(직급, 직위, 호봉 등)을 사용해야 합니다."
        logger.error(f"TypeQL Error: {error_msg}\nQuery: {query}")
        return json.dumps({
            "error": f"TypeQL 실행 오류: {error_msg}",
            "failed_query": query,
            "hint": hint,
        }, ensure_ascii=False)
    finally:
        driver.close()


@tool
def ask_db_expert(question: str) -> str:
    """TypeDB 데이터베이스에서 기준표 수치(금액, 한도, 호봉 등)를 조회할 때 하위 에이전트(Qwen)에게 자연어로 질문을 전달합니다."""
    from src.bok_compensation_typedb.llm import create_qwen_model
    qwen_llm = create_qwen_model(temperature=0)
    qwen_agent = create_react_agent(
        qwen_llm,
        [execute_typeql],
        prompt=QWEN_SCHEMA_PROMPT,
    )
    try:
        res = qwen_agent.invoke(
            {"messages": [HumanMessage(content=question)]},
            config={"recursion_limit": 12},  # 재시도 허용
        )
    except Exception as e:
        return f"DB 조회 실패: {str(e)}"

    query_traces = []
    for msg in res["messages"]:
        if getattr(msg, "tool_calls", None):
            for tcall in msg.tool_calls:
                if tcall.get("name") == "execute_typeql":
                    query_traces.append(f"Sub-Query: {tcall.get('args', {}).get('query', '')}")

    ans = res["messages"][-1].content
    if query_traces:
        return f"{ans}\n\n[내부 쿼리 실행 내역]\n" + "\n".join(query_traces)
    return ans


@tool
def search_regulations(keyword: str) -> str:
    """텍스트 문서에서 징계 감액률, 본봉 계산 규칙, 기준일 등 본문 문맥(Context)을 검색합니다."""
    from src.bok_compensation_context.context_query import select_relevant_rules
    try:
        sections = select_relevant_rules(keyword, top_k=3)
        if not sections:
            return "일치하는 본문 결과가 없습니다."
        return "\n\n".join([sec["content"] for sec in sections])
    except Exception as e:
        return f"Error: {str(e)}"


# ---------------------------------------------------------------------------
# 3. 구조화된 엔티티 추출 (LLM 기반 + 정규식 폴백)
# ---------------------------------------------------------------------------
def _extract_entities_regex(question: str) -> Dict[str, Any]:
    """정규식 폴백 — LLM 호출 실패 시 사용."""
    grade = next(
        (g for g in ["1급", "2급", "3급", "4급", "5급", "6급", "G1", "G2", "G3", "G4", "G5"]
         if g in question),
        None,
    )
    step_match = re.search(r"(\d+)\s*호봉", question)
    step_no = int(step_match.group(1)) if step_match else None

    position = next(
        (p for p in ["부서장(가)", "부서장(나)", "팀장", "부장", "반장"]
         if p in question),
        None,
    )
    eval_grade = next(
        (e for e in ["EX", "EE", "ME", "BE", "CE", "S", "A", "M"]
         if e in question.upper()),
        None,
    )
    country = next(
        (c for c in ["미국", "일본", "영국", "홍콩", "중국", "독일"]
         if c in question),
        None,
    )
    salary_match = re.search(r"(\d{1,3}(?:,\d{3})+)\s*원", question)
    current_salary = int(salary_match.group(1).replace(",", "")) if salary_match else None

    return {
        "grade": grade, "position": position, "step_no": step_no,
        "eval_grade": eval_grade, "country": country, "current_salary": current_salary,
        "intent": "salary_lookup",
    }


def extract_entities(question: str, llm: Any) -> Dict[str, Any]:
    """LLM 기반 구조화된 엔티티 추출. 실패 시 정규식 폴백."""
    try:
        prompt = ENTITY_EXTRACTION_PROMPT.format(question=question)
        response = llm.invoke([HumanMessage(content=prompt)])
        text = response.content.strip()
        # JSON 블록 추출
        json_match = re.search(r"\{[^{}]+\}", text, re.DOTALL)
        if json_match:
            entities = json.loads(json_match.group())
            # 타입 보정
            if entities.get("step_no") is not None:
                entities["step_no"] = int(entities["step_no"])
            if entities.get("current_salary") is not None:
                entities["current_salary"] = int(entities["current_salary"])
            return entities
    except Exception as e:
        logger.warning(f"LLM 엔티티 추출 실패, 정규식 폴백: {e}")
    return _extract_entities_regex(question)


# ---------------------------------------------------------------------------
# 4. 커스텀 StateGraph
# ---------------------------------------------------------------------------
class AgentState(TypedDict):
    question: str
    entities: Dict[str, Any]
    rules_context: str                             # 텍스트 규정 검색 결과
    db_results: str                                # DB 조회 결과
    draft_answer: str                              # HCX 초안
    validation_feedback: str                       # 검증 피드백
    final_answer: str
    iteration: int
    trace_logs: Annotated[List[Dict], operator.add] # 추적 로그 누적


def _entity_extraction_node(state: AgentState) -> dict:
    """질문에서 엔티티 추출."""
    from src.bok_compensation_typedb.llm import create_chat_model
    llm = create_chat_model(temperature=0.0)
    entities = extract_entities(state["question"], llm)
    return {
        "entities": entities,
        "trace_logs": [{
            "module": "EntityExtraction",
            "function": "extract_entities",
            "arguments": {"question": state["question"]},
            "result": json.dumps(entities, ensure_ascii=False),
        }],
    }


def _fetch_rules_node(state: AgentState) -> dict:
    """규정 텍스트 검색 — 병렬 실행 가능."""
    result = search_regulations.invoke(state["question"])
    return {
        "rules_context": result,
        "trace_logs": [{
            "module": "RulesRetrieval",
            "function": "search_regulations",
            "arguments": {"keyword": state["question"]},
            "result": result[:300] + "..." if len(result) > 300 else result,
        }],
    }


def _fetch_db_node(state: AgentState) -> dict:
    """DB 수치 조회 — 병렬 실행 가능."""
    entities = state.get("entities") or {}
    # 수치 조회가 필요 없는 규정 해석 질문은 스킵
    intent = entities.get("intent", "")
    if intent == "eligibility" and not entities.get("grade"):
        return {
            "db_results": "",
            "trace_logs": [{
                "module": "DBRetrieval",
                "function": "ask_db_expert",
                "arguments": {"question": state["question"]},
                "result": "수치 조회 불필요 (규정 해석 질문)",
            }],
        }
    result = ask_db_expert.invoke(state["question"])
    return {
        "db_results": result,
        "trace_logs": [{
            "module": "DBRetrieval",
            "function": "ask_db_expert",
            "arguments": {"question": state["question"]},
            "result": result[:300] + "..." if len(result) > 300 else result,
        }],
    }


def _reason_node(state: AgentState) -> dict:
    """HCX가 수집된 컨텍스트로 초안 답변 생성."""
    from src.bok_compensation_typedb.llm import create_chat_model
    llm = create_chat_model(temperature=0.0)

    rules = state.get("rules_context") or "없음"
    db = state.get("db_results") or "없음"
    feedback = state.get("validation_feedback") or ""
    iteration = state.get("iteration", 0)

    revision_note = ""
    if feedback and iteration > 0:
        revision_note = f"\n\n[이전 답변에 대한 검증 피드백 — 반드시 반영하세요]\n{feedback}"

    prompt = f"""{HCX_SYSTEM_PROMPT}

[질문]
{state['question']}

[규정 텍스트 검색 결과]
{rules}

[DB 수치 조회 결과]
{db}
{revision_note}

위 정보를 종합하여 최종 답변을 작성하세요."""

    response = llm.invoke([HumanMessage(content=prompt)])
    draft = response.content

    return {
        "draft_answer": draft,
        "trace_logs": [{
            "module": "Reasoning",
            "function": "generate_draft_answer",
            "arguments": {"iteration": iteration},
            "result": draft[:300] + "..." if len(draft) > 300 else draft,
        }],
    }


def _validate_node(state: AgentState) -> dict:
    """초안 답변을 DB 결과와 교차 검증."""
    from src.bok_compensation_typedb.llm import create_chat_model
    llm = create_chat_model(temperature=0.0)

    prompt = VALIDATION_PROMPT.format(
        question=state["question"],
        db_results=state.get("db_results") or "없음",
        rules_context=state.get("rules_context") or "없음",
        draft_answer=state.get("draft_answer") or "",
    )
    response = llm.invoke([HumanMessage(content=prompt)])
    feedback = response.content
    iteration = state.get("iteration", 0) + 1

    return {
        "validation_feedback": feedback,
        "iteration": iteration,
        "trace_logs": [{
            "module": "Validation",
            "function": "validate_answer",
            "arguments": {"iteration": iteration},
            "result": feedback[:200] + "..." if len(feedback) > 200 else feedback,
        }],
    }


def _finalize_node(state: AgentState) -> dict:
    """최종 답변 확정."""
    return {
        "final_answer": state.get("draft_answer", ""),
        "trace_logs": [{
            "module": "Finalize",
            "function": "finalize_answer",
            "arguments": {},
            "result": "답변 확정",
        }],
    }


def _route_after_validation(state: AgentState) -> str:
    """검증 결과에 따라 재시도 또는 확정."""
    feedback = state.get("validation_feedback", "")
    iteration = state.get("iteration", 0)

    if iteration >= 2:
        return "finalize"
    if "PASS" in feedback.upper():
        return "finalize"
    return "retry"


def build_typedb_graph() -> Any:
    """커스텀 StateGraph 구성."""
    workflow = StateGraph(AgentState)

    # 노드 등록
    workflow.add_node("extract_entities", _entity_extraction_node)
    workflow.add_node("fetch_rules", _fetch_rules_node)
    workflow.add_node("fetch_db", _fetch_db_node)
    workflow.add_node("reason", _reason_node)
    workflow.add_node("validate", _validate_node)
    workflow.add_node("finalize", _finalize_node)

    # 엔티티 추출 → 병렬 조회 (규정 + DB)
    workflow.add_edge(START, "extract_entities")
    workflow.add_edge("extract_entities", "fetch_rules")
    workflow.add_edge("extract_entities", "fetch_db")

    # 병렬 조회 완료 → 추론
    workflow.add_edge("fetch_rules", "reason")
    workflow.add_edge("fetch_db", "reason")

    # 추론 → 검증
    workflow.add_edge("reason", "validate")

    # 검증 결과에 따라 분기
    workflow.add_conditional_edges("validate", _route_after_validation, {
        "retry": "reason",
        "finalize": "finalize",
    })

    workflow.add_edge("finalize", END)

    return workflow.compile()


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------
def run_query(question: str) -> dict:
    """질문을 받아 TypeDB MoE 파이프라인 실행 후 답변 + trace 반환."""
    graph = build_typedb_graph()
    initial_state: AgentState = {
        "question": question,
        "entities": {},
        "rules_context": "",
        "db_results": "",
        "draft_answer": "",
        "validation_feedback": "",
        "final_answer": "",
        "iteration": 0,
        "trace_logs": [
            {
                "module": "System",
                "function": "Start",
                "arguments": {"mode": "TypeDB Custom StateGraph (HCX+Qwen MoE)"},
                "result": "파이프라인 시작",
            }
        ],
    }

    try:
        result = graph.invoke(initial_state)
        final_answer = result.get("final_answer") or result.get("draft_answer", "")
        trace_logs = result.get("trace_logs", [])
        trace_logs.append({
            "module": "System",
            "function": "End",
            "arguments": {},
            "result": "파이프라인 완료",
        })
        return {"answer": final_answer, "trace_logs": trace_logs}
    except Exception as e:
        logger.error(f"TypeDB Agent 오류: {e}")
        return {
            "answer": f"시스템 오류 발생: {str(e)}",
            "trace_logs": initial_state["trace_logs"] + [{
                "module": "System",
                "function": "Error",
                "arguments": {"error": str(e)},
                "result": "오류 발생",
            }],
        }
