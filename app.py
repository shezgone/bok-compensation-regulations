"""한국은행 보수규정 Graph RAG 데모 — Streamlit 앱."""

import os
import sys
import time
import traceback
import json
import re
from textwrap import dedent
from typing import List, Optional, Tuple

import streamlit as st
from dotenv import load_dotenv
load_dotenv()


# src 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))


# ---------------------------------------------------------------------------
# 페이지 설정
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="보수규정 Graph RAG 데모",
    page_icon="🏛️",
    layout="wide",
)

st.title("🏛️ 한국은행 보수규정 — 4-Way 아키텍처 비교 데모")
st.caption("TypeDB KG RAG · Neo4j Graph RAG · Context RAG · Base LLM")

if "question_input" not in st.session_state:
    st.session_state["question_input"] = ""

# ---------------------------------------------------------------------------
# 아키텍처별 실행 함수 (lazy import — 연결 실패 시 graceful)
# ---------------------------------------------------------------------------

def _run_typedb(question: str) -> str:
    from bok_compensation.nl_query import run_with_trace as typedb_run_with_trace

    return typedb_run_with_trace(question)


def _run_neo4j(question: str) -> str:
    from bok_compensation_neo4j.nl_query import run_with_trace as neo4j_run_with_trace

    return neo4j_run_with_trace(question)


def _run_context_rag(question: str) -> str:
    from bok_compensation_context.context_query import run_with_trace as context_run_with_trace

    return context_run_with_trace(question)


def _run_base_llm(question: str) -> str:
    from langchain_core.messages import HumanMessage
    from bok_compensation.llm import create_chat_model

    model = create_chat_model(temperature=0.0)
    response = model.invoke([HumanMessage(content=question)])
    return {
        "answer": response.content,
        "trace": {
            "question": question,
            "mode": "direct_llm",
        },
    }


def _format_simple_value(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, bool):
        return "예" if value else "아니오"
    if value is None:
        return "없음"
    return str(value)


def _split_graph_sections(graph_context: str) -> dict:
    sections = {}
    for block in (graph_context or "").split("\n\n"):
        block = block.strip()
        if not block:
            continue
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        title = lines[0].rstrip(":")
        sections[title] = lines[1:]
    return sections


def _plan_name_to_section_prefix(name: str) -> str:
    mapping = {
        "호봉 조회": "호봉",
        "초임호봉 조회": "초임호봉",
        "연봉차등 조회": "연봉차등",
        "연봉상한 조회": "연봉상한",
        "직책급 조회": "직책급",
        "상여금 조회": "상여금",
        "국외본봉 조회": "국외본봉",
        "임금피크제 조회": "임금피크제",
        "집행간부 본봉 조회": "집행간부 본봉",
        "부칙 오버라이드 조회": "부칙",
    }
    return mapping.get(name, name)


def _find_section_lines(graph_context: str, plan_name: str) -> list:
    prefix = _plan_name_to_section_prefix(plan_name)
    sections = _split_graph_sections(graph_context)
    for title, lines in sections.items():
        if title.startswith(prefix):
            return lines
    return []


def _backend_descriptor(trace: dict) -> dict:
    query_language = trace.get("query_language")
    if query_language == "TypeQL":
        return {
            "label": "TypeDB KG RAG",
            "runner": "bok_compensation.nl_query.run_with_trace(question)",
            "module": "src/bok_compensation/nl_query.py",
            "graph_fetcher": "fetch_subgraph_typedb(entities, question)",
            "rules_fetcher": "fetch_relevant_rules(question, entities)",
        }
    if query_language == "Cypher":
        return {
            "label": "Neo4j Graph RAG",
            "runner": "bok_compensation_neo4j.nl_query.run_with_trace(question)",
            "module": "src/bok_compensation_neo4j/nl_query.py",
            "graph_fetcher": "fetch_subgraph_neo4j(entities, question)",
            "rules_fetcher": "fetch_relevant_rules(question, entities)",
        }
    return {
        "label": trace.get("mode") or "Unknown",
        "runner": "unknown",
        "module": "unknown",
        "graph_fetcher": "unknown",
        "rules_fetcher": "unknown",
    }


def _build_graph_query(query_language: str, plan_item: dict, trace: dict) -> str:
    name = plan_item.get("name") or ""
    targets = plan_item.get("targets") or {}
    entities = trace.get("entities") or {}
    question = trace.get("question") or ""
    grade = targets.get("grade") or entities.get("grade")
    position = targets.get("position") or entities.get("position")
    eval_grade = targets.get("eval") or entities.get("eval")
    country = targets.get("country") or entities.get("country")
    track = targets.get("track") or entities.get("track")

    if query_language == "TypeQL":
        templates = {
            "호봉 조회": f'''
match
    $g isa 직급, has 직급코드 "{grade}";
    (소속직급: $g, 구성호봉: $h) isa 호봉체계구성;
    $h has 호봉번호 $n, has 호봉금액 $amt;
sort $n;
''',
            "초임호봉 조회": f'''
match
    $s isa 직렬, has 직렬명 "{track}";
    (대상직렬: $s, 적용기준: $std) isa 초임호봉결정;
    $std has 초임호봉번호 $n, has 초임호봉기준설명 $desc;
''',
            "연봉차등 조회": (
                f'''
match
    $g isa 직급, has 직급코드 "{grade}";
    $ev isa 평가결과, has 평가등급 "{eval_grade}";
    (적용기준: $d, 해당직급: $g, 해당등급: $ev) isa 연봉차등;
    $d has 차등액 $diff, has 연봉차등액코드 $code;
    $code contains "ADIFF";
'''
                if grade and eval_grade else
                '''
match
    $g isa 직급, has 직급코드 $grade;
    $ev isa 평가결과, has 평가등급 $eval;
    (적용기준: $d, 해당직급: $g, 해당등급: $ev) isa 연봉차등;
    $d has 차등액 $diff, has 연봉차등액코드 $code;
    $code contains "ADIFF";
sort $diff desc;
'''
            ),
            "연봉상한 조회": f'''
match
    $g isa 직급, has 직급코드 "{grade}";
    (적용기준: $cap, 해당직급: $g) isa 연봉상한;
    $cap has 연봉상한액 $cap_amt, has 연봉상한액코드 $code;
''',
            "직책급 조회": f'''
match
    $g isa 직급, has 직급코드 "{grade}";
    $pos isa 직위, has 직위명 $posname;
    {{ $posname == "{position}"; }};
    (적용기준: $pp, 해당직급: $g, 해당직위: $pos) isa 직책급결정;
    $pp has 직책급액 $amount, has 직책급코드 $code;
''',
            "상여금 조회": f'''
match
    $pos isa 직위, has 직위명 $posname;
    {{ $posname == "{position}"; }};
    $ev isa 평가결과, has 평가등급 "{eval_grade}";
    (적용기준: $bonus, 해당직책구분: $pos, 해당등급: $ev) isa 상여금결정;
    $bonus has 상여금지급률 $rate, has 상여금코드 $code;
''',
            "국외본봉 조회": f'''
match
    $g isa 직급, has 직급코드 "{grade}";
    (적용기준: $os, 해당직급: $g) isa 국외본봉결정;
    $os has 국가명 "{country}", has 국외기본급액 $amt, has 통화단위 $cur;
''',
            "임금피크제 조회": '''
match
    $w isa 임금피크제기준,
        has 적용연차 $year,
        has 임금피크지급률 $rate,
        has 임금피크제설명 $desc;
sort $year;
''',
            "집행간부 본봉 조회": f'''
match
    $b isa 보수기준,
        has 보수기준명 $name,
        has 보수기준명 "{position} 본봉",
        has 보수기본급액 $amount,
        has 보수기준설명 $desc;
''',
        }
        if name == "부칙 오버라이드 조회":
            return dedent(
                """
                여러 개의 3-hop TypeQL 조회를 순차 실행합니다.
                예: 부칙 -> 규정_대체 -> 조문/연봉차등액기준/연봉상한액기준/직책급기준/상여금기준
                실제 구현 함수: _fetch_override_sections_typedb(entities)
                """
            ).strip()
        return dedent(templates.get(name, "")).strip()

    templates = {
        "호봉 조회": f"MATCH (g:직급 {{직급코드: '{grade}'}})-[:호봉체계구성]->(h:호봉) RETURN h.호봉번호 AS n, h.호봉금액 AS amt ORDER BY n",
        "초임호봉 조회": f"MATCH (s:초임호봉기준)-[:대상직렬]->(:직렬 {{직렬명: '{track}'}}) RETURN s.초임호봉번호 AS n, s.설명 AS desc",
        "연봉차등 조회": (
            f"MATCH (d:연봉차등액기준)-[:해당직급]->(:직급 {{직급코드: '{grade}'}}) MATCH (d)-[:해당등급]->(:평가결과 {{평가등급: '{eval_grade}'}}) RETURN d.차등액 AS diff, d.연봉차등액코드 AS code"
            if grade and eval_grade else
            "MATCH (d:연봉차등액기준)-[:해당직급]->(g:직급) MATCH (d)-[:해당등급]->(e:평가결과) RETURN g.직급코드 AS grade, e.평가등급 AS eval, d.차등액 AS diff, d.연봉차등액코드 AS code ORDER BY diff DESC"
        ),
        "연봉상한 조회": f"MATCH (c:연봉상한액기준)-[:해당직급]->(:직급 {{직급코드: '{grade}'}}) RETURN c.연봉상한액 AS cap_amt, c.연봉상한액코드 AS code",
        "직책급 조회": f"MATCH (p:직책급기준)-[:해당직위]->(:직위 {{직위명: '{position}'}}) MATCH (p)-[:해당직급]->(:직급 {{직급코드: '{grade}'}}) RETURN p.직책급액 AS amount, p.직책급코드 AS code",
        "상여금 조회": f"MATCH (b:상여금기준)-[:해당직책구분]->(:직위 {{직위명: '{position}'}}) MATCH (b)-[:해당등급]->(:평가결과 {{평가등급: '{eval_grade}'}}) RETURN b.상여금지급률 AS rate, b.상여금코드 AS code",
        "국외본봉 조회": f"MATCH (o:국외본봉기준 {{국가명: '{country}'}})-[:해당직급]->(:직급 {{직급코드: '{grade}'}}) RETURN o.국외기본급액 AS amt, o.통화단위 AS cur",
        "임금피크제 조회": "MATCH (w:임금피크제기준) RETURN w.적용연차 AS year, w.임금피크지급률 AS rate, w.설명 AS desc ORDER BY year",
        "집행간부 본봉 조회": f"MATCH (b:보수기준) WHERE b.보수기준명 IN ['{position} 본봉'] RETURN b.보수기준명 AS name, b.보수기본급액 AS amount, b.설명 AS desc",
    }
    if name == "부칙 오버라이드 조회":
        return dedent(
            """
            여러 개의 Cypher 조회를 순차 실행합니다.
            예: MATCH (b:부칙)-[r:규정_대체]->(...)
            실제 구현 함수: _fetch_override_sections_neo4j(entities)
            """
        ).strip()
    return templates.get(name, "")


def _build_followup_questions(trace: dict) -> list:
    entities = trace.get("entities") or {}
    validation = trace.get("validation") or {}
    issues = " ".join(validation.get("issues") or [])
    grade = entities.get("grade")
    position = entities.get("position")
    step_no = entities.get("step_no")
    suggestions = []

    if step_no is not None and grade is None:
        suggestions.append(f"3급 {step_no}호봉의 본봉은?")
        if position:
            suggestions.append(f"3급 {step_no}호봉 {position}의 연봉은?")
            suggestions.append(f"4급 {step_no}호봉 {position}의 연봉은?")
        else:
            suggestions.append(f"4급 {step_no}호봉의 본봉은?")

    if grade in {"1급", "2급", "G1", "G2"}:
        suggestions.append(f"현재 연봉제본봉이 60,000,000원인 {grade} EX 직원의 연봉은?")
        suggestions.append(f"2025년 기준 {grade} EX의 연봉차등액은 얼마인가?")

    if position and "직책은 직급에 따라 직책급이 달라" in issues:
        suggestions.append(f"3급 {position}의 직책급은 얼마인가?")

    deduped = []
    seen = set()
    for suggestion in suggestions:
        if suggestion not in seen:
            seen.add(suggestion)
            deduped.append(suggestion)
    return deduped[:3]


def _render_followup_questions(trace: dict) -> None:
    suggestions = _build_followup_questions(trace)
    if not suggestions:
        return
    st.caption("보정 질문 예시")
    for suggestion in suggestions:
        st.write(f"- {suggestion}")


def _collect_shared_followup_questions(results: dict) -> list:
    merged = []
    seen = set()
    for result in results.values():
        trace = result.get("trace") or {}
        for suggestion in _build_followup_questions(trace):
            if suggestion not in seen:
                seen.add(suggestion)
                merged.append(suggestion)
    return merged


def _build_validation_summary(trace: dict) -> Optional[str]:
    validation = trace.get("validation") or {}
    issues = validation.get("issues") or []
    entities = trace.get("entities") or {}
    grade = entities.get("grade")
    position = entities.get("position")
    step_no = entities.get("step_no")

    if step_no is not None and grade is None:
        if position:
            return "호봉과 직책만으로는 계산할 수 없어 직급을 먼저 지정해야 합니다."
        return "호봉만으로는 계산할 수 없어 직급을 먼저 지정해야 합니다."

    if step_no is not None and grade in {"1급", "2급", "G1", "G2"}:
        return "연봉제 대상 직급은 호봉표가 아니라 연봉제본봉 기준으로 계산해야 합니다."

    if issues:
        return issues[0]
    return None


def _extract_missing_inputs(trace: dict) -> List[str]:
    validation = trace.get("validation") or {}
    issues = " ".join(validation.get("issues") or [])
    entities = trace.get("entities") or {}
    grade = entities.get("grade")
    step_no = entities.get("step_no")
    missing = []

    if step_no is not None and grade is None:
        missing.append("직급")

    if step_no is not None and grade in {"1급", "2급", "G1", "G2"}:
        missing.append("직전 또는 현재 연봉제본봉")

    if "평가등급" in issues and entities.get("eval") is None:
        missing.append("평가등급")

    deduped = []
    seen = set()
    for item in missing:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def _collect_shared_validation_signals(results: dict) -> Tuple[List[str], List[str]]:
    summaries = []
    missing_inputs = []
    seen_summaries = set()
    seen_missing = set()

    for result in results.values():
        trace = result.get("trace") or {}
        summary = _build_validation_summary(trace)
        if summary and summary not in seen_summaries:
            seen_summaries.add(summary)
            summaries.append(summary)

        for item in _extract_missing_inputs(trace):
            if item not in seen_missing:
                seen_missing.add(item)
                missing_inputs.append(item)

    return summaries, missing_inputs


def _render_missing_input_tags(items: List[str]) -> None:
    if not items:
        return
    html = " ".join(
        f"<span style='display:inline-block;margin:0 8px 8px 0;padding:0.28rem 0.7rem;border-radius:999px;background:#eef2ff;color:#1e3a8a;border:1px solid #c7d2fe;font-size:0.92rem;font-weight:600;'>{item}</span>"
        for item in items
    )
    st.markdown(html, unsafe_allow_html=True)


def _extract_reference_labels(trace: dict) -> List[str]:
    references: List[str] = []
    seen = set()

    def add_reference(label: str) -> None:
        if label not in seen:
            seen.add(label)
            references.append(label)

    rules_context = trace.get("rules_context") or ""
    for match in re.findall(r"부칙 제\s*(\d+)조", rules_context):
        add_reference(f"부칙 제{match}조")
    for match in re.findall(r"(?<!부칙 )제\s*(\d+)조", rules_context):
        add_reference(f"제{match}조")

    deterministic = trace.get("deterministic_execution") or {}
    values = deterministic.get("values") or {}
    articles = values.get("articles") or []
    for article_no in articles:
        add_reference(f"제{article_no}조")

    article_no = (trace.get("entities") or {}).get("article_no")
    if article_no is not None:
        add_reference(f"제{article_no}조")

    return references[:6]


def _build_process_lines(trace: dict) -> List[str]:
    validation = trace.get("validation") or {}
    if validation:
        issues = validation.get("issues") or []
        lines = ["질문 검증 단계에서 계산 가능 여부를 먼저 확인했습니다."]
        if issues:
            lines.append(issues[0])
        return lines

    deterministic = trace.get("deterministic_execution") or {}
    steps = deterministic.get("steps") or []
    if steps:
        return steps[:4]

    graph_plan = ((trace.get("retrieval_plan") or {}).get("graph") or [])
    executed_items = [item for item in graph_plan if item.get("executed")]
    lines = []
    for item in executed_items[:4]:
        name = item.get("name") or "조회"
        reason = item.get("reason") or ""
        row_count = item.get("row_count")
        suffix = f" 결과 {_format_simple_value(row_count)}건" if row_count is not None else ""
        lines.append(f"{name}를 실행했습니다.{suffix} {reason}".strip())
    return lines


def _render_result_card_summary(trace: dict) -> None:
    references = _extract_reference_labels(trace)
    process_lines = _build_process_lines(trace)

    if references:
        st.caption("참조 번호")
        st.write(" · ".join(references))

    if process_lines:
        st.caption("처리 과정 요약")
        for line in process_lines:
            st.write(f"- {line}")


def _render_flow_overview(trace: dict) -> None:
    backend = _backend_descriptor(trace)
    deterministic = trace.get("deterministic_execution")
    st.markdown("**실행 흐름 요약**")
    lines = [
        f"1. Streamlit 앱 app.py 가 `{backend['runner']}` 를 호출합니다.",
        "2. `extract_entities(question)` 가 질문에서 직급, 직위, 평가등급, 토픽을 뽑습니다.",
        "3. `validate_question(question, entities)` 가 질문이 너무 모호한지 먼저 검사합니다.",
        f"4. `{backend['rules_fetcher']}` 가 관련 조문 텍스트를 모읍니다.",
        f"5. `{backend['graph_fetcher']}` 가 그래프 조회 계획을 세우고 실제 쿼리를 실행합니다.",
        "6. `try_execute_regulation(...)` 과 `try_execute(...)` 가 LLM 없이 바로 계산 가능한지 확인합니다.",
        "7. 결정적 실행이 가능하면 그 결과를 바로 답으로 사용하고, 아니면 `generate_answer(...)` 가 수집된 컨텍스트로 최종 문장을 만듭니다.",
    ]
    if deterministic:
        lines.append(f"8. 이번 질문은 결정적 실행 경로(`{deterministic.get('kind') or 'unknown'}`)로 답을 만들었습니다.")
    else:
        lines.append("8. 이번 질문은 결정적 실행으로 끝나지 않아 LLM 생성 단계까지 진행했습니다.")
    for line in lines:
        st.write(line)
    st.caption(f"실행 모듈: {backend['module']}")


def _render_rules_plan(trace: dict) -> None:
    retrieval_plan = trace.get("retrieval_plan") or {}
    rules_plan = retrieval_plan.get("rules") or {}
    rules_context = trace.get("rules_context") or ""
    st.markdown("**1단계. 규정 검색 함수가 세운 계획**")
    st.write(f"- 함수: fetch_relevant_rules(question, entities)")
    st.write(f"- 모드: {rules_plan.get('mode', 'unknown')}")
    st.write(f"- 직접 조문 조회 여부: {'예' if rules_plan.get('article_direct_lookup') else '아니오'}")
    st.write(f"- 토픽: {', '.join(rules_plan.get('topics') or []) or '없음'}")
    st.write(f"- 검색 키워드: {rules_plan.get('keyword') or '없음'}")
    with st.expander("규정 검색 결과 보기"):
        st.code(rules_context or "없음", language="text")


def _render_graph_plan(trace: dict) -> None:
    retrieval_plan = trace.get("retrieval_plan") or {}
    graph_plan = retrieval_plan.get("graph") or []
    graph_context = trace.get("graph_context") or ""
    query_language = trace.get("query_language") or "text"
    backend = _backend_descriptor(trace)

    st.markdown("**2단계. 그래프 조회 함수가 세운 계획과 실제 쿼리**")
    st.write(f"- 함수: {backend['graph_fetcher']}")
    if not graph_plan:
        st.write("- 그래프 조회 계획이 없습니다.")
        return

    for index, item in enumerate(graph_plan, start=1):
        name = item.get("name") or f"조회 {index}"
        executed = bool(item.get("executed"))
        title = f"{index}. {name} {'실행' if executed else '생략'}"
        with st.expander(title, expanded=executed):
            st.write(f"- 이유: {item.get('reason') or '없음'}")
            targets = item.get("targets") or {}
            if targets:
                st.write("- 조회 대상")
                for key, value in targets.items():
                    st.write(f"  - {key}: {_format_simple_value(value)}")
            row_count = item.get("row_count")
            if row_count is not None:
                st.write(f"- 반환 행 수: {row_count}")
            if executed:
                query_text = _build_graph_query(query_language, item, trace)
                st.markdown("**실행 함수 안에서 사용된 쿼리**")
                st.code(query_text or "구성된 쿼리를 복원하지 못했습니다.", language=query_language.lower())
                section_lines = _find_section_lines(graph_context, name)
                st.markdown("**DB가 돌려준 결과**")
                if section_lines:
                    st.code("\n".join(section_lines), language="text")
                else:
                    st.code("결과 섹션을 찾지 못했습니다. 아래 원본 그래프 컨텍스트를 참고하세요.", language="text")


def _render_answer_construction(trace: dict) -> None:
    deterministic = trace.get("deterministic_execution")
    st.markdown("**3단계. 수집된 결과를 바탕으로 답을 만드는 과정**")
    st.write("- 함수 후보 1: try_execute_regulation(question, entities)")
    st.write("- 함수 후보 2: try_execute(question, entities, provider)")
    st.write("- 함수 후보 3: generate_answer(question, entities, rules_context, graph_context)")
    if deterministic is not None:
        st.success("이번 질문은 결정적 실행으로 끝났습니다. 즉, LLM이 문장을 새로 지어낸 것이 아니라 조회된 값으로 바로 답을 만들었습니다.")
        st.write(f"- 결정적 실행 종류: {deterministic.get('kind') or 'unknown'}")
        steps = deterministic.get("steps") or []
        if steps:
            st.markdown("**순차 처리 단계**")
            for idx, step in enumerate(steps, start=1):
                st.write(f"{idx}. {step}")
        values = deterministic.get("values")
        if values:
            st.markdown("**최종 답 생성에 사용한 값**")
            st.code(json.dumps(values, ensure_ascii=False, indent=2), language="json")
    else:
        st.warning("이번 질문은 결정적 실행으로 닫히지 않아 generate_answer(...) 단계에서 규정 컨텍스트와 그래프 컨텍스트를 조합해 최종 답변을 만들었습니다.")


def _render_trace(trace: dict) -> None:
    query_language = trace.get("query_language")
    if query_language is not None:
        st.markdown("**조회 언어**")
        st.write(query_language)

    validation = trace.get("validation")
    if validation is not None:
        st.markdown("**질문 검증**")
        st.code(validation.get("message") or "", language="text")

    entities = trace.get("entities")
    if entities is not None:
        st.markdown("**추출 엔티티**")
        st.code(json.dumps(entities, ensure_ascii=False, indent=2), language="json")

    if query_language in {"TypeQL", "Cypher"}:
        st.divider()
        _render_flow_overview(trace)
        st.divider()
        _render_rules_plan(trace)
        st.divider()
        _render_graph_plan(trace)
        st.divider()
        _render_answer_construction(trace)

    retrieval_plan = trace.get("retrieval_plan")
    if retrieval_plan is not None:
        st.markdown("**원본 조회 계획**")
        rules_plan = retrieval_plan.get("rules")
        graph_plan = retrieval_plan.get("graph") or []
        if rules_plan is not None:
            st.markdown("**원본 규정 검색 계획**")
            st.write(f"- 모드: {rules_plan.get('mode', 'unknown')}")
            st.write(f"- 직접 조문 조회: {'예' if rules_plan.get('article_direct_lookup') else '아니오'}")
            st.write(f"- topics: {', '.join(rules_plan.get('topics') or []) or '없음'}")
            st.write(f"- keyword: {rules_plan.get('keyword') or '없음'}")
        if graph_plan:
            st.markdown("**원본 그래프 조회 계획**")
            header = "| 조회명 | 실행 여부 | 이유 | 대상 | 결과 수 |\n| --- | --- | --- | --- | --- |"
            rows = [header]
            for item in graph_plan:
                name = str(item.get("name") or "")
                executed = "실행" if item.get("executed") else "생략"
                reason = str(item.get("reason") or "").replace("\n", " ").replace("|", "/")
                targets = item.get("targets") or {}
                target_text = ", ".join(f"{key}={value}" for key, value in targets.items()) if targets else "-"
                row_count = item.get("row_count")
                row_count_text = str(row_count) if row_count is not None else "-"
                rows.append(f"| {name} | {executed} | {reason} | {target_text} | {row_count_text} |")
            st.markdown("\n".join(rows))
        elif rules_plan is None:
            st.write("없음")

    selected_sections = trace.get("selected_sections")
    if selected_sections is not None:
        st.markdown("**선택 섹션**")
        st.write(", ".join(selected_sections) if selected_sections else "없음")

    section_count = trace.get("section_count")
    if section_count is not None:
        st.caption(f"선택 섹션 수: {section_count}")

    rules_context = trace.get("rules_context")
    if rules_context is not None:
        st.markdown("**규정 컨텍스트**")
        st.code(rules_context or "없음", language="text")

    graph_context = trace.get("graph_context")
    if graph_context is not None:
        st.markdown("**원본 그래프 컨텍스트**")
        st.code(graph_context or "없음", language="text")

    context_excerpt = trace.get("context_excerpt")
    if context_excerpt is not None:
        st.markdown("**문서 컨텍스트**")
        st.code(context_excerpt or "없음", language="markdown")

    deterministic_execution = trace.get("deterministic_execution")
    if deterministic_execution is not None:
        st.markdown("**결정적 실행**")
        st.write(f"- 종류: {deterministic_execution.get('kind') or 'unknown'}")
        steps = deterministic_execution.get("steps") or []
        if steps:
            for step in steps:
                st.write(f"- {step}")
        values = deterministic_execution.get("values")
        if values:
            st.code(json.dumps(values, ensure_ascii=False, indent=2), language="json")

    mode = trace.get("mode")
    if mode is not None:
        st.markdown("**실행 모드**")
        st.write(mode)


ARCHITECTURES = {
    "TypeDB KG RAG": {"fn": _run_typedb, "icon": "🚀", "color": "#2196F3"},
    "Neo4j Graph RAG": {"fn": _run_neo4j, "icon": "🕸️", "color": "#4CAF50"},
    "Context RAG": {"fn": _run_context_rag, "icon": "📄", "color": "#FF9800"},
    "Base LLM": {"fn": _run_base_llm, "icon": "🏛️", "color": "#9C27B0"},
}


def _clear_question_input() -> None:
    st.session_state["question_input"] = ""

# ---------------------------------------------------------------------------
# 예시 질문
# ---------------------------------------------------------------------------
EXAMPLE_QUESTIONS = [
    {
        "id": "Q1",
        "label": "단일 조회 — 연봉제 본봉 산정",
        "question": (
            "3급 G3 종합기획직원 A가 다음 조건을 모두 충족할 때, "
            "2025년 5월 1일 기준으로 적용되는 연봉제 본봉을 산정하시오.\n"
            "조건:\n"
            "1. 2024년 12월 31일 기준 직전 연봉제 본봉: 60,000,000원\n"
            "2. 2024년도 성과평가 등급: 'EX'"
        ),
        "answer": "63,024,000원 (= 60,000,000 + 3,024,000)",
    },
    {
        "id": "Q2",
        "label": "다중 관계 조인 — 직책급·차등액·상한액",
        "question": "3급 팀장이며 성과평가 EX 등급인 직원의 직책급, 연봉차등액, 연봉상한액을 모두 조회하시오.",
        "answer": "직책급 1,956,000원, 차등액 3,024,000원, 상한액 77,724,000원",
    },
    {
        "id": "Q3",
        "label": "범위 필터 — 차등액 ≥ 200만원",
        "question": "연봉차등액이 200만원 이상인 직급과 평가등급 조합을 모두 나열하시오.",
        "answer": "1급EX(3,672,000), 1급EE(2,448,000), 2급EX(3,348,000), 2급EE(2,232,000), 3급EX(3,024,000), 3급EE(2,016,000) — 6건",
    },
]


# ---------------------------------------------------------------------------
# 사이드바: 아키텍처 선택 & 예시 질문
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 설정")

    st.subheader("아키텍처 선택")
    selected_archs = []
    for arch_name, arch_info in ARCHITECTURES.items():
        if st.checkbox(
            f"{arch_info['icon']} {arch_name}",
            value=(arch_name != "Base LLM"),
            key=f"arch_{arch_name}",
        ):
            selected_archs.append(arch_name)

    st.divider()
    st.subheader("📋 예시 질문")
    for eq in EXAMPLE_QUESTIONS:
        if st.button(f"[{eq['id']}] {eq['label']}", key=eq["id"], use_container_width=True):
            st.session_state["question_input"] = eq["question"]

    st.divider()
    st.caption("한국은행 보수규정 Graph RAG PoC\n\nTypeDB 3.x · Neo4j 5.x · LangChain")


# ---------------------------------------------------------------------------
# 메인 영역: 질문 입력
# ---------------------------------------------------------------------------
question = st.text_area(
    "💬 질문을 입력하세요",
    height=120,
    placeholder="예: 3급 팀장이며 성과평가 EX 등급인 직원의 직책급을 조회하시오.",
    key="question_input",
)

# 예시 질문의 정답 표시: 현재 질문이 예시와 정확히 일치할 때만 노출
expected = next(
    (example["answer"] for example in EXAMPLE_QUESTIONS if example["question"] == question),
    "",
)
if expected:
    st.info(f"📌 **기대 정답:** {expected}")

col_run, col_clear = st.columns([1, 5])
with col_run:
    run_clicked = st.button("🔍 실행", type="primary", use_container_width=True)
with col_clear:
    st.button("🗑️ 초기화", use_container_width=True, on_click=_clear_question_input)




# ---------------------------------------------------------------------------
# 실행 & 결과 표시
# ---------------------------------------------------------------------------
if run_clicked and question.strip():
    if not selected_archs:
        st.warning("왼쪽 사이드바에서 최소 1개 아키텍처를 선택하세요.")
    else:
        results = {}
        progress = st.progress(0, text="실행 준비 중...")

        for idx, arch_name in enumerate(selected_archs):
            arch_info = ARCHITECTURES[arch_name]
            progress.progress(
                (idx) / len(selected_archs),
                text=f"{arch_info['icon']} {arch_name} 실행 중...",
            )

            start = time.time()
            try:
                response = arch_info["fn"](question.strip())
                elapsed = time.time() - start
                results[arch_name] = {
                    "answer": response["answer"],
                    "trace": response.get("trace") or {},
                    "elapsed": elapsed,
                    "error": None,
                }
            except Exception as e:
                elapsed = time.time() - start
                results[arch_name] = {
                    "answer": None,
                    "trace": None,
                    "elapsed": elapsed,
                    "error": f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
                }

        progress.progress(1.0, text="완료!")
        time.sleep(0.3)
        progress.empty()

        st.session_state["results"] = results

# ---------------------------------------------------------------------------
# 결과 렌더링
# ---------------------------------------------------------------------------
if st.session_state.get("results"):
    results = st.session_state["results"]
    shared_validation_summaries, shared_missing_inputs = _collect_shared_validation_signals(results)
    shared_followups = _collect_shared_followup_questions(results)

    st.divider()
    st.subheader("📊 결과 비교")

    # 카드형 레이아웃
    cols = st.columns(len(results))
    for col, (arch_name, result) in zip(cols, results.items()):
        arch_info = ARCHITECTURES[arch_name]
        with col:
            st.markdown(f"### {arch_info['icon']} {arch_name}")
            st.caption(f"⏱️ {result['elapsed']:.1f}초")

            if result["error"]:
                st.error("실행 오류")
                with st.expander("오류 상세"):
                    st.code(result["error"], language="text")
            else:
                st.success("실행 완료")
                st.markdown(result["answer"])
                _render_result_card_summary(result.get("trace") or {})
                with st.expander("Trace"):
                    _render_trace(result.get("trace") or {})

    if shared_validation_summaries or shared_missing_inputs:
        st.divider()
        st.markdown("**공통 계산 안내**")
        for summary in shared_validation_summaries:
            st.info(summary)
        if shared_missing_inputs:
            st.caption("추가로 필요한 입력")
            _render_missing_input_tags(shared_missing_inputs)

    if shared_followups:
        st.divider()
        st.markdown("**공통 보정 질문 예시**")
        st.caption("아래 예시는 특정 백엔드 전용이 아니라 현재 질문을 계산 가능하게 바꾸기 위한 공통 입력 예시입니다.")
        for suggestion in shared_followups:
            st.write(f"- {suggestion}")
