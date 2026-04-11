"""7가지 예시 질문 테스트 — Context RAG 백엔드."""

import sys
import os
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from dotenv import load_dotenv
load_dotenv()

from bok_compensation_context.context_query import run_with_trace

TESTS = [
    {
        "id": "Q1",
        "question": "G5 직원의 초봉은?",
        "expected": "종합기획직원 5급의 초임호봉은 11호봉이며, 5급 11호봉 본봉은 1,554,000원",
    },
    {
        "id": "Q2",
        "question": "팀장 3급 직책급은?",
        "expected": "팀장 직위의 3급 연간 직책급액은 1,956,000원",
    },
    {
        "id": "Q3",
        "question": "미국 주재 2급 직원의 국외본봉은?",
        "expected": "미국 주재 2급 직원의 월 국외본봉은 9,760 USD",
    },
    {
        "id": "Q4",
        "question": "현재 연봉제 본봉이 70,000,000원이고 3급 EE이면 조정 후 연봉제 본봉은?",
        "expected": "72,016,000원 (= 70,000,000 + 차등액 2,016,000)",
    },
    {
        "id": "Q5",
        "question": "현재 연봉제 본봉이 77,000,000원인 3급 직원이 EE등급이면 상한을 넘는가?",
        "expected": "77,000,000 + 2,016,000 = 79,016,000원으로, 3급 상한액 77,724,000원을 초과",
    },
    {
        "id": "Q6",
        "question": "기한부 고용계약자는 상여금을 받을 수 있어?",
        "expected": "받을 수 없다. 제14조에 따라 제2장 보수 및 제3장 상여금 규정을 적용하지 않는다",
    },
    {
        "id": "Q7",
        "question": "임금피크제 적용 대상과 연차별 지급률은?",
        "expected": "잔여근무기간 3년 이하 직원 대상. 1년차 0.9, 2년차 0.8, 3년차 0.7",
    },
]

if __name__ == "__main__":
    print("=" * 70)
    print("Context RAG 테스트 — 7가지 예시 질문")
    print("=" * 70)

    for test in TESTS:
        print(f"\n{'─' * 70}")
        print(f"[{test['id']}] {test['question']}")
        print(f"  기대: {test['expected']}")

        start = time.time()
        try:
            result = run_with_trace(test["question"])
            elapsed = time.time() - start
            answer = result.get("answer", "")
            print(f"  응답: {answer}")
            print(f"  시간: {elapsed:.1f}s")
        except Exception as e:
            elapsed = time.time() - start
            print(f"  오류: {e}")
            print(f"  시간: {elapsed:.1f}s")

    print(f"\n{'=' * 70}")
    print("테스트 완료")
