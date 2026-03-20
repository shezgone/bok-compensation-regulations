from src.bok_compensation_typedb.agent import run_query

def test(q):
    print(f"\n--- Question: {q} ---")
    res = run_query(q)
    print("Answer:", res.get("answer"))
    for t in res.get("trace_logs", []):
        if t["module"] == "Agent" and t["function"] == "Call_Tool_execute_typeql":
            print("TypeQL Executed:\n", t["arguments"].get("query"))
            print("Result:\n", t["result"])
            
test("3급 G3 종합기획직원 A가 다음 조건을 모두 충족할 때, 2025년 5월 1일 기준으로 적용되는 연봉제 본봉을 산정하시오.\n조건:\n1. 2024년 12월 31일 기준 직전 연봉제 본봉: 60,000,000원\n2. 2024년도 성과평가 등급: 'EX'")
