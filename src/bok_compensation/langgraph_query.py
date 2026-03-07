import json
import os
import sys
from typing import TypedDict, List, Annotated, Dict, Any
import operator

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END, START

from typedb.driver import TransactionType
from bok_compensation.config import TypeDBConfig
from bok_compensation.connection import get_driver

# ====== 1. 환경 설정 ======
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:14b-instruct")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

llm_json = ChatOllama(
    model=MODEL_NAME,
    base_url=OLLAMA_URL,
    temperature=0.0,
    format="json"  
)
llm_text = ChatOllama(
    model=MODEL_NAME,
    base_url=OLLAMA_URL,
    temperature=0.0
)

# ====== TypeDB 유틸리티 ======
try:
    SCHEMA_PATH = os.path.join(
        os.path.dirname(__file__), os.pardir, os.pardir,
        "schema", "compensation_regulation.tql"
    )
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        SCHEMA_TEXT = f.read()
except Exception:
    SCHEMA_TEXT = "TypeDB Schema"

def fetch_rules() -> str:
    """TypeDB에서 조문 정보를 가져옵니다."""
    config = TypeDBConfig()
    try:
        driver = get_driver(config)
    except Exception as e:
        print(f"Error connecting to TypeDB: {e}")
        return ""
        
    try:
        tx = driver.transaction(config.database, TransactionType.READ)
        result = tx.query("""
            match
                $article isa 조문, has 조번호 $id, has 조문내용 $text;
            sort $id;
        """).resolve()
        rules = []
        for row in result:
            rule_id = row.get("id").get_integer()
            rule_text = row.get("text").get_value()
            rules.append(f"Rule {rule_id}: {rule_text}")
        return "\n".join(rules)
    except Exception as e:
        print(f"Error fetching rules: {e}")
        return ""
    finally:
        tx.close()
        driver.close()

def execute_typeql(query: str, variables: list) -> list:
    """TypeDB에서 쿼리를 실행합니다."""
    config = TypeDBConfig()
    driver = get_driver(config)
    rows = []
    try:
        tx = driver.transaction(config.database, TransactionType.READ)
        result = tx.query(query).resolve()
        
        for row in result:
            record = {}
            for var in variables:
                name = var["name"]
                vtype = var.get("type", "string")
                concept = row.get(name)
                if concept is None:
                    record[name] = None
                    continue
                if vtype == "integer":
                    record[name] = concept.get_integer()
                elif vtype == "double":
                    record[name] = concept.get_double()
                elif vtype == "datetime":
                    raw = concept.get_value()
                    record[name] = str(raw)[:10] if raw else None
                else:
                    record[name] = concept.get_value()
            rows.append(record)
    except Exception as e:
        raise e
    finally:
        tx.close()
        driver.close()
    return rows

# ====== 2. 상태 (State) 정의 ======
class AgentState(TypedDict):
    query: str
    semantic_queries: List[str]
    data_queries: List[str]
    semantic_results: Annotated[List[str], operator.add]
    data_results: Annotated[List[str], operator.add]
    final_answer: str

# ====== 3. 에이전트 노드 구현 ======

def planner_node(state: AgentState):
    """
    [Agent 1: Planner]
    사용자 질문을 분석하여 조문 해석(Semantic)과 데이터/금액 조회(Data) 쿼리로 나눕니다.
    """
    print("\n[Planner Agent] 질문 의도 분석 및 하위 쿼리 계획 수립 중...")
    prompt = f"""당신은 분석 에이전트입니다. 
질문을 규정 해석(semantic_queries)과 금액/수치 조회(data_queries)로 분리하세요.

[예시]
질문: "기한부 고용계약자가 상여금을 받을 수 있는지 조문에서 찾고, 1급 보직자의 직책급 월액은 얼마인지 계산해줘."
출력:
{{
  "semantic_queries": ["기한부 고용계약자가 상여금을 받을 수 있는가?"],
  "data_queries": ["1급 보직자의 직책급 월액은 얼마인가?"]
}}

사용자 질문: "{state['query']}"
"""
    response = llm_json.invoke([HumanMessage(content=prompt)])
    try:
        plan = json.loads(response.content)
    except Exception as e:
        print(f"JSON Parsing Error: {e}")
        plan = {"semantic_queries": [], "data_queries": [state["query"]]}
    
    sq = plan.get("semantic_queries", [])
    dq = plan.get("data_queries", [])
    print(f"  -> 계획 수립 완료:\n     * Semantic 질문: {sq}\n     * Data 질문: {dq}")
    return {"semantic_queries": sq, "data_queries": dq}

def semantic_agent_node(state: AgentState):
    """
    [Agent 2: Semantic Agent]
    조문 파악 질문에 대해 TypeDB에서 조회한 규정을 읽고 답합니다.
    """
    queries = state.get("semantic_queries", [])
    if not queries:
        return {"semantic_results": []}
    
    print(f"\n[Semantic Agent] 조문 데이터 검색 및 독해 중... (대기 쿼리: {len(queries)}건)")
    rules = fetch_rules()
    
    results = []
    for q in queries:
        prompt = f"""다음 한국은행 보수규정 조문을 읽고 질문에 명확히 답하세요.

[보수규정 조문 내용]
{rules}

질문: {q}
답변:"""
        res = llm_text.invoke([HumanMessage(content=prompt)])
        results.append(f"Q: {q}\nA: {res.content}")
        print(f"  -> Semantic 답변 완료: '{q}'")
    
    return {"semantic_results": results}

def data_agent_node(state: AgentState):
    """
    [Agent 3: Data Agent]
    데이터 조회가 필요한 질문에 대해 TypeQL을 생성하고 TypeDB에서 실행합니다.
    """
    queries = state.get("data_queries", [])
    if not queries:
        return {"data_results": []}
    
    print(f"\n[Data Agent] TypeDB TypeQL 쿼리 생성 및 실행 중... (대기 쿼리: {len(queries)}건)")
    results = []
    
    for q in queries:
        prompt = f"""당신은 TypeDB 3.x TypeQL READ 쿼리 전문가입니다. 
사용자의 한국어 질문을 TypeDB 3.x TypeQL READ 쿼리로 변환합니다.

## 규칙
1. match 절만 사용하세요 (insert/delete 절대 불가).
2. 스키마에 정의된 엔티티, 관계, 속성만 사용하세요.
3. 문자열 비교 시 {{ $var == "값"; }} 패턴을 사용하세요.
4. 결과에 필요한 속성을 반드시 변수로 바인딩하세요.
5. 응답은 반드시 아래 JSON 형식으로만 반환하세요.
6. **절대 금지**: TypeQL match 절 안에서 산술 연산, 집계함수(reduce, count, sum)를 지원하지 않으므로 사용하지 마세요. 비교가 필요하면 두 변수를 각각 조회만 하세요.

## DB에 존재하는 실제 데이터 값 (참고)
- 직급코드: "1급", "2급", "3급", "4급", "5급" 등
- 직위명: "부서장(가)", "국소속실장", "부장", "팀장", "조사역" 등
- 평가등급: "EX", "EE", "ME", "BE", "정기"

## 응답 JSON 형식
{{
  "typeql": "match $x isa 직위, has 직위명 '1급'; ... ;",
  "variables": [
    {{"name": "조회할_바인딩변수명_달러기호($)제외", "type": "integer" 혹은 "double" 혹은 "string"}}
  ]
}}

[예시]
질문: "부서장(가) 1급 직책급은 얼마야?"
{{
  "typeql": "match $grade isa 직급, has 직급코드 '1급'; $pos isa 직위, has 직위명 $posname; {{ $posname == '부서장(가)'; }}; (적용기준: $std, 해당직급: $grade, 해당직위: $pos) isa 직책급결정; $std has 직책급액 $ppay;",
  "variables": [{{"name": "ppay", "type": "double"}}]
}}

[Schema의 일부]
{SCHEMA_TEXT[:5000]}

질문: {q}
"""
        try:
            res = llm_json.invoke([HumanMessage(content=prompt)])
            parsed = json.loads(res.content)
            typeql = parsed.get("typeql", "")
            variables = parsed.get("variables", [])
            print(f"  -> 생성된 TypeQL:\n{typeql}")
            
            for v in variables:
                v["name"] = v["name"].replace("$", "")
                
            db_rows = execute_typeql(typeql, variables)
            results.append(f"Q: {q}\nDB 조회 결과: {json.dumps(db_rows, ensure_ascii=False)}")
            print(f"  -> Data 조회 완료: DB 결과 {len(db_rows)}건 리턴")
        except Exception as e:
            err_msg = f"Q: {q}\n조회 실패: TypeQL 생성/실행 에러 ({str(e)})"
            results.append(err_msg)
            print(f"  -> 에러: {e}")

    return {"data_results": results}

def summary_agent_node(state: AgentState):
    """
    [Agent 4: Summary Agent]
    에이전트 2,3의 답변을 취합합니다.
    """
    print("\n[Summary Agent] 합산 및 최종 답변 생성 중...")
    
    semantic_info = "\n\n".join(state.get("semantic_results", []))
    data_info = "\n\n".join(state.get("data_results", []))
    
    prompt = f"""당신은 한국은행 보수규정에 대해 완벽하게 답변하는 AI 어시스턴트입니다.
사용자의 원래 질문에 대해 각 하위 에이전트들이 도출한 분석결과를 참고하여, 
자연스럽고 완벽하게 연결된 하나의 통합된 최종 답변을 작성하세요.

사용자의 원래 질문: "{state['query']}"

[참고할 조문 분석결과 (Semantic Agent)]
{semantic_info if semantic_info else '(필요하지 않음)'}

[참고할 직책/수치 분석결과 (Data Agent)]
{data_info if data_info else '(필요하지 않음)'}

최종 답변:"""
    
    res = llm_text.invoke([HumanMessage(content=prompt)])
    print("  -> 결과 요약 완료!")
    return {"final_answer": res.content}

# ====== 4. LangGraph 그래프 구성 ======
def create_langgraph():
    workflow = StateGraph(AgentState)
    workflow.add_node("planner_agent", planner_node)
    workflow.add_node("semantic_agent", semantic_agent_node)
    workflow.add_node("data_agent", data_agent_node)
    workflow.add_node("summary_agent", summary_agent_node)

    workflow.add_edge(START, "planner_agent")
    workflow.add_edge("planner_agent", "semantic_agent")
    workflow.add_edge("planner_agent", "data_agent")
    workflow.add_edge("semantic_agent", "summary_agent")
    workflow.add_edge("data_agent", "summary_agent")
    workflow.add_edge("summary_agent", END)

    return workflow.compile()

# ====== 5. 실행 엔트리포인트 ======
def run_langgraph(query: str):
    app = create_langgraph()
    
    print("=" * 70)
    print(f"🚀 [LangGraph TypeDB Multi-Agent 시작]\n질의: {query}")
    print("=" * 70)
    
    final_state = app.invoke({
        "query": query, 
        "semantic_queries": [], 
        "data_queries": [], 
        "semantic_results": [], 
        "data_results": []
    })
    
    print("\n" + "=" * 70)
    print("✅ [최종 응답 (Summary Agent)]")
    print("=" * 70)
    print(final_state["final_answer"])
    print("=" * 70)

if __name__ == "__main__":
    test_query = "기한부 고용계약자가 상여금을 받을 수 있는지 조문에서 찾고, 1급 보직자의 직책급 월액은 얼마인지 계산해줘."
    if len(sys.argv) > 1:
        test_query = " ".join(sys.argv[1:])
    run_langgraph(test_query)
