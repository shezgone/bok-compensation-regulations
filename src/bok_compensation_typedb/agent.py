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

Example TypeQL for '단일 조회 — 팀장 직책급':
match 
$pos isa 직위, has 직위명 "팀장"; 
$grd isa 직급, has 직급명 "3급"; 
$rel (해당직위: $pos, 해당직급: $grd, 적용기준: $pay_ref) isa 직책급결정; 
$pay_ref isa 직책급기준, has 직책급액 $amt; 

Example TypeQL for '다중 관계 조인 — 차등액과 상한액':
match 
$grd isa 직급, has 직급명 "3급"; 
$eval isa 평가결과, has 평가등급 "EX"; 
$rel1 (해당직급: $grd, 해당등급: $eval, 적용기준: $diff_ref) isa 연봉차등;
$diff_ref isa 연봉차등액기준, has 차등액 $da;
$rel2 (해당직급: $grd, 적용기준: $cap_ref) isa 연봉상한;
$cap_ref isa 연봉상한액기준, has 연봉상한액 $la;

Instructions:
1. TypeDB 3.x DOES NOT use `get` or `return` keywords. A `match` statement implicitly returns all variables bound in the query. Do NOT append `get $amt;` or `return ...` at the end of your query. JUST END WITH THE LAST SEMICOLON.
2. Use the `execute_typeql` tool to query the database.
3. Provide exact numerical answers and context.
4. Don't do math inside TypeQL, do it in your output.
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

def run_query(question: str):
    agent_executor = build_typedb_agent()
    response = agent_executor.invoke({"messages": [HumanMessage(content=question)]})
    return response["messages"][-1].content
