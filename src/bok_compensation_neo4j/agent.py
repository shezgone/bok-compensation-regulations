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
- (JobGrade)-[:HAS_DIFFERENTIAL_AMOUNT {eval_grade: string}]->(DifferentialAmount) // The property eval_grade holds the exact grade name ('EX', etc.)

Example Cypher for '단일 조회 — 연봉제 본봉 산정' (Finding Base Salary after applying differential amount for 3급 JobGrade and EX EvaluationGrade given a base of 60000000. DO NOT DO MATH IN CYPHER, RETURN RAW VALUES AND DO THE MATH IN YOUR OUTPUT):
MATCH (g:JobGrade {name: '3급'})-[:HAS_DIFFERENTIAL_AMOUNT {eval_grade: 'EX'}]->(d:DifferentialAmount)
RETURN d.amount as DifferentialAmount

Example Cypher for '다중 관계 조인 — 직책급·차등액·상한액' (Finding Duty Allowance for '팀장', Differential Amount, and Salary Limit for a 3급 EX grade employee):
MATCH (g:JobGrade {name: '3급'})
MATCH (g)-[:HAS_DUTY_ALLOWANCE]->(da:DutyAllowance {duty: '팀장'})
MATCH (g)-[:HAS_DIFFERENTIAL_AMOUNT {eval_grade: 'EX'}]->(diff:DifferentialAmount)
MATCH (g)-[:HAS_SALARY_LIMIT]->(lim:SalaryLimit)
RETURN da.amount as DutyAllowance, diff.amount as DifferentialAmount, lim.amount as SalaryLimit

Example Cypher for '범위 필터 — 차등액 >= 200만원' (Listing all Job Grade and Evaluation Grade combinations where differential amount >= 2000000):
MATCH (g:JobGrade)-[r:HAS_DIFFERENTIAL_AMOUNT]->(d:DifferentialAmount)
WHERE d.amount >= 2000000
RETURN g.name as JobGrade, r.eval_grade as EvaluationGrade, d.amount as Amount
ORDER BY JobGrade ASC, d.amount DESC

Instructions:
1. Always use the `execute_cypher` tool to fetch exact values before returning an answer. 
2. Ensure you understand exactly what the user is asking and write the correct Cypher logic to match. Do not guess schema.
3. Your responses should format numbers cleanly (e.g. 63,024,000원) and explicitly mention steps.
4. For single calculations, calculate it thoroughly (e.g. base + differential amount).
"""

# Define the Tool function
@tool
def execute_cypher(query: str) -> str:
    """Executes a Cypher query against the Neo4j HR rules graph and returns the result."""
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        with driver.session() as session:
            result = session.run(query)
            records = [dict(record) for record in result]
            driver.close()
            
            if not records:
                return "Query executed successfully but returned no results."
            return json.dumps(records, ensure_ascii=False)
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
    agent_executor = build_neo4j_agent()
    response = agent_executor.invoke({"messages": [HumanMessage(content=question)]})
    return response["messages"][-1].content

if __name__ == "__main__":
    test_question = "3급 팀장이며 성과평가 EX 등급인 직원의 직책급, 연봉차등액, 연봉상한액을 모두 조회하시오."
    print(f"Question: {test_question}")
    answer = run_query(test_question)
    print(f"Answer: {answer}")
