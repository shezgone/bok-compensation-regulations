import sys
from src.bok_compensation_neo4j.agent import run_query

try:
    q = "과장 직급을 가진 직원이 이번 평가에서 3100점을 받았습니다. 연봉 인상액은 얼마인가요?"
    ans = run_query(q)
    with open("result.txt", "w") as f:
        f.write(ans)
    print("DONE! Wrote to result.txt")
except Exception as e:
    with open("result_err.txt", "w") as f:
        import traceback
        f.write(traceback.format_exc())
    print("FAILED! Wrote to result_err.txt")
