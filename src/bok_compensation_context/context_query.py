"""LLM reasoning path that answers directly from a preprocessed markdown context."""

from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Tuple

from src.bok_compensation_typedb.llm import create_chat_model
from src.bok_compensation_typedb.question_validation import extract_step_no, validate_question


CONTEXT_PATH = Path(__file__).with_name("regulation_context.md")
RULES_PATH = Path(__file__).with_name("regulation_rules.md")


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


def load_rules_document() -> str:
    return RULES_PATH.read_text(encoding="utf-8")


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


def select_relevant_rules(question: str, *, top_k: int = 3) -> List[Dict[str, str]]:
    """MoE agent의 search_regulations 도구용. 수치 테이블 없는 조문 전용 문서에서 검색."""
    return _score_sections(split_sections(load_rules_document()), question, top_k=top_k)


def _score_sections(sections: List[Dict[str, str]], question: str, *, top_k: int) -> List[Dict[str, str]]:
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
        if any(marker in normalized_question for marker in ("직책급", "팀장", "부장", "반장")) and "직책급" in content:
            score += 4.0
        if any(marker in normalized_question for marker in ("상여금", "ee", "ex", "me", "be")) and "상여금" in content:
            score += 4.0
        if any(marker in normalized_question for marker in ("국외본봉", "주재", "미국", "독일", "일본", "영국", "홍콩", "중국")) and "국외본봉" in content:
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


def _compose_qa_prompt(question: str, document: str) -> str:
    return f"""당신은 한국은행 보수규정 질의 응답 에이전트(계산 및 설명자)입니다.
아래 제공된 [전체 전처리 문서]만을 근거로 삼아 질문에 최종 답변을 작성하세요. 지식이나 외부 정보를 더하지 마세요.
문서에서 확인되지 않는 내용은 '제공된 전처리 문서에서 확인되지 않습니다.'라고 답하세요.
복합 질문이면 항목별로 나눠 답하세요.
질문이 수식/계산을 요구하면 적용 규칙, 사용한 값, 계산식, 최종 답을 보여주세요.
조회 질문이면 해당 기준표의 값과 근거 조항을 함께 답하세요.
적용 가능 여부를 묻는 질문이면 결론을 명확히 밝히고 근거 조항을 인용하세요.
질문에 여러 조건이 있을 때 계산에 직접 사용한 조건과 사용하지 않은 조건을 구분해 간단히 설명하세요.
질문에 포함된 조건이 문서의 계산 규칙상 직접 계산에 쓰이지 않으면 그 이유를 한 줄로 밝혀야 합니다.
연봉제본봉 조정 질문에서는 직책급이나 상여금을 자동으로 합산하지 마세요.

[질문]
{question}

[전체 전처리 문서]
{document}

최종 답변:"""


def _invoke_1step_context_answer(question: str, document: str) -> Tuple[str, Dict[str, int]]:
    try:
        from langchain_core.messages import HumanMessage
    except ImportError:
        return "Error: LangChain core not installed", {"input": 0, "output": 0}

    model = create_chat_model(temperature=0.0)
    
    prompt = _compose_qa_prompt(question, document)
    response = model.invoke([HumanMessage(content=prompt)])
    final_answer = str(response.content)
    usage = _extract_usage(response)
    
    return final_answer, usage


def answer_with_context(question: str) -> Tuple[str, str]:
    validation = validate_question(question, _validation_entities(question))
    if validation is not None:
        return validation["message"], ""

    document = load_context_document()
    answer, _ = _invoke_1step_context_answer(question, document)
    return answer, document


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
                    "function": "load_context_document",
                    "values": {},
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

    document = load_context_document()
    function_calls.append(
        {
            "module": "src/bok_compensation_context/context_query.py",
            "function": "load_context_document",
            "arguments": {},
            "result": {
                "document_length": len(document),
                "context_preview": _trace_preview_text(document, max_lines=6),
            },
            "next_inputs": [
                {
                    "function": "_invoke_1step_context_answer",
                    "values": {
                        "question": question,
                        "document": "full document",
                    },
                }
            ],
        }
    )

    answer, token_usage = _invoke_1step_context_answer(question, document)
    prompt = _compose_qa_prompt(question, document)
    
    function_calls.append(
        {
            "module": "src/bok_compensation_context/context_query.py",
            "function": "_invoke_1step_context_answer",
            "arguments": {
                "question": question,
                "document": "full document",
            },
            "llm_input": {
                "qa_prompt": prompt,
            },
            "result": {
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
