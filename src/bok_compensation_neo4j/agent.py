import os
import json
import logging
from typing import TypedDict, Annotated, Sequence
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from neo4j import GraphDatabase

from src.bok_compensation_neo4j.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Schema definition to instruct the LLM
NEO4J_SCHEMA_INFO = """
You have access to a Neo4j Graph Database that contains Bank of Korea compensation and HR rules.
The graph has the following nodes and relationships:

Nodes:
- JobGrade {name: string}  // Example: '1급', '2급', '3급', '4급'
- EvaluationGrade {name: string}  // Example: 'EX', 'EE', 'EI', 'MU'
- SalaryLimit {amount: integer}
- DutyAllowance {amount: integer, duty: string}  // Duty is the literal title, e.g., '팀장'
- DifferentialAmount {amount: integer}

Relationships:
- (JobGrade)-[:HAS_SALARY_LIMIT]->(SalaryLimit)
- (JobGrade)-[:HAS_DUTY_ALLOWANCE]->(DutyAllowance)     // Filter DutyAllowance by duty property
- (EvaluationGrade)-[:HAS_DIFFERENTIAL_AMOUNT {for_grade: string}]->(DifferentialAmount) // The property for_grade holds the exact job grade name ('3급', etc.)

Example Cypher for '단일 조회 — 연봉제 본봉 산정' (Finding Base Salary after applying differential amount for 3급 JobGrade and EX EvaluationGrade given a base of 60000000. DO NOT DO MATH IN CYPHER, RETURN RAW VALUES AND DO THE MATH IN YOUR OUTPUT):
MATCH (e:EvaluationGrade {name: 'EX'})-[:HAS_DIFFERENTIAL_AMOUNT {for_grade: '3급'}]->(d:DifferentialAmount)
RETURN d.amount as DifferentialAmount

Example Cypher for '다중 관계 조인 — 직책급·차등액·상한액' (Finding Duty Allowance for '팀장', Differential Amount, and Salary Limit for a 3급 EX grade employee):
MATCH (g:JobGrade {name: '3급'})
MATCH (g)-[:HAS_DUTY_ALLOWANCE]->(da:DutyAllowance {duty: '팀장'})
MATCH (g)-[:HAS_SALARY_LIMIT]->(lim:SalaryLimit)
MATCH (e:EvaluationGrade {name: 'EX'})-[:HAS_DIFFERENTIAL_AMOUNT {for_grade: '3급'}]->(diff:DifferentialAmount)
RETURN da.amount as DutyAllowance, diff.amount as DifferentialAmount, lim.amount as SalaryLimit

Example Cypher for '범위 필터 — 차등액 >= 200만원' (Listing all Job Grade and Evaluation Grade combinations where differential amount >= 2000000):
MATCH (e:EvaluationGrade)-[r:HAS_DIFFERENTIAL_AMOUNT]->(d:DifferentialAmount)
WHERE d.amount >= 2000000
RETURN r.for_grade as JobGrade, e.name as EvaluationGrade, d.amount as Amount
ORDER BY JobGrade ASC, d.amount DESC

Instructions:
1. Always use the `execute_cypher` tool to fetch exact values before returning an answer. 
2. Ensure you understand exactly what the user is asking and write the correct Cypher logic to match. Do not guess schema.
3. Your responses should format numbers cleanly (e.g. 63,024,000원) and explicitly mention steps.
4. For single calculations, calculate it thoroughly (e.g. base + differential amount).
5. IMPORTANT: You MUST output your final answer and all intermediate thoughts in native Korean (한국어).
6. To use a tool, you must output ONLY a valid JSON block like:
```json
{"name": "execute_cypher", "arguments": {"query": "..."}}
```
Do not add natural language before or after the JSON block when calling a tool.

"""

# Define the Tool function
@tool
def execute_cypher(query: str) -> str:
    """Executes a Cypher query against the Neo4j HR rules graph and returns the result."""
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        
        def serialize_record(record):
            res = {}
            for k, v in record.items():
                if hasattr(v, "labels") and hasattr(v, "items"): # Node
                    res[k] = {"labels": list(v.labels), "properties": dict(v.items())}
                elif hasattr(v, "type") and hasattr(v, "items"): # Relationship
                    res[k] = {"type": v.type, "properties": dict(v.items())}
                else:
                    res[k] = v
            return res

        with driver.session() as session:
            result = session.run(query)
            records = [serialize_record(record) for record in result]
            driver.close()
            
            if not records:
                return "Query executed successfully but returned no results."
            return json.dumps(records, ensure_ascii=False, default=str)
    except Exception as e:
        return f"Error executing Cypher query: {str(e)}"

from src.bok_compensation_typedb.llm import create_chat_model

# Setup Agent
llm = create_chat_model(temperature=0)

def build_neo4j_agent():
    tools = [execute_cypher]
    agent_executor = create_react_agent(
        llm, 
        tools, 
        prompt=NEO4J_SCHEMA_INFO
    )
    return agent_executor

def run_query(question: str):
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
    from src.bok_compensation_typedb.llm import create_chat_model
    
    llm = create_chat_model(temperature=0)
    messages = [
        SystemMessage(content=NEO4J_SCHEMA_INFO),
        HumanMessage(content=question)
    ]
    
    trace_calls = []
    trace_calls.append({
        "module": "Graph RAG",
        "function": "ReAct_Loop_Start",
        "arguments": {"question": question},
        "result": "검색 루프 시작"
    })
    
    for step in range(1, 10):
        try:
            response = llm.invoke(messages)
        except Exception as e:
            trace_calls.append({
                "module": "Agent",
                "function": "LLM_Invoke",
                "arguments": {"step": step},
                "result": f"에러 발생: {e}"
            })
            return {"answer": "LLM 호출 중 에러가 발생했습니다.", "trace_logs": trace_calls}
            
        messages.append(response)
        content_str = response.content.strip()
        
        parsed = None
        try:
            import json
            import re
            
            json_str = content_str
            match_md = re.search(r"```(?:json)?\s*(.*?)(?:```|$)", content_str, re.DOTALL)
            if match_md:
                json_str = match_md.group(1).strip()
            else:
                json_str = content_str.strip()
                
            if not json_str.startswith('{'):
                start_idx = content_str.find('{')
                end_idx = content_str.rfind('}')
                if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
                    json_str = content_str[start_idx:end_idx+1]
                    
            parsed = json.loads(json_str)
        except Exception:
            pass
            
        if isinstance(parsed, dict) and "name" in parsed and parsed.get("name") == "execute_cypher":
            query = parsed.get("arguments", {}).get("query", "")
            
            trace_calls.append({
                "module": "Agent",
                "function": "Action_Generated",
                "arguments": {"step": step, "target_tool": "execute_cypher"},
                "result": query
            })
            
            tool_result = execute_cypher.invoke({"query": query})
            
            if "Error" in tool_result or "returned no results" in tool_result:
                result_summary = tool_result
            else:
                result_summary = "조회 성공"
                
            trace_calls.append({
                "module": "DB",
                "function": "execute_cypher",
                "arguments": {"step": step},
                "result": result_summary
            })
            
            obs_content = f"Observation (데이터베이스 조회 결과):\n{tool_result}\n\n위 결과를 바탕으로 질문에 대한 최종 답변을 한국어로 작성하거나, 결과가 없거나 부족하다면 다른 조건으로 쿼리 작업을 재시도하세요."
            messages.append(AIMessage(content=content_str))
            messages.append(HumanMessage(content=obs_content))
            continue
            
        # JSON 포맷의 Action이 아니면 최종 답변으로 간주
        if isinstance(parsed, dict) and "name" in parsed and parsed.get("name") == "execute_cypher":
            continue

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
    return {"answer": "데이터를 찾기 위한 탐색 횟수를 초과하여 최종 답변을 생성하지 못했습니다.", "trace_logs": trace_calls}
