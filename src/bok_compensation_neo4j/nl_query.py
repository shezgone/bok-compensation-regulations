"""Graph-first natural-language query entrypoint for Neo4j."""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import Neo4jConfig
from .connection import get_driver
from bok_compensation.llm import create_chat_model
from bok_compensation.question_validation import extract_step_no, validate_question


SOURCE_TEXT_PATH = Path(__file__).resolve().parents[2] / "extracted_pdf.txt"


def _invoke_text(prompt: str) -> str:
    from langchain_core.messages import HumanMessage

    model = create_chat_model(temperature=0.0)
    response = model.invoke([HumanMessage(content=prompt)])
    return response.content


def _invoke_json(prompt: str) -> Dict[str, Any]:
    from langchain_core.messages import HumanMessage

    model = create_chat_model(temperature=0.0, json_output=True)
    response = model.invoke([HumanMessage(content=prompt)])
    return json.loads(response.content)


def _regex_first(question: str, pattern: str) -> Optional[str]:
    match = re.search(pattern, question, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _parse_threshold(question: str) -> Optional[float]:
    amount_match = re.search(r"(\d+)\s*만\s*원", question)
    if amount_match:
        return float(amount_match.group(1)) * 10000.0
    plain_match = re.search(r"(\d{1,3}(?:,\d{3})+|\d+)\s*원", question)
    if plain_match:
        return float(plain_match.group(1).replace(",", ""))
    return None


def _normalize_threshold(value: Any, question: str) -> Optional[float]:
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric * 10000.0 if numeric < 10000 else numeric
    if isinstance(value, str):
        parsed = _parse_threshold(value)
        if parsed is not None:
            return parsed
        stripped = value.replace(",", "").strip()
        if stripped.isdigit():
            numeric = float(stripped)
            return numeric * 10000.0 if numeric < 10000 else numeric
    return _parse_threshold(question)


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _determine_hop_depth(question: str, entities: Dict[str, Any]) -> int:
    topics = set(entities.get("topics") or [])
    override_markers = ("부칙", "대체", "경과조치", "우선 적용", "우선적용", "개정")
    if any(marker in question for marker in override_markers) or "부칙" in topics:
        return 3
    if entities.get("article_no") is not None and topics.issubset({"조문"}):
        return 1
    if not topics and entities.get("article_no") is not None:
        return 1
    return 2


def extract_entities(question: str) -> Dict[str, Any]:
    prompt = f"""당신은 한국은행 보수규정 Graph RAG용 엔티티 추출기입니다.
질문에서 주요 엔티티와 탐색 토픽만 추출하세요.

반드시 아래 JSON 형식으로만 답하세요.
{{
  "grade": "",
  "position": "",
  "eval": "",
  "country": "",
  "track": "",
  "article_no": null,
  "topics": [],
  "keyword": "",
  "amount_threshold": null
}}

질문: {question}
"""
    try:
        entities = _invoke_json(prompt)
    except Exception:
        entities = {}

    grade = entities.get("grade") or _regex_first(question, r"\b([1-6]급|G[1-5])\b")
    eval_grade = entities.get("eval") or _regex_first(question, r"\b(EX|EE|ME|BE|NI)\b")
    article_no = entities.get("article_no")
    if article_no is None:
        article_match = _regex_first(question, r"제\s*(\d+)\s*조")
        article_no = int(article_match) if article_match else None

    topics = list(entities.get("topics") or [])
    detected_position = entities.get("position")
    if not detected_position:
        detected_position = next(
            (
                name
                for name in ["총재", "위원", "부총재", "부총재보", "감사", "팀장", "부장", "반장"]
                if name in question
            ),
            None,
        )
    keyword_map = {
        "연봉차등": ("차등", "차등액", "연봉차등"),
        "연봉상한": ("상한", "연봉상한"),
        "직책급": ("직책급",),
        "상여금": ("상여금", "평가상여금", "정기상여금"),
        "임금피크제": ("임금피크", "피크제", "임금피크제", "기본급지급률"),
        "본봉": ("본봉", "연간 본봉", "기본급"),
        "보수": ("보수",),
        "호봉": ("호봉",),
        "초임호봉": ("초봉", "초임"),
        "국외본봉": ("국외", "해외", "주재"),
        "조문": ("조문", "규정", "부칙", "가능", "대상", "해석"),
        "부칙": ("부칙", "대체", "경과조치"),
    }
    for topic, markers in keyword_map.items():
        if any(marker in question for marker in markers):
            topics.append(topic)

    return {
        "grade": grade,
        "position": detected_position,
        "eval": eval_grade,
        "country": entities.get("country") or next((name for name in ["미국", "독일", "일본", "영국", "홍콩", "중국"] if name in question), None),
        "track": entities.get("track") or ("종합기획직원" if "종합기획" in question or "G" in question else None),
        "step_no": extract_step_no(question),
        "article_no": article_no,
        "topics": _dedupe(topics),
        "keyword": entities.get("keyword") or question,
        "amount_threshold": _normalize_threshold(entities.get("amount_threshold"), question),
    }


def _execute_cypher(cypher: str) -> List[Dict[str, Any]]:
    config = Neo4jConfig()
    driver = get_driver(config)
    try:
        with driver.session(database=config.database) as session:
            return [record.data() for record in session.run(cypher)]
    finally:
        driver.close()


def get_rules_subgraph() -> str:
    rows = _execute_cypher("MATCH (n:조문) RETURN n.조번호 AS id, n.조문내용 AS text ORDER BY id")
    return "\n".join(f"제{row['id']}조: {row['text']}" for row in rows)


def _get_source_rule_snippets(question: str, entities: Dict[str, Any]) -> List[str]:
    try:
        source_text = SOURCE_TEXT_PATH.read_text(encoding="utf-8")
    except OSError:
        return []

    snippets: List[str] = []
    topics = set(entities.get("topics") or [])
    if "임금피크제" in topics or "임금피크" in question or "피크제" in question:
        for pattern in (
            r"제4조\([^\n]*본봉[^\n]*?⑥임금피크제본봉은잔여근무기간이3년이하인직원을대상으로한다\.",
            r"⑥임금피크제본봉은잔여근무기간이3년이하인직원을대상으로한다\."
        ):
            match = re.search(pattern, re.sub(r"\s+", "", source_text))
            if match:
                cleaned = match.group(0)
                cleaned = cleaned.replace("⑥", "제4조 ⑥ ") if cleaned.startswith("⑥") else cleaned
                snippets.append(cleaned)
                break
        if snippets:
            snippets = ["제4조 ⑥ 임금피크제본봉은 잔여근무기간이 3년 이하인 직원을 대상으로 한다."]

    return snippets


def fetch_relevant_rules(question: str, entities: Dict[str, Any], limit: int = 8) -> str:
    all_rules = get_rules_subgraph().splitlines()
    article_no = entities.get("article_no")
    if article_no is not None:
        matched = [line for line in all_rules if line.startswith(f"제{article_no}조:")]
        return "\n".join(matched)

    exec_positions = {"총재", "위원", "부총재", "부총재보", "감사"}
    is_exec_salary_question = entities.get("position") in exec_positions and any(token in question for token in ("본봉", "보수"))

    keywords = [token for token in re.findall(r"[0-9A-Za-z가-힣]+", question) if len(token) >= 2]
    topic_boosts = []
    if "연봉차등" in question or entities.get("amount_threshold") is not None:
        topic_boosts.extend(["연봉제본봉", "차등액", "평가등급"])
    if "연봉상한" in question:
        topic_boosts.extend(["상한액", "연봉제본봉"])
    if "직책급" in question:
        topic_boosts.extend(["직책급"])
    if "상여금" in question:
        topic_boosts.extend(["상여금", "지급률"])
    if "임금피크" in question or "피크제" in question:
        topic_boosts.extend(["임금피크제본봉", "잔여근무기간", "기본급지급률"])
    if "본봉" in question or "보수" in question:
        topic_boosts.extend(["본봉", "별표1", "연간총액"])

    scored: List[tuple[int, str]] = []
    for line in all_rules:
        score = sum(1 for keyword in keywords if keyword in line)
        score += 3 * sum(1 for keyword in topic_boosts if keyword in line)
        if is_exec_salary_question:
            score += 5 * sum(1 for keyword in ("집행간부", "별표1", "연간총액") if keyword in line)
            score -= 3 if "초임호봉" in line else 0
        if score > 0:
            scored.append((score, line))
    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [line for _, line in scored[:limit]]
    for snippet in _get_source_rule_snippets(question, entities):
        if snippet not in selected:
            selected.append(snippet)
    return "\n".join(selected)


def _fetch_override_sections_neo4j(entities: Dict[str, Any]) -> List[str]:
    sections: List[str] = []
    article_no = entities.get("article_no")
    grade = entities.get("grade")
    eval_grade = entities.get("eval")
    threshold = entities.get("amount_threshold")
    topics = set(entities.get("topics") or [])

    if article_no is not None:
        rows = _execute_cypher(
            "\n".join([
                f"MATCH (b:부칙)-[r:규정_대체]->(a:조문 {{조번호: {article_no}}})",
                "RETURN b.부칙조번호 AS buchik_jo, b.부칙내용 AS content, r.대체사유 AS reason, r.우선순위 AS priority",
                "ORDER BY priority ASC",
            ])
        )
        sections.append(_format_section("조문 오버라이드 3-hop", rows))

    if "연봉차등" in topics or threshold is not None:
        filters: List[str] = []
        if grade:
            filters.append(f"g.직급코드 = '{grade}'")
        if eval_grade:
            filters.append(f"e.평가등급 = '{eval_grade}'")
        if threshold is not None:
            filters.append(f"d.차등액 >= {threshold}")
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        rows = _execute_cypher(
            "\n".join([
                "MATCH (b:부칙)-[r:규정_대체]->(d:연봉차등액기준)-[:해당직급]->(g:직급)",
                "MATCH (d)-[:해당등급]->(e:평가결과)",
                where_clause,
                "RETURN b.부칙조번호 AS buchik_jo, r.대체사유 AS reason, r.우선순위 AS priority, g.직급코드 AS grade, e.평가등급 AS eval, d.차등액 AS diff, d.연봉차등액코드 AS code",
                "ORDER BY diff DESC",
            ])
        )
        sections.append(_format_section("부칙 차등액 오버라이드 3-hop", rows))

    return [section for section in sections if section]


def _format_section(title: str, rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return ""
    lines = [f"[{title}]"]
    for row in rows:
        parts = [f"{key}={value}" for key, value in row.items() if value not in (None, "")]
        lines.append("- " + ", ".join(parts))
    return "\n".join(lines)


def fetch_subgraph_neo4j(entities: Dict[str, Any], question: Optional[str] = None) -> str:
    sections: List[str] = []
    hop_depth = int(entities.get("hop_depth") or _determine_hop_depth(question or "", entities))
    topics = set(entities.get("topics") or [])
    grade = entities.get("grade")
    position = entities.get("position")
    eval_grade = entities.get("eval")
    country = entities.get("country")
    track = entities.get("track")

    if grade and "호봉" in topics:
        rows = _execute_cypher(
            f"MATCH (g:직급 {{직급코드: '{grade}'}})-[:호봉체계구성]->(h:호봉) RETURN h.호봉번호 AS n, h.호봉금액 AS amt ORDER BY n"
        )
        sections.append(_format_section(f"호봉 {hop_depth}-hop", rows))

    if track and "초임호봉" in topics:
        rows = _execute_cypher(
            f"MATCH (s:초임호봉기준)-[:대상직렬]->(:직렬 {{직렬명: '{track}'}}) RETURN s.초임호봉번호 AS n, s.설명 AS desc"
        )
        sections.append(_format_section(f"초임호봉 {hop_depth}-hop", rows))

    if ("연봉차등" in topics or entities.get("amount_threshold") is not None) and grade and eval_grade:
        rows = _execute_cypher(
            f"MATCH (d:연봉차등액기준)-[:해당직급]->(:직급 {{직급코드: '{grade}'}}) MATCH (d)-[:해당등급]->(:평가결과 {{평가등급: '{eval_grade}'}}) RETURN d.차등액 AS diff, d.연봉차등액코드 AS code"
        )
        sections.append(_format_section(f"연봉차등 {hop_depth}-hop", rows))
    elif "연봉차등" in topics or entities.get("amount_threshold") is not None:
        rows = _execute_cypher(
            "MATCH (d:연봉차등액기준)-[:해당직급]->(g:직급) MATCH (d)-[:해당등급]->(e:평가결과) RETURN g.직급코드 AS grade, e.평가등급 AS eval, d.차등액 AS diff, d.연봉차등액코드 AS code ORDER BY diff DESC"
        )
        sections.append(_format_section(f"연봉차등 {hop_depth}-hop", rows))

    if "연봉상한" in topics and grade:
        rows = _execute_cypher(
            f"MATCH (c:연봉상한액기준)-[:해당직급]->(:직급 {{직급코드: '{grade}'}}) RETURN c.연봉상한액 AS cap_amt, c.연봉상한액코드 AS code"
        )
        sections.append(_format_section(f"연봉상한 {hop_depth}-hop", rows))

    if "직책급" in topics and grade and position:
        rows = _execute_cypher(
            f"MATCH (p:직책급기준)-[:해당직위]->(:직위 {{직위명: '{position}'}}) MATCH (p)-[:해당직급]->(:직급 {{직급코드: '{grade}'}}) RETURN p.직책급액 AS amount, p.직책급코드 AS code"
        )
        sections.append(_format_section(f"직책급 {hop_depth}-hop", rows))

    if "상여금" in topics and position and eval_grade:
        rows = _execute_cypher(
            f"MATCH (b:상여금기준)-[:해당직책구분]->(:직위 {{직위명: '{position}'}}) MATCH (b)-[:해당등급]->(:평가결과 {{평가등급: '{eval_grade}'}}) RETURN b.상여금지급률 AS rate, b.상여금코드 AS code"
        )
        sections.append(_format_section(f"상여금 {hop_depth}-hop", rows))

    if "국외본봉" in topics and country and grade:
        rows = _execute_cypher(
            f"MATCH (o:국외본봉기준 {{국가명: '{country}'}})-[:해당직급]->(:직급 {{직급코드: '{grade}'}}) RETURN o.국외기본급액 AS amt, o.통화단위 AS cur"
        )
        sections.append(_format_section(f"국외본봉 {hop_depth}-hop", rows))

    if "임금피크제" in topics:
        rows = _execute_cypher(
            "MATCH (w:임금피크제기준) RETURN w.적용연차 AS year, w.임금피크지급률 AS rate, w.설명 AS desc ORDER BY year"
        )
        sections.append(_format_section(f"임금피크제 {hop_depth}-hop", rows))

    if position and ("본봉" in topics or "보수" in topics or "본봉" in (question or "")):
        position_aliases = {
            "총재": ["총재 본봉"],
            "위원": ["위원·부총재 본봉"],
            "부총재": ["위원·부총재 본봉"],
            "감사": ["감사 본봉"],
            "부총재보": ["부총재보 본봉"],
        }
        name_list = position_aliases.get(position, [f"{position} 본봉"])
        quoted_names = ", ".join([f"'{name}'" for name in name_list])
        rows = _execute_cypher(
            "\n".join([
                "MATCH (b:보수기준)",
                f"WHERE b.보수기준명 IN [{quoted_names}]",
                "RETURN b.보수기준명 AS name, b.보수기본급액 AS amount, b.설명 AS desc",
            ])
        )
        sections.append(_format_section(f"집행간부 본봉 {hop_depth}-hop", rows))

    if hop_depth >= 3:
        sections.extend(_fetch_override_sections_neo4j(entities))

    return "\n\n".join(section for section in sections if section)


def generate_answer(question: str, entities: Dict[str, Any], rules_context: str, graph_context: str) -> str:
    prompt = f"""당신은 한국은행 보수규정 Graph RAG 답변 모델입니다.
반드시 아래의 서브쿼리 결과만 근거로 추론하세요.

규칙:
1. 주요 엔티티와 규정, adaptive 1~3-hop 그래프 조회 결과를 함께 보고 답하세요.
2. 질문이 비교/필터를 요구하면 후보 행을 하나씩 끝까지 검토하세요.
3. 숫자는 서브쿼리 결과에 있는 값만 사용하세요.
4. 값이 없으면 추정하지 말고 조회 결과가 없다고 말하세요.
5. 부칙 또는 대체 규정이 보이면 본문보다 우선 적용 여부를 먼저 판단하세요.
6. 답변은 너무 짧게 끝내지 말고, 필요하면 근거 규정과 조회된 엔티티를 짧게 설명하세요.

[질문]
{question}

[추출된 주요 엔티티]
{json.dumps(entities, ensure_ascii=False)}

[관련 규정 서브쿼리 결과]
{rules_context or '없음'}

[Adaptive hop 그래프 서브쿼리 결과]
{graph_context or '없음'}

최종 답변:
"""
    return _invoke_text(prompt)


def run_with_trace(question: str) -> Dict[str, Any]:
    entities = extract_entities(question)
    entities["hop_depth"] = _determine_hop_depth(question, entities)
    validation = validate_question(question, entities)
    if validation is not None:
        return {
            "answer": validation["message"],
            "trace": {
                "question": question,
                "query_language": "Cypher",
                "entities": entities,
                "validation": validation,
                "rules_context": "",
                "graph_context": "",
            },
        }

    rules_context = fetch_relevant_rules(question, entities)
    graph_context = fetch_subgraph_neo4j(entities, question)
    answer = generate_answer(question, entities, rules_context, graph_context)
    return {
        "answer": answer,
        "trace": {
            "question": question,
            "query_language": "Cypher",
            "entities": entities,
            "rules_context": rules_context,
            "graph_context": graph_context,
        },
    }


def run(question: str) -> str:
    return run_with_trace(question)["answer"]


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]).strip() or "일반사무직원의 초봉은?"
    print(run(query))