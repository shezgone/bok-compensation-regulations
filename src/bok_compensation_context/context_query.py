"""LLM reasoning path that answers directly from a preprocessed markdown context."""

from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Tuple

from src.bok_compensation_typedb.llm import create_chat_model
from src.bok_compensation_typedb.question_validation import extract_step_no, validate_question


CONTEXT_PATH = Path(__file__).with_name("regulation_context.md")


def _validation_entities(question: str) -> Dict[str, Any]:
    return {
        "grade": next(
            (
                grade
                for grade in ["1급", "2급", "3급", "4급", "5급", "6급", "G1", "G2", "G3", "G4", "G5"]
                if grade in question
            ),
            None,
        ),
        "step_no": extract_step_no(question),
    }


def _trace_preview_text(text: str, max_lines: int = 4) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return ""
    preview = lines[:max_lines]
    if len(lines) > max_lines:
        preview.append("...")
    return "\n".join(preview)


def _extract_usage(response: Any) -> Dict[str, int]:
    usage = getattr(response, "usage_metadata", None) or getattr(response, "response_metadata", {}).get("token_usage") or {}
    return {
        "input": int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0),
        "output": int(usage.get("output_tokens") or usage.get("completion_tokens") or 0),
    }


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


def _compose_extraction_prompt(question: str, selected_sections: List[Dict[str, str]]) -> str:
    selected_text = "\n\n".join(section["content"] for section in selected_sections)
    return f"""당신은 한국은행 보수규정 분석을 위한 '정보 추출기(Extractor)'입니다.
아래 제공된 [전처리 문서 발췌] 내용에서, 사용자의 [질문]에 답변하거나 계산하기 위해 필요한 규정, 예외사항, 직제/직급별 지급 기준액 등의 '사실(Fact)'만을 빠짐없이 요약하고 추출하세요.
여기서는 직접 계산하거나 최종 답변을 내리지 마세요! 오직 필요한 데이터만 짧고 명확한 목록 형태로 나열하세요. (예: "1. 본봉 산정 기준: ~, 2. 파트장 직책급: 350,000원")
같은 정보가 JSON과 마크다운 표에 모두 있으면 JSON을 기준값으로 사용하세요.

[질문]
{question}

[전처리 문서 발췌]
{selected_text}

추출된 사실:"""


def _compose_reasoning_prompt(question: str, extracted_facts: str) -> str:
    return f"""당신은 한국은행 보수규정 질의 응답 보조 모델(계산 및 설명자)입니다.
반드시 아래 제공된 [추출된 사실]만을 근거로 삼아 질문에 최종 답변을 작성하세요. 지식이나 외부 정보를 더하지 마세요.
문서에서 확인되지 않는 내용은 '제공된 전처리 문서에서 확인되지 않습니다.'라고 답하세요.
복합 질문이면 항목별로 나눠 답하세요.
질문이 수식/계산을 요구하면 계산식을 짧고 명확하게 보여주세요. (예 형식: 적용 규칙, 사용한 값, 계산식, 최종 답)
초봉 질문이면 반드시 초임호봉 번호와 해당 호봉의 본봉 금액을 함께 답하세요.
기한부 고용계약자와 상여금 질문이면 결론을 반드시 '받을 수 없다' 또는 '받을 수 있다' 형태로 분명히 쓰세요.
질문에 여러 조건이 있을 때 계산에 직접 사용한 조건과 사용하지 않은 조건을 구분해 간단히 설명하세요.
직책, 직급평점 수치, 기준일이 질문에 포함되어 있어도 문서의 계산 규칙상 직접 계산에 쓰이지 않으면 그 이유를 한 줄로 밝혀야 합니다.
연봉제본봉 조정 질문에서는 직책급이나 상여금을 자동으로 합산하지 마세요.

[질문]
{question}

[추출된 사실]
{extracted_facts}

최종 답변:"""


def _invoke_2step_context_answer(question: str, selected_sections: List[Dict[str, str]]) -> Tuple[str, Dict[str, int], str]:
    try:
        from langchain_core.messages import HumanMessage
    except ImportError:
        return "Error: LangChain core not installed", {"input": 0, "output": 0}, ""

    model = create_chat_model(temperature=0.0)
    
    # 1단계: 추출 (Extraction)
    extraction_prompt = _compose_extraction_prompt(question, selected_sections)
    extraction_response = model.invoke([HumanMessage(content=extraction_prompt)])
    extracted_facts = str(extraction_response.content)
    usage1 = _extract_usage(extraction_response)
    
    # 2단계: 추론/계산 (Reasoning & Calculation)
    reasoning_prompt = _compose_reasoning_prompt(question, extracted_facts)
    reasoning_response = model.invoke([HumanMessage(content=reasoning_prompt)])
    final_answer = str(reasoning_response.content)
    usage2 = _extract_usage(reasoning_response)
    
    total_usage = {
        "input": usage1.get("input", 0) + usage2.get("input", 0),
        "output": usage1.get("output", 0) + usage2.get("output", 0),
    }
    
    return final_answer, total_usage, extracted_facts


def answer_with_context(question: str) -> Tuple[str, List[Dict[str, str]]]:
    validation = validate_question(question, _validation_entities(question))
    if validation is not None:
        return validation["message"], []

    sections = select_relevant_sections(question)
    answer, _, _ = _invoke_2step_context_answer(question, sections)
    return answer, sections


def run_with_trace(question: str) -> Dict[str, object]:
    validation_entities = _validation_entities(question)
    function_calls: List[Dict[str, Any]] = []

    validation = validate_question(question, validation_entities)
    function_calls.append(
        {
            "module": "src/bok_compensation_context/context_query.py",
            "function": "validate_question",
            "arguments": {
                "question": question,
                "entities": validation_entities,
            },
            "result": {
                "is_valid": validation is None,
                "message": None if validation is None else validation.get("message"),
                "issues": [] if validation is None else validation.get("issues") or [],
            },
            "next_inputs": [] if validation is not None else [
                {
                    "function": "select_relevant_sections",
                    "values": {"question": question, "top_k": 8},
                }
            ],
        }
    )

    if validation is not None:
        return {
            "answer": validation["message"],
            "trace": {
                "question": question,
                "validation": validation,
                "function_calls": function_calls,
                "token_usage": {"input": 0, "output": 0},
            },
        }

    sections = select_relevant_sections(question)
    function_calls.append(
        {
            "module": "src/bok_compensation_context/context_query.py",
            "function": "select_relevant_sections",
            "arguments": {"question": question, "top_k": 8},
            "result": {
                "section_count": len(sections),
                "selected_sections": [section["title"] for section in sections],
                "context_preview": _trace_preview_text("\n\n".join(section["content"] for section in sections), max_lines=6),
            },
            "next_inputs": [
                {
                    "function": "_invoke_2step_context_answer",
                    "values": {
                        "question": question,
                        "selected_sections": [section["title"] for section in sections],
                    },
                }
            ],
        }
    )

    answer, token_usage, extracted_facts = _invoke_2step_context_answer(question, sections)
    
    extraction_prompt = _compose_extraction_prompt(question, sections)
    reasoning_prompt = _compose_reasoning_prompt(question, extracted_facts)
    
    function_calls.append(
        {
            "module": "src/bok_compensation_context/context_query.py",
            "function": "_invoke_2step_context_answer",
            "arguments": {
                "question": question,
                "selected_sections": [section["title"] for section in sections],
            },
            "llm_input": {
                "step1_extraction_prompt": extraction_prompt,
                "step2_reasoning_prompt": reasoning_prompt,
            },
            "result": {
                "extracted_facts": extracted_facts,
                "answer": answer,
                "token_usage": token_usage,
            },
            "next_inputs": [],
        }
    )

    return {
        "answer": answer,
        "trace": {
            "question": question,
            "function_calls": function_calls,
            "token_usage": token_usage,
        },
    }


def run(question: str) -> str:
    answer, _ = answer_with_context(question)
    return answer


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]).strip() or "G5 직원의 초봉은?"
    print(run(query))
