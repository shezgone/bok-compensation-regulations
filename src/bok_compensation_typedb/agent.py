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

[TypeQL 규칙 - 3.x 대응 핵심 중요 사항!]
1. TypeDB 3.x에서는 `get $var;`, `return $var;` 등의 키워드를 절대 사용하지 않습니다!! 오로지 `match` 블록 내의 변수 선언만으로 반환합니다.
2. 수치 필터링 시에는 `... has 연봉차등액 $amt; $amt >= 2000000;` 와 같이 세미콜론으로 구분하여 필터링합니다.

<정상 예시 모음>
- 직책급 조회:
  `match $g isa 직급, has 직급명 "3급"; $v isa 직위, has 직위명 "팀장"; $rel (해당직급:$g, 해당직위:$v, 적용기준:$ref) isa 직책급결정; $ref isa 직책급기준, has 직책급액 $amt;`
- 연봉차등액 조회 + 이상 필터:
  `match $g isa 직급, has 직급명 $g_name; $eval isa 평가결과, has 평가등급 $eval_name; $rel (해당직급:$g, 해당등급:$eval, 적용기준:$ref) isa 연봉차등; $ref isa 연봉차등액기준, has 차등액 $amt; $amt >= 2000000;`
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
4. "G5 직원의 초봉" 같이 2단계가 필요한 경우, 먼저 `search_regulations`로 초임호봉을 찾고 `ask_db_expert`로 호봉금액을 가져오세요.
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
            return "Query executed successfully but returned no results."
        return json.dumps(results, ensure_ascii=False)
    except Exception as e:
        logger.error(f"TypeQL Error: {str(e)}\nQuery: {query}")
        return f"Error executing TypeQL query: {str(e)}"

@tool
def ask_db_expert(question: str) -> str:
    """TypeDB 데이터베이스에서 기준표 수치(금액, 한도, 호봉 등)를 조회할 때 하위 에이전트(Qwen)에게 자연어로 질문을 전달합니다."""
    from src.bok_compensation_typedb.llm import create_chat_model
    qwen_llm = create_chat_model(temperature=0)
    qwen_agent = create_react_agent(qwen_llm, [execute_typeql], prompt=QWEN_SCHEMA_PROMPT)
    res = qwen_agent.invoke({"messages": [HumanMessage(content=question)]})
    return res["messages"][-1].content

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
    from langchain_openai import ChatOpenAI
    hcx_llm = ChatOpenAI(
        base_url="http://211.188.81.250:30402/v1",
        model="HCX-GOV-THINK-V1-32B",
        api_key="sk-dummy",
        temperature=0,
        max_tokens=2048,
    )
    tools = [ask_db_expert, search_regulations]
    return create_react_agent(hcx_llm, tools, prompt=HCX_SYSTEM_PROMPT)

def run_query(question: str):
    agent = build_typedb_agent()
    trace_calls = [{"module": "System", "function": "Start", "arguments": {"mode": "LangGraph Hybrid TypeDB (HCX+Qwen MoE)"}, "result": "검색 루프 시작"}]
    
    try:
        result = agent.invoke({"messages": [HumanMessage(content=question)]})
        final_answer = result["messages"][-1].content
        
        for msg in result["messages"]:
            if getattr(msg, "tool_calls", None):
                for tcall in msg.tool_calls:
                    trace_calls.append({
                        "module": "Agent",
                        "function": f"Call_Tool_{tcall.get('name')}",
                        "arguments": tcall.get("args"),
                        "result": "요청중"
                    })
            elif getattr(msg, "type", "") == "tool":
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
