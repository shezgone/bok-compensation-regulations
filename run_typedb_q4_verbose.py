from src.bok_compensation_typedb.agent import run_query
q = "평가고과가 7000점인 G3 팀장의 연봉은?"
res = run_query(q)
for t in res.get("trace_logs", []):
    if t["module"] == "Tool Response":
        print(f"Tool {t['function']} returned:\n", t['result'])
print("\nFinal:", res.get("answer"))
