import os
from langchain_core.messages import HumanMessage
from src.bok_compensation.llm import create_chat_model
from src.bok_compensation.nl_query import run as typedb_run
from src.bok_compensation_neo4j.nl_query import run as neo4j_run
from src.bok_compensation_context.context_query import answer_with_context

# ============================================================
# 테스트 질문 정의
# ============================================================
QUESTIONS = [
    {
        "id": "Q1",
        "label": "단일 테이블 조회 (연봉차등액 1건 → 산정)",
        "question": """3급 G3 종합기획직원 A가 다음 조건을 모두 충족할 때, 2025년 5월 1일 기준으로 적용되는 연봉제 본봉을 산정하시오.
조건:
1. 2024년 12월 31일 기준 직전 연봉제 본봉: 60,000,000원
2. 2024년도 성과평가 등급: 'EX'
""",
        "answer": "63,024,000원 (= 60,000,000 + 3,024,000)",
    },
    {
        "id": "Q2",
        "label": "다중 관계 조인 (직책급 + 차등액 + 상한액 3-way)",
        "question": "3급 팀장이며 성과평가 EX 등급인 직원의 직책급, 연봉차등액, 연봉상한액을 모두 조회하시오.",
        "answer": "직책급 1,956,000원, 차등액 3,024,000원, 상한액 77,724,000원",
    },
    {
        "id": "Q3",
        "label": "범위 필터 (차등액 ≥ 200만원 전체 나열)",
        "question": "연봉차등액이 200만원 이상인 직급과 평가등급 조합을 모두 나열하시오.",
        "answer": "1급 EX(3,672,000), 1급 EE(2,448,000), 2급 EX(3,348,000), 2급 EE(2,232,000), 3급 EX(3,024,000), 3급 EE(2,016,000) — 총 6건",
    },
]


def run_base_llm(question: str) -> str:
    os.environ["OPENAI_BASE_URL"] = "http://127.0.0.1:9999/v1"
    os.environ["OPENAI_MODEL"] = os.getenv("BASE_LLM_MODEL", "your-model-name")
    model = create_chat_model(temperature=0.0)
    response = model.invoke([HumanMessage(content=question)])
    return response.content


ARCHITECTURES = [
    ("🏛️  Base LLM", run_base_llm),
    ("🕸️  Neo4j Graph RAG", neo4j_run),
    ("🚀  TypeDB KG RAG", typedb_run),
    ("📄  Context RAG", lambda q: answer_with_context(q)[0]),
]


if __name__ == "__main__":
    for q_info in QUESTIONS:
        print("=" * 60)
        print(f"📋 [{q_info['id']}] {q_info['label']}")
        print(f"   질문: {q_info['question'].strip()}")
        print(f"   정답: {q_info['answer']}")
        print("=" * 60)

        for arch_name, arch_fn in ARCHITECTURES:
            print(f"\n{arch_name}")
            print("-" * 40)
            try:
                result = arch_fn(q_info["question"])
                print(result)
            except Exception as e:
                print(f"Error: {e}")

        print("\n")

