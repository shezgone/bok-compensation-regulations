import os
from langchain_core.messages import HumanMessage
from src.bok_compensation.llm import create_chat_model
from src.bok_compensation.nl_query import run as typedb_run
from src.bok_compensation_neo4j.nl_query import run as neo4j_run

question = """3급 G3 종합기획직원 A가 다음 조건을 모두 충족할 때, 2025년 5월 1일 기준으로 적용되는 연봉제 본봉을 산정하시오.
조건:
1. 2024년 12월 31일 기준 직전 연봉제 본봉: 60,000,000원
2. 2024년도 성과평가 등급: 'EX'
"""

print("==================================================")
print("🧐 [테스트 질문]")
print(question.strip())
print("==================================================\n")

# 1. Base LLM (RAG 없이 직접 질문)
print("🏛️ [아키텍처 1] Base LLM (일반/지능형 질의)")
try:
    # 9999 포트인 우리가 띄운 vLLM 프록시를 쓴다고 해보자
    os.environ["OPENAI_BASE_URL"] = "http://127.0.0.1:9999/v1"
    os.environ["OPENAI_MODEL"] = "/data/models/naver-hyperclovax/HyperCLOVAX-SEED-Think-32B-text-only/llm/HyperCLOVAX-SEED-Think-32B"
    model = create_chat_model(temperature=0.0)
    response = model.invoke([HumanMessage(content=question)])
    print(response.content)
except Exception as e:
    print(f"Error: {e}")

print("\n==================================================\n")

# 2. Neo4j 파이프라인
print("🕸️ [아키텍처 2] Neo4j Graph RAG (Text-to-Cypher)")
try:
    neo_answer = neo4j_run(question)
    print(neo_answer)
except Exception as e:
    print(f"Error: {e}")

print("\n==================================================\n")

# 3. TypeDB 파이프라인
print("🚀 [아키텍처 3] TypeDB Knowledge Graph RAG (Text-to-TypeQL)")
try:
    type_answer = typedb_run(question)
    print(type_answer)
except Exception as e:
    print(f"Error: {e}")

print("\n==================================================")
