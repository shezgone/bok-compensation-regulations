import json
import logging
from typing import TypedDict, Annotated, Sequence, Any
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool

from src.bok_compensation_typedb.config import TypeDBConfig
from src.bok_compensation_typedb.connection import get_driver
from typedb.driver import TransactionType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TYPEDB_SCHEMA_INFO = """
당신은 한국은행 보수규정 전문 [하이브리드 RAG 에이전트(Hybrid Reasoning Agent)] 입니다.
당신은 두 가지 강력한 도구를 활용해 복합적인 계산과 논리적 추론을 수행해야 합니다:

1. `execute_typeql`: 기본급, 직책급, 연봉차등액, 연봉상한액, 호봉 등 '기준표(Table)'에 명시된 순수 수치 팩트를 TypeDB 그래프에서 직접 조회할 때 사용합니다.
2. `search_regulations`: 수치가 아니라 "결근 감액 방식, 징계, 임금피크 지급률, 적용 기준일" 등 계산 공식과 텍스트 규정/예외가 필요할 때 텍스트에서 검색합니다.

[**필수 행동 지침 - 엄격히 준수할 것**]
1. 사용자의 질문에 조건(결근, 직위해제, 승급, 임금피크, 기한부 계약자 등)이 있거나, "연봉", "연봉제 본봉", "조정 후 연봉" 등의 산정 수식을 모를 경우 절대 임의로 식을 만들어내지 말고 **자신의 지식을 배제한 채 무조건 `search_regulations` 도구를 제일 먼저 호출하여 관련 규정/수식을 문맥에서 검색하세요**.
   * "연봉 공식을 알려줘"라는 생각 대신, `search_regulations`에 "연봉 산정"을 질의하세요.
2. 기준이 되는 기본 수치(예: XX급 직책급, 연봉차등액 등)가 필요하면 **반드시 `execute_typeql` 도구를 호출하여 정확한 숫자를 가져오세요**.
3. [초강력 경고] 연봉이나 총보수를 계산하라는 질문에 "기본급(직전 연봉제 본봉)" 식 항목의 금액이 주어지지 않았다면, **절대로!! 기타 수당이나 연봉차등액만 임의로 가져와 더해서 연봉이라고 답변하지 마세요.**
   * 절대 금지 행동: `최종 연봉 = 직책급액 + 차등액 = 390만 원` 이따위로 머릿속 상상으로 사칙연산을 수행해서 연봉이라고 단정 짓는 행위. 
   * 올바른 행동: "현재 연봉제 본봉 금액 정보가 주어져 있지 않으므로 덧셈을 통한 정확한 연봉 총액(조정 후 연봉제본봉) 산출은 불가합니다. 단, 질문하신 조건에 따른 연봉차등액은 X원, 직책급은 Y원입니다." 라고만 답변하세요.
4. "G5 직원의 초봉" 같이 2단계가 필요한 경우, 먼저 `search_regulations`로 초임호봉이 몇 호봉인지 알아낸 뒤, `execute_typeql`로 해당 호봉의 금액을 가져오세요.
5. 복합 질문은 순차적으로 도구를 호출하여 종합하세요.

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

[TypeQL 규칙 - 3.x 대응 핵심 중요 사항!]
1. TypeDB 3.x에서는 `get $var;`, `return $var;` 등의 키워드를 절대 사용하지 않습니다!! 
   (오답: `... has 직책급액 $amt; get $amt;` -> 정답: `... has 직책급액 $amt;`)
   오로지 `match` 블록 내의 변수 선언만으로 모든 조회 변수를 반환합니다. 쿼리의 마지막은 항상 세미콜론(`;`)입니다.
   어떤 상황에서도 `get`, `return` 키워드를 문장 끝에 붙이지 마세요.

2. 논리 연산자(>= 등)의 사용법
   수치 필터링 시에는 `... has 연봉차등액 $amt; $amt >= 2000000;` 와 같이 세미콜론으로 구분하여 필터링합니다.

3. 관계(Relation) 조회 구문
   관계에 역할을 바인딩할 때, 다른 변수에 연관지어 매칭합니다.
   `$rel (해당직급:$g, 해당직위:$p, 적용기준:$ref) isa 직책급결정;` 처럼 `$rel`을 선언할 수도 있지만,
   `get`을 빼고 끝내야만 올바른 파싱이 이뤄집니다.

<정상 예시 모음>
- 직책급 조회:
  `match $g isa 직급, has 직급명 "3급"; $v isa 직위, has 직위명 "팀장"; $rel (해당직급:$g, 해당직위:$v, 적용기준:$ref) isa 직책급결정; $ref isa 직책급기준, has 직책급액 $amt;`
- 연봉차등액 조회 + 이상 필터:
  `match $g isa 직급, has 직급명 $g_name; $eval isa 평가결과, has 평가등급 $eval_name; $rel (해당직급:$g, 해당등급:$eval, 적용기준:$ref) isa 연봉차등; $ref isa 연봉차등액기준, has 차등액 $amt; $amt >= 2000000;`
"""

@tool
def execute_typeql(query: str) -> str:
    """TypeDB 3.x TypeQL 쿼리를 날려 기준표 수치를 JSON 파싱하여 반환합니다."""
    try:
        config = TypeDBConfig()
        driver = get_driver(config)
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
        driver.close()
        
        if not results:
            return "Query executed successfully but returned no results. 조건 오류 혹은 스키마 불일치입니다."
        return json.dumps(results, ensure_ascii=False)
    except Exception as e:
        logger.error(f"TypeQL Error: {str(e)}\nQuery: {query}")
        return f"Error executing TypeQL query: {str(e)}"

@tool
def search_regulations(keyword: str) -> str:
    """텍스트 문서에서 징계 감액률, 본봉 계산 규칙, 기준일 등 본문 문맥(Context)을 검색합니다."""
    from src.bok_compensation_context.context_query import select_relevant_sections
    try:
        sections = select_relevant_sections(keyword, top_k=3)
        if not sections:
            return "일치하는 본문 결과가 없습니다."
        return "\n\n".join([sec["content"] for sec in sections])
    except Exception as e:
        return f"Error: {str(e)}"

def build_typedb_agent() -> Any:
    from src.bok_compensation_typedb.llm import create_chat_model
    llm = create_chat_model(temperature=0)
    tools = [execute_typeql, search_regulations]
    # LangGraph prebuilt ReAct Agent 사용
    return create_react_agent(llm, tools, prompt=TYPEDB_SCHEMA_INFO)

def run_query(question: str):
    """
    기존 TypeDB ReAct Agent를 완전한 LangGraph 하이브리드 노드로 업그레이드하였습니다.
    """
    agent = build_typedb_agent()
    trace_calls = [{"module": "System", "function": "Start", "arguments": {"mode": "LangGraph Hybrid TypeDB"}, "result": "검색 루프 시작"}]
    
    try:
        result = agent.invoke({"messages": [HumanMessage(content=question)]})
        final_answer = result["messages"][-1].content
        
        # Tool Call Log Tracing
        for msg in result["messages"]:
            if getattr(msg, "tool_calls", None):
                for tcall in msg.tool_calls:
                    trace_calls.append({
                        "module": "Agent",
                        "function": f"Call_Tool_{tcall.get('name')}",
                        "arguments": tcall.get("args"),
                        "result": "요청중"
                    })
            elif msg.type == "tool":
                snippet = str(msg.content)
                if len(snippet) > 80: snippet = snippet[:80] + "..."
                trace_calls.append({
                    "module": "Tool Response",
                    "function": msg.name,
                    "arguments": {},
                    "result": snippet
                })
        
        trace_calls.append({"module": "Agent", "function": "End", "arguments": {}, "result": "최종 답변 완료"})
        return {"answer": final_answer, "trace_logs": trace_calls}
    except Exception as e:
        trace_calls.append({"module": "Agent", "function": "Error", "arguments": {"error": str(e)}, "result": "오류"})
        return {"answer": f"시스템 오류 발생: {str(e)}", "trace_logs": trace_calls}
