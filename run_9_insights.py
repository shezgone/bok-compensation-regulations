import os
import sys

from src.bok_compensation_neo4j.agent import run_query as neo4j_run
from src.bok_compensation_typedb.agent import run_query as typedb_run
from src.bok_compensation_context.context_query import run_with_trace as context_run

questions = [
    ("하", "보수규정에서 직원의 보수는 어떻게 구성되는가?"),
    ("하", "미국 주재 2급 직원의 국외본봉은 얼마인가?"),
    ("하", "월급 지급일이 휴일인 경우 언제 지급하는가?"),
    ("중", "현재 연봉제 본봉이 70,000,000원인 3급 직원이 EE등급을 받았을 때 연봉차등액과 조정 후 연봉제 본봉은 얼마인가?"),
    ("중", "임금피크제 1년차 직원의 임금피크제본봉 지급기준과 시간외근무수당 지급 기준(시간당 보수의 몇 배인지)은 무엇인가?"),
    ("중", "직위해제 처분일로부터 4개월이 지난 직원의 보수는 본봉의 몇 퍼센트가 지급되는가?"),
    ("상", "3급 직원이 EX등급을 받았을 때, 이 직원이 영국에 주재한다면 받을 국외본봉과 연봉차등액은 각각 얼마인가?"),
    ("상", "기한부 고용계약자의 상여금 지급 여부와, 결근 3일을 했을 때 감액되는 보수 산정 공식을 설명하라."),
    ("상", "1급 직원의 연봉상한액은 얼마인가? 만약 현재 연봉제 본봉이 100,000,000원인 1급 직원이 EX등급을 받았다면 조정 후 연봉제 본봉은 상한액을 초과하는가?")
]

results = {}
runners = {"Context-Only": context_run, "Neo4j-Agent": neo4j_run, "TypeDB-Agent": typedb_run}

with open("insights_9.txt", "w", encoding="utf-8") as f:
    for name, runner in runners.items():
        print(f"--- Running {name} ---")
        f.write(f"\n=====================================\n")
        f.write(f" Backend: {name}\n")
        f.write(f"=====================================\n")
        
        for diff, q in questions:
            print(f"Q: {q}")
            try:
                res = runner(q)
                ans = res.get('answer', str(res)).replace('\n', ' ')
                f.write(f"[{diff}] Q: {q}\n[A] {ans}\n[Status] SUCCESS\n\n")
            except Exception as e:
                f.write(f"[{diff}] Q: {q}\n[A] ERROR: {str(e)}\n[Status] FAILED\n\n")

print("Done. Check insights_9.txt")
