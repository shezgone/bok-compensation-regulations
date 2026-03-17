"""Measure token usage across 4 architectures x 3 questions.

Approach: wrap _invoke_text / _invoke_json at the module level to intercept
LLM responses and extract token_usage from response_metadata.
"""
import json
import sys

sys.path.insert(0, "src")

from langchain_core.messages import HumanMessage
from bok_compensation.llm import create_chat_model

# ── Token accumulator ──
_call_log = []


def _extract_usage(response):
    """Extract token usage from a LangChain AIMessage response."""
    usage = getattr(response, "response_metadata", {}).get("token_usage", {})
    if not usage:
        um = getattr(response, "usage_metadata", None)
        if um:
            usage = {
                "prompt_tokens": getattr(um, "input_tokens", 0),
                "completion_tokens": getattr(um, "output_tokens", 0),
                "total_tokens": getattr(um, "total_tokens", 0),
            }
    return usage or {}


# ── Build wrapped _invoke_text / _invoke_json that track tokens ──
def _make_tracked_invoke_text(original_fn):
    def tracked(prompt):
        model = create_chat_model(temperature=0.0)
        response = model.invoke([HumanMessage(content=prompt)])
        usage = _extract_usage(response)
        if usage:
            _call_log.append(dict(usage))
        return response.content
    return tracked


def _make_tracked_invoke_json(original_fn):
    def tracked(prompt):
        model = create_chat_model(temperature=0.0, json_output=True)
        response = model.invoke([HumanMessage(content=prompt)])
        usage = _extract_usage(response)
        if usage:
            _call_log.append(dict(usage))
        return json.loads(response.content)
    return tracked


# ── Patch at module level ──
import bok_compensation.nl_query as typedb_mod
import bok_compensation_neo4j.nl_query as neo4j_mod
import bok_compensation_context.context_query as context_mod

# TypeDB module
typedb_mod._invoke_text = _make_tracked_invoke_text(typedb_mod._invoke_text)
typedb_mod._invoke_json = _make_tracked_invoke_json(typedb_mod._invoke_json)

# Neo4j module
neo4j_mod._invoke_text = _make_tracked_invoke_text(neo4j_mod._invoke_text)
neo4j_mod._invoke_json = _make_tracked_invoke_json(neo4j_mod._invoke_json)

# Context module: answer_with_context calls create_chat_model directly
# We need to wrap it differently
_orig_answer_with_context = context_mod.answer_with_context

def _tracked_answer_with_context(question):
    prompt, sections = context_mod.build_context_prompt(question)
    model = create_chat_model(temperature=0.0)
    response = model.invoke([HumanMessage(content=prompt)])
    usage = _extract_usage(response)
    if usage:
        _call_log.append(dict(usage))
    return str(response.content), sections

context_mod.answer_with_context = _tracked_answer_with_context


QUESTIONS = [
    {
        "id": "Q1",
        "label": "단일 테이블 조회",
        "question": (
            "3급 G3 종합기획직원 A가 다음 조건을 모두 충족할 때, "
            "2025년 5월 1일 기준으로 적용되는 연봉제 본봉을 산정하시오.\n"
            "조건:\n1. 2024년 12월 31일 기준 직전 연봉제 본봉: 60,000,000원\n"
            "2. 2024년도 성과평가 등급: 'EX'"
        ),
    },
    {
        "id": "Q2",
        "label": "3-way 조인",
        "question": "3급 팀장이며 성과평가 EX 등급인 직원의 직책급, 연봉차등액, 연봉상한액을 모두 조회하시오.",
    },
    {
        "id": "Q3",
        "label": "범위 필터 6건",
        "question": "연봉차등액이 200만원 이상인 직급과 평가등급 조합을 모두 나열하시오.",
    },
]


def run_base_llm(question):
    model = create_chat_model(temperature=0.0)
    response = model.invoke([HumanMessage(content=question)])
    usage = _extract_usage(response)
    return response.content, usage


ARCHITECTURES = [
    ("Base LLM", "base"),
    ("Context RAG", "context"),
    ("Neo4j Graph RAG", "neo4j"),
    ("TypeDB KG RAG", "typedb"),
]

results = {}

for q in QUESTIONS:
    qid = q["id"]
    results[qid] = {}
    question = q["question"]

    for arch_name, arch_key in ARCHITECTURES:
        print(f"[{qid}] {arch_name}...", end=" ", flush=True)
        _call_log.clear()

        try:
            if arch_key == "base":
                answer, usage = run_base_llm(question)
                results[qid][arch_key] = {
                    "calls": 1,
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                }
            elif arch_key == "context":
                answer, _ = context_mod.answer_with_context(question)
                results[qid][arch_key] = {
                    "calls": len(_call_log),
                    "prompt_tokens": sum(c.get("prompt_tokens", 0) for c in _call_log),
                    "completion_tokens": sum(c.get("completion_tokens", 0) for c in _call_log),
                    "total_tokens": sum(c.get("total_tokens", 0) for c in _call_log),
                }
            elif arch_key == "neo4j":
                answer = neo4j_mod.run(question)
                results[qid][arch_key] = {
                    "calls": len(_call_log),
                    "prompt_tokens": sum(c.get("prompt_tokens", 0) for c in _call_log),
                    "completion_tokens": sum(c.get("completion_tokens", 0) for c in _call_log),
                    "total_tokens": sum(c.get("total_tokens", 0) for c in _call_log),
                }
            elif arch_key == "typedb":
                answer = typedb_mod.run(question)
                results[qid][arch_key] = {
                    "calls": len(_call_log),
                    "prompt_tokens": sum(c.get("prompt_tokens", 0) for c in _call_log),
                    "completion_tokens": sum(c.get("completion_tokens", 0) for c in _call_log),
                    "total_tokens": sum(c.get("total_tokens", 0) for c in _call_log),
                }

            r = results[qid][arch_key]
            print(
                f"calls={r['calls']} "
                f"prompt={r['prompt_tokens']} "
                f"completion={r['completion_tokens']} "
                f"total={r['total_tokens']}"
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"ERROR: {e}")
            results[qid][arch_key] = {
                "calls": 0, "prompt_tokens": 0,
                "completion_tokens": 0, "total_tokens": 0,
                "error": str(e),
            }

# ── Summary table ──
print("\n" + "=" * 90)
print(f"{'질문':>10} | {'Base LLM':>12} | {'Context RAG':>12} | {'Neo4j':>12} | {'TypeDB':>12}")
print("-" * 90)

for qid in ["Q1", "Q2", "Q3"]:
    row = []
    for arch_key in ["base", "context", "neo4j", "typedb"]:
        r = results[qid][arch_key]
        calls = r["calls"]
        total = r["total_tokens"]
        prompt = r["prompt_tokens"]
        comp = r["completion_tokens"]
        row.append(f"{total:,} ({calls}c)")
    print(f"  {qid:>8} | {row[0]:>12} | {row[1]:>12} | {row[2]:>12} | {row[3]:>12}")

print("-" * 90)
print(f"  {'합계':>8} |", end="")
for arch_key in ["base", "context", "neo4j", "typedb"]:
    total = sum(results[qid][arch_key]["total_tokens"] for qid in ["Q1", "Q2", "Q3"])
    calls = sum(results[qid][arch_key]["calls"] for qid in ["Q1", "Q2", "Q3"])
    print(f" {total:,} ({calls}c) |", end="")
print()

print("\n상세 (prompt/completion 분리):")
print(f"{'':>10} | {'Base LLM':>20} | {'Context RAG':>20} | {'Neo4j':>20} | {'TypeDB':>20}")
for qid in ["Q1", "Q2", "Q3"]:
    row = []
    for arch_key in ["base", "context", "neo4j", "typedb"]:
        r = results[qid][arch_key]
        row.append(f"{r['prompt_tokens']:,}+{r['completion_tokens']:,}")
    print(f"  {qid:>8} | {row[0]:>20} | {row[1]:>20} | {row[2]:>20} | {row[3]:>20}")

print("\n\nJSON:")
print(json.dumps(results, ensure_ascii=False, indent=2))
