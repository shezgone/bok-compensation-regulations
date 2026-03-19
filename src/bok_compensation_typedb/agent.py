import json
import logging
from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool

from src.bok_compensation_typedb.config import TypeDBConfig
from src.bok_compensation_typedb.connection import get_driver
from typedb.driver import TransactionType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TYPEDB_SCHEMA_INFO = """
You have access to a TypeDB Graph Database that contains Bank of Korea compensation and HR rules.

Below is an overview of the REAL Graph Entities and Relationships (TypeQL):

Entities:
- 직급 (attributes: 직급명 - e.g. '1급', '2급', '3급', '4급')
- 직위 (attributes: 직위명 - e.g. '부서장(가)', '팀장')
- 평가결과 (attributes: 평가등급 - e.g. 'EX', 'EE')
- 직책급기준 (attributes: 직책급액 - number)
- 연봉차등액기준 (attributes: 차등액 - number)
- 연봉상한액기준 (attributes: 연봉상한액 - number)

Key Relationships (Relations):
- 직책급결정 (roles: 해당직위, 해당직급, 적용기준)
   * 해당직위 is played by 직위
   * 해당직급 is played by 직급
   * 적용기준 is played by 직책급기준
- 연봉차등 (roles: 해당등급, 해당직급, 적용기준)
   * 해당등급 is played by 평가결과
   * 해당직급 is played by 직급
   * 적용기준 is played by 연봉차등액기준
- 연봉상한 (roles: 해당직급, 적용기준)
   * 해당직급 is played by 직급
   * 적용기준 is played by 연봉상한액기준

Example TypeQL for '단일 조회 — 연봉제 본봉 산정' (Finding Base Salary after applying differential amount for 3급 JobGrade and EX EvaluationGrade given a base of 60000000. DO NOT DO MATH IN TYPEQL, RETURN RAW VALUES AND DO THE MATH IN YOUR OUTPUT):
match 
$grd isa 직급, has 직급명 "3급"; 
$eval isa 평가결과, has 평가등급 "EX"; 
$rel (해당등급: $eval, 해당직급: $grd, 적용기준: $diff_ref) isa 연봉차등;
$diff_ref isa 연봉차등액기준, has 차등액 $da; 

Example TypeQL for '다중 관계 조인 — 차등액과 상한액':
match 
$grd isa 직급, has 직급명 "3급"; 
$eval isa 평가결과, has 평가등급 "EX"; 
$rel1 (해당직급: $grd, 해당등급: $eval, 적용기준: $diff_ref) isa 연봉차등;
$diff_ref isa 연봉차등액기준, has 차등액 $da;
$rel2 (해당직급: $grd, 적용기준: $cap_ref) isa 연봉상한;
$cap_ref isa 연봉상한액기준, has 연봉상한액 $la;

Instructions:
1. TypeDB 3.x DOES NOT use `get`, `return`, `select`, or `filter` keywords. A `match` statement implicitly returns all variables bound in the query. Do NOT append `get $amt;` or `select $grd;` at the end of your query. JUST END WITH THE LAST SEMICOLON.
2. To filter values (e.g., > 2000000), just add it as a statement in the match block: `$da > 2000000;`. DO NOT use `filter $da > 2000000;`.
3. Use the `execute_typeql` tool to query the database.
4. Provide exact numerical answers and context.
5. Don't do math inside TypeQL, do it in your output.
5. IMPORTANT: You MUST output your final answer and all intermediate thoughts in native Korean (한국어).
6. To use a tool, you must output ONLY a valid JSON block like:
```json
{"name": "execute_typeql", "arguments": {"query": "..."}}
```
Do not add natural language before or after the JSON block when calling a tool.

"""

@tool
def execute_typeql(query: str) -> str:
    """Executes a valid TypeDB 3.x TypeQL query and returns JSON results."""
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

def build_typedb_agent():
    from src.bok_compensation_typedb.llm import create_chat_model
    llm = create_chat_model(temperature=0)
    tools = [execute_typeql]
    return create_react_agent(llm, tools, prompt=TYPEDB_SCHEMA_INFO)

import re
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

def run_query(question: str):
    from src.bok_compensation_typedb.llm import create_chat_model
    llm = create_chat_model(temperature=0)
    
    messages = [
        SystemMessage(content=TYPEDB_SCHEMA_INFO),
        HumanMessage(content=question)
    ]
    
    trace_calls = []
    trace_calls.append({
        "module": "KG RAG",
        "function": "ReAct_Loop_Start",
        "arguments": {"question": question},
        "result": "검색 루프 시작"
    })
    
    for step in range(1, 10):
        response = llm.invoke(messages)
        content_str = response.content
        
        json_match = re.search(r"```(?:json)?\s*(.*?)(?:```|$)", content_str, re.DOTALL)
        if json_match:
            raw_json_text = json_match.group(1).strip()
        else:
            raw_json_text = content_str.strip()
            
        # Fallback to extract from first '{' to last '}' if full parse fails
        if not raw_json_text.startswith('{'):
            start_idx = content_str.find('{')
            end_idx = content_str.rfind('}')
            if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
                raw_json_text = content_str[start_idx:end_idx+1]
        
        try:
            parsed = json.loads(raw_json_text)
            if isinstance(parsed, dict) and "name" in parsed and "arguments" in parsed:
                if parsed["name"] == "execute_typeql":
                    query_arg = parsed["arguments"].get("query", "")
                    
                    trace_calls.append({
                        "module": "Agent",
                        "function": "Action_Generated",
                        "arguments": {"step": step, "target_tool": "execute_typeql"},
                        "result": query_arg
                    })
                    
                    tool_result = execute_typeql.invoke({"query": query_arg})
                    
                    trace_calls.append({
                        "module": "TypeDB",
                        "function": "execute_typeql",
                        "arguments": {"step": step},
                        "result": "조회 성공" if "Error" not in tool_result else tool_result
                    })
                    
                    obs_content = f"Observation (데이터베이스 조회 결과):\n{tool_result}\n\n위 결과를 바탕으로 질문에 대한 최종 답변을 한국어로 작성하세요. 수학적인 계산이 필요하면 이 정보를 활용하고, 아직 정보가 부족하다면 다시 JSON 도구 호출 포맷을 사용해 추가 조회를 수행하세요."
                    messages.append(AIMessage(content=content_str))
                    messages.append(HumanMessage(content=obs_content))
                    continue
        except Exception:
            pass  # Not a valid JSON tool call, treat as final answer
            
        trace_calls.append({
            "module": "Agent",
            "function": "End_Loop",
            "arguments": {"reason": "final_answer_generated", "step": step},
            "result": "최종 답변 도출 완료"
        })
        return {"answer": content_str, "trace_logs": trace_calls}
        
    trace_calls.append({
        "module": "Agent",
        "function": "Timeout",
        "arguments": {"reason": "max_steps"},
        "result": "최대 반복 횟수 초과"
    })
    return {"answer": "최대 반복 횟수 초과. 현재까지의 정보를 바탕으로 답변을 구성하지 못했습니다.", "trace_logs": trace_calls}
