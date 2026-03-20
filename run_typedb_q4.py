from src.bok_compensation_typedb.agent import run_query
q = "평가고과가 7000점인 G3 팀장의 연봉은?"
print(run_query(q).get("answer"))
