"""LLM reasoning path that answers directly from a preprocessed markdown context."""

from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Dict, List, Tuple

from bok_compensation.llm import create_chat_model
from bok_compensation.question_validation import extract_step_no, validate_question


CONTEXT_PATH = Path(__file__).with_name("regulation_context.md")


def load_context_document() -> str:
    return CONTEXT_PATH.read_text(encoding="utf-8")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def _tokens(text: str) -> List[str]:
    return re.findall(r"[0-9a-zA-Z가-힣]+", text.lower())


def split_sections(document: str) -> List[Dict[str, str]]:
    sections: List[Dict[str, str]] = []
    current_title = "문서 전체"
    current_lines: List[str] = []

    for line in document.splitlines():
        if line.startswith("## "):
            if current_lines:
                sections.append({"title": current_title, "content": "\n".join(current_lines).strip()})
            current_title = line[3:].strip()
            current_lines = [line]
            continue
        current_lines.append(line)

    if current_lines:
        sections.append({"title": current_title, "content": "\n".join(current_lines).strip()})
    return sections


def select_relevant_sections(question: str, *, top_k: int = 8) -> List[Dict[str, str]]:
    sections = split_sections(load_context_document())
    question_tokens = set(_tokens(question))
    normalized_question = _normalize(question)
    scored: List[Tuple[float, Dict[str, str]]] = []

    for section in sections:
        content = section["content"]
        section_tokens = set(_tokens(content))
        overlap = len(question_tokens & section_tokens)
        score = float(overlap)

        normalized_content = _normalize(content)
        for token in question_tokens:
            if token and token in normalized_content:
                score += min(len(token) / 3.0, 2.0)

        if any(marker in normalized_question for marker in ("초봉", "초임", "호봉")) and "초임호봉" in content:
            score += 4.0
        if any(marker in normalized_question for marker in ("직책급", "팀장", "부장", "반장")) and "직책급표" in content:
            score += 4.0
        if any(marker in normalized_question for marker in ("상여금", "ee", "ex", "me", "be")) and "평가상여금" in content:
            score += 4.0
        if any(marker in normalized_question for marker in ("국외본봉", "주재", "미국", "독일", "일본", "영국", "홍콩", "중국")) and "국외본봉표" in content:
            score += 4.0
        if any(marker in normalized_question for marker in ("연봉차등", "상한", "연봉제")) and "연봉제 관련 표" in content:
            score += 4.0
        if any(marker in normalized_question for marker in ("기한부", "고용계약", "상여금", "개정", "임금피크")) and "주요 조문" in content:
            score += 4.0
        if any(marker in normalized_question for marker in ("연봉제", "본봉", "조정", "차등액", "직급평점", "평가", "기준일")) and "계산 규칙" in content:
            score += 6.0
        if any(marker in normalized_question for marker in ("g3", "g5", "직급평점", "평가등급", "본봉 조정", "국외본봉")) and "용어 정규화" in content:
            score += 4.0
        if any(marker in normalized_question for marker in ("기한부", "반장", "직책", "상한", "기준일", "직급평점")) and "적용 제외 및 주의사항" in content:
            score += 5.0
        if any(marker in normalized_question for marker in ("직급평점", "반장", "기준일", "ee", "연봉제")) and "문서 사용 원칙" in content:
            score += 5.0

        scored.append((score, section))

    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [section for score, section in scored[:top_k] if score > 0]
    return selected or sections[:top_k]


def build_context_prompt(question: str) -> Tuple[str, List[Dict[str, str]]]:
    selected_sections = select_relevant_sections(question)
    selected_text = "\n\n".join(section["content"] for section in selected_sections)
    prompt = f"""당신은 한국은행 보수규정 질의 응답 보조 모델입니다.
반드시 아래에 제공된 전처리 문서 내용만 근거로 답하세요.
문서 밖의 지식은 사용하지 마세요.
숫자와 통화는 문서에 나온 값을 그대로 쓰세요.
질문이 계산을 요구하면 계산식을 짧게 보여주세요.
계산 질문이면 JSON 블록의 구조화 데이터를 우선 사용하세요.
같은 정보가 JSON과 마크다운 표에 모두 있으면 JSON을 기준값으로 사용하고, 마크다운 표는 참고용으로만 사용하세요.
문서에서 확인되지 않는 내용은 '제공된 전처리 문서에서 확인되지 않습니다.'라고 답하세요.
초봉 질문이면 반드시 초임호봉 번호와 해당 호봉의 본봉 금액을 함께 답하세요.
기한부 고용계약자와 상여금 질문이면 결론을 반드시 '받을 수 없다' 또는 '받을 수 있다' 형태로 분명히 쓰세요.
복합 질문이면 항목별로 나눠 답하세요.
계산 질문이면 다음 형식을 최대한 따르세요: 적용 규칙, 사용한 값, 계산식, 최종 답.
질문에 여러 조건이 있을 때 계산에 직접 사용한 조건과 사용하지 않은 조건을 구분해 간단히 설명하세요.
직책, 직급평점 수치, 기준일이 질문에 포함되어 있어도 문서의 계산 규칙상 직접 계산에 쓰이지 않으면 그 이유를 한 줄로 밝혀야 합니다.
연봉제본봉 조정 질문에서는 직책급이나 상여금을 자동으로 합산하지 마세요.

[질문]
{question}

[전처리 문서 발췌]
{selected_text}

답변:"""
    return prompt, selected_sections


def answer_with_context(question: str) -> Tuple[str, List[Dict[str, str]]]:
    validation = validate_question(question, {"grade": next((grade for grade in ["1급", "2급", "3급", "4급", "5급", "6급", "G1", "G2", "G3", "G4", "G5"] if grade in question), None), "step_no": extract_step_no(question)})
    if validation is not None:
        return validation["message"], []

    prompt, sections = build_context_prompt(question)
    try:
        from langchain_core.messages import HumanMessage
    except ImportError:
        return prompt, sections

    model = create_chat_model(temperature=0.0)
    response = model.invoke([HumanMessage(content=prompt)])
    return str(response.content), sections


def run_with_trace(question: str) -> Dict[str, object]:
    validation = validate_question(question, {"grade": next((grade for grade in ["1급", "2급", "3급", "4급", "5급", "6급", "G1", "G2", "G3", "G4", "G5"] if grade in question), None), "step_no": extract_step_no(question)})
    if validation is not None:
        return {
            "answer": validation["message"],
            "trace": {
                "question": question,
                "query_language": "Context-only",
                "validation": validation,
                "selected_sections": [],
                "section_count": 0,
                "context_excerpt": "",
            },
        }

    answer, sections = answer_with_context(question)
    return {
        "answer": answer,
        "trace": {
            "question": question,
            "query_language": "Context-only",
            "selected_sections": [section["title"] for section in sections],
            "section_count": len(sections),
            "context_excerpt": "\n\n".join(section["content"] for section in sections),
        },
    }


def run(question: str) -> str:
    answer, _ = answer_with_context(question)
    return answer


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]).strip() or "G5 직원의 초봉은?"
    print(run(query))
