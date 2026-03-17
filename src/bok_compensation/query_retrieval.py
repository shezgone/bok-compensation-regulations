"""Sparse retrieval helpers for schema/value-aware NL query planning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
from typing import Dict, List, Optional, Sequence, Tuple

from bok_compensation.live_catalog import LiveBinding, get_neo4j_live_bindings, get_typedb_live_bindings


@dataclass(frozen=True)
class CatalogEntry:
    key: str
    kind: str
    label: str
    description: str
    aliases: Tuple[str, ...] = ()
    metadata: Optional[Dict[str, str]] = None


INTENT_ENTRIES: Tuple[CatalogEntry, ...] = (
    CatalogEntry(
        key="salary_step_table",
        kind="intent",
        label="호봉표 조회",
        description="직급별 호봉 목록과 호봉금액을 조회하는 질문",
        aliases=("호봉", "호봉표", "호봉 테이블", "본봉표", "호봉 목록", "급여표"),
    ),
    CatalogEntry(
        key="starting_salary",
        kind="intent",
        label="초임호봉 조회",
        description="G5 또는 신규채용자의 초임호봉과 초봉 본봉 금액을 찾는 질문",
        aliases=("초봉", "초임호봉", "시작호봉", "초임", "신규채용"),
    ),
    CatalogEntry(
        key="wage_peak",
        kind="intent",
        label="임금피크 지급률 조회",
        description="임금피크제 적용연차별 지급률을 조회하는 질문",
        aliases=("임금피크", "임금피크제", "지급률", "연차별 지급률"),
    ),
    CatalogEntry(
        key="overseas_salary",
        kind="intent",
        label="국외본봉 조회",
        description="해외 주재나 파견 직원의 국가별 국외본봉을 조회하는 질문",
        aliases=("국외본봉", "해외 본봉", "해외근무 본봉", "주재", "파견", "해외"),
    ),
    CatalogEntry(
        key="revision_history",
        kind="intent",
        label="개정이력 조회",
        description="보수규정의 개정일과 개정 설명 목록을 조회하는 질문",
        aliases=("개정", "개정이력", "연혁", "이력", "언제 개정"),
    ),
    CatalogEntry(
        key="grade_position_eval_package",
        kind="intent",
        label="직급-직위-평가 종합 조회",
        description="직급, 직위, 평가등급 조합으로 직책급 상여금 연봉차등액 상한액을 묻는 질문",
        aliases=("직책급", "상여금", "상여금지급률", "연봉차등액", "연봉상한액", "평가"),
    ),
    CatalogEntry(
        key="position_pay_lookup",
        kind="intent",
        label="직책급 조회",
        description="직급과 직위 조합으로 직책급을 조회하는 질문",
        aliases=("직책급", "직책 수당", "직위 수당"),
    ),
    CatalogEntry(
        key="bonus_rate_lookup",
        kind="intent",
        label="상여금 지급률 조회",
        description="직위와 평가등급 조합으로 평가상여금 지급률을 조회하는 질문",
        aliases=("상여금지급률", "평가상여금", "보너스 비율"),
    ),
    CatalogEntry(
        key="salary_calculation",
        kind="intent",
        label="연봉제 본봉 산정",
        description="직전 본봉과 평가등급으로 연봉제 본봉(차등액)을 산정하는 질문",
        aliases=("본봉 산정", "연봉 산정", "연봉제 본봉", "본봉 계산", "차등액 산정", "연봉차등", "본봉을 산정"),
    ),
)


VALUE_ENTRIES: Tuple[CatalogEntry, ...] = (
    CatalogEntry("grade-1", "grade", "1급", "종합기획직 1급", ("1 급",)),
    CatalogEntry("grade-2", "grade", "2급", "종합기획직 2급", ("2 급",)),
    CatalogEntry("grade-3", "grade", "3급", "종합기획직 3급", ("3 급",)),
    CatalogEntry("grade-4", "grade", "4급", "종합기획직 4급", ("4 급",)),
    CatalogEntry("grade-5", "grade", "5급", "종합기획직 5급", ("5 급",)),
    CatalogEntry("grade-6", "grade", "6급", "종합기획직 6급", ("6 급",)),
    CatalogEntry("grade-g5", "grade", "G5", "종합기획직 G5 등급", ("g5", "g 5")),
    CatalogEntry("position-p05", "position", "팀장", "직위 코드 P05 팀장", ("팀 장",)),
    CatalogEntry("position-p01", "position", "부서장(가)", "직위 코드 P01 부서장(가)", ("부서장 가",)),
    CatalogEntry("position-p02", "position", "부서장(나)", "직위 코드 P02 부서장(나)", ("부서장 나",)),
    CatalogEntry("position-p04", "position", "부장", "직위 코드 P04 부장", ()),
    CatalogEntry("eval-ex", "eval", "EX", "평가등급 EX", ("ex",)),
    CatalogEntry("eval-ee", "eval", "EE", "평가등급 EE", ("ee",)),
    CatalogEntry("eval-me", "eval", "ME", "평가등급 ME", ("me",)),
    CatalogEntry("eval-be", "eval", "BE", "평가등급 BE", ("be",)),
    CatalogEntry("country-us", "country", "미국", "국가명 미국, 통화 USD", ("usa", "us", "미합중국")),
    CatalogEntry("country-de", "country", "독일", "국가명 독일, 통화 EUR", ()),
    CatalogEntry("country-jp", "country", "일본", "국가명 일본, 통화 JPY", ()),
    CatalogEntry("country-gb", "country", "영국", "국가명 영국, 통화 GBP", ()),
    CatalogEntry("country-hk", "country", "홍콩", "국가명 홍콩, 통화 HKD", ()),
    CatalogEntry("country-cn", "country", "중국", "국가명 중국, 통화 CNY", ()),
    CatalogEntry("track-gp", "track", "종합기획직원", "직렬명 종합기획직원, 1급~6급 및 G1~G5 적용", ("종합기획직",)),
)


def _env_enabled(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def _word_tokens(text: str) -> List[str]:
    return re.findall(r"[0-9a-zA-Z가-힣]+", text.lower())


def _char_ngrams(text: str, size: int = 2) -> Dict[str, float]:
    normalized = normalize_text(text)
    if not normalized:
        return {}
    if len(normalized) < size:
        return {normalized: 1.0}
    grams: Dict[str, float] = {}
    for index in range(len(normalized) - size + 1):
        gram = normalized[index:index + size]
        grams[gram] = grams.get(gram, 0.0) + 1.0
    return grams


def _cosine_similarity(left: Dict[str, float], right: Dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(left[key] * right.get(key, 0.0) for key in left)
    if numerator == 0.0:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _entry_corpus(entry: CatalogEntry) -> str:
    parts = [entry.label, entry.description, *entry.aliases]
    return " ".join(part for part in parts if part)


def _binding_to_entry(binding: LiveBinding) -> CatalogEntry:
    aliases = tuple(alias for alias in binding.aliases if alias)
    description = binding.description or f"{binding.kind} {binding.label}"
    metadata = dict(binding.metadata)
    metadata.update({"key_name": binding.key_name, "key_value": binding.key_value})
    return CatalogEntry(
        key=f"{binding.kind}:{binding.key_value}",
        kind=binding.kind,
        label=binding.label,
        description=description,
        aliases=aliases,
        metadata=metadata,
    )


def _catalog_entries_for_backend(backend: Optional[str], use_live_catalog: bool) -> Tuple[CatalogEntry, ...]:
    if not use_live_catalog:
        return VALUE_ENTRIES

    if backend == "typedb":
        live_entries = tuple(_binding_to_entry(binding) for binding in get_typedb_live_bindings())
    elif backend == "neo4j":
        live_entries = tuple(_binding_to_entry(binding) for binding in get_neo4j_live_bindings())
    else:
        live_entries = ()

    return VALUE_ENTRIES + live_entries


def _entry_score(query: str, entry: CatalogEntry) -> float:
    normalized_query = normalize_text(query)
    normalized_terms = [normalize_text(entry.label), *(normalize_text(alias) for alias in entry.aliases)]
    exact_boost = 0.0
    for term in normalized_terms:
        if term and term in normalized_query:
            exact_boost = max(exact_boost, 1.2 + (len(term) / 20.0))

    query_tokens = set(_word_tokens(query))
    corpus = _entry_corpus(entry)
    corpus_tokens = set(_word_tokens(corpus))
    overlap = len(query_tokens & corpus_tokens)
    token_score = overlap / max(len(query_tokens), 1)
    gram_score = _cosine_similarity(_char_ngrams(query), _char_ngrams(corpus))
    return exact_boost + (token_score * 0.8) + (gram_score * 0.6)


def rank_entries(
    query: str,
    entries: Sequence[CatalogEntry],
    *,
    kind: Optional[str] = None,
    top_k: int = 5,
) -> List[Tuple[CatalogEntry, float]]:
    candidates = [entry for entry in entries if kind is None or entry.kind == kind]
    scored = [(entry, _entry_score(query, entry)) for entry in candidates]
    scored.sort(key=lambda item: item[1], reverse=True)
    return [item for item in scored[:top_k] if item[1] > 0.0]


def detect_intent(query: str) -> Optional[str]:
    hits = rank_entries(query, INTENT_ENTRIES, top_k=1)
    if not hits:
        return None
    entry, score = hits[0]
    if score < 0.45:
        return None
    return entry.key


def detect_best_entry(
    query: str,
    entries: Sequence[CatalogEntry],
    *,
    kind: str,
    min_score: float = 0.8,
) -> Optional[CatalogEntry]:
    hits = rank_entries(query, entries, kind=kind, top_k=1)
    if not hits or hits[0][1] < min_score:
        return None
    return hits[0][0]


def _detect_intent_with_bindings(
    query: str,
    *,
    starting_rule_entry: Optional[CatalogEntry],
    position_pay_rule_entry: Optional[CatalogEntry],
    bonus_rule_entry: Optional[CatalogEntry],
    grade_code: Optional[str],
    eval_grade: Optional[str],
) -> Optional[str]:
    if grade_code and eval_grade and any(term in query for term in ("본봉 산정", "본봉을 산정", "연봉 산정", "연봉제 본봉", "차등액 산정")):
        return "salary_calculation"
    if starting_rule_entry is not None and any(term in query for term in ("초봉", "초임호봉", "시작호봉")):
        return "starting_salary"
    if bonus_rule_entry is not None and any(term in query for term in ("상여금", "지급률", "평가상여금")):
        return "bonus_rate_lookup"
    if position_pay_rule_entry is not None and "직책급" in query and not eval_grade:
        return "position_pay_lookup"
    if position_pay_rule_entry is not None and grade_code and eval_grade and any(term in query for term in ("직책급", "연봉차등", "상한")):
        return "grade_position_eval_package"
    return detect_intent(query)


def _detect_by_regex(query: str, pattern: str) -> Optional[str]:
    match = re.search(pattern, query, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).upper()


def detect_grade_code(query: str) -> Optional[str]:
    regex_hit = _detect_by_regex(query, r"\b([1-6]급|g[1-5]|ga|cl|po)\b")
    if regex_hit is not None:
        return regex_hit
    hits = rank_entries(query, VALUE_ENTRIES, kind="grade", top_k=1)
    if not hits or hits[0][1] < 0.8:
        return None
    return hits[0][0].label.upper()


def detect_eval_grade(query: str) -> Optional[str]:
    regex_hit = _detect_by_regex(query, r"\b(ex|ee|me|be|ni)\b")
    if regex_hit is not None:
        return regex_hit
    hits = rank_entries(query, VALUE_ENTRIES, kind="eval", top_k=1)
    if not hits or hits[0][1] < 0.8:
        return None
    return hits[0][0].label.upper()


def _detect_label(query: str, kind: str, *, min_score: float = 0.8) -> Optional[str]:
    hits = rank_entries(query, VALUE_ENTRIES, kind=kind, top_k=1)
    if not hits or hits[0][1] < min_score:
        return None
    return hits[0][0].label


def detect_country_name(query: str) -> Optional[str]:
    return _detect_label(query, "country")


def detect_position_name(query: str) -> Optional[str]:
    return _detect_label(query, "position")


def detect_track_name(query: str) -> Optional[str]:
    return _detect_label(query, "track")


def build_retrieval_context(
    query: str,
    *,
    backend: Optional[str] = None,
    use_live_catalog: Optional[bool] = None,
    use_key_binding: Optional[bool] = None,
) -> Dict[str, object]:
    live_catalog_enabled = _env_enabled("BOK_USE_LIVE_CATALOG", True) if use_live_catalog is None else use_live_catalog
    key_binding_enabled = _env_enabled("BOK_USE_KEY_BINDING", True) if use_key_binding is None else use_key_binding
    catalog_entries = _catalog_entries_for_backend(backend, live_catalog_enabled)
    intent_hits = rank_entries(query, INTENT_ENTRIES, top_k=3)
    value_hits = rank_entries(query, catalog_entries, top_k=8)

    grade_entry = detect_best_entry(query, catalog_entries, kind="grade", min_score=0.8)
    position_entry = detect_best_entry(query, catalog_entries, kind="position", min_score=0.8)
    eval_entry = detect_best_entry(query, catalog_entries, kind="eval", min_score=0.8)
    country_entry = detect_best_entry(query, catalog_entries, kind="country", min_score=0.8)
    track_entry = detect_best_entry(query, catalog_entries, kind="track", min_score=0.8)

    starting_rule_entry = None
    position_pay_rule_entry = None
    bonus_rule_entry = None
    if key_binding_enabled:
        starting_rule_entry = detect_best_entry(query, catalog_entries, kind="starting-rule", min_score=0.7)
        position_pay_rule_entry = detect_best_entry(query, catalog_entries, kind="position-pay-rule", min_score=0.7)
        bonus_rule_entry = detect_best_entry(query, catalog_entries, kind="bonus-rule", min_score=0.7)

    detected_intent = _detect_intent_with_bindings(
        query,
        starting_rule_entry=starting_rule_entry,
        position_pay_rule_entry=position_pay_rule_entry,
        bonus_rule_entry=bonus_rule_entry,
        grade_code=(grade_entry.label.upper() if grade_entry else detect_grade_code(query)),
        eval_grade=(eval_entry.label.upper() if eval_entry else detect_eval_grade(query)),
    )

    return {
        "intent": detected_intent,
        "intent_hits": [(entry.key, round(score, 3)) for entry, score in intent_hits],
        "value_hits": [(entry.kind, entry.label, round(score, 3)) for entry, score in value_hits],
        "grade_code": (grade_entry.label.upper() if grade_entry else detect_grade_code(query)),
        "eval_grade": (eval_entry.label.upper() if eval_entry else detect_eval_grade(query)),
        "country_name": (country_entry.label if country_entry else detect_country_name(query)),
        "position_name": (position_entry.label if position_entry else detect_position_name(query)),
        "track_name": (track_entry.label if track_entry else detect_track_name(query)),
        "grade_entry": grade_entry,
        "position_entry": position_entry,
        "eval_entry": eval_entry,
        "country_entry": country_entry,
        "track_entry": track_entry,
        "starting_rule_entry": starting_rule_entry,
        "position_pay_rule_entry": position_pay_rule_entry,
        "bonus_rule_entry": bonus_rule_entry,
        "live_catalog_enabled": live_catalog_enabled,
        "key_binding_enabled": key_binding_enabled,
    }


def serialize_entry(entry: Optional[CatalogEntry]) -> Optional[Dict[str, object]]:
    if entry is None:
        return None
    return {
        "key": entry.key,
        "kind": entry.kind,
        "label": entry.label,
        "description": entry.description,
        "aliases": list(entry.aliases),
        "metadata": dict(entry.metadata or {}),
    }


def build_trace_context(
    query: str,
    *,
    backend: str,
    use_live_catalog: Optional[bool] = None,
    use_key_binding: Optional[bool] = None,
) -> Dict[str, object]:
    context = build_retrieval_context(
        query,
        backend=backend,
        use_live_catalog=use_live_catalog,
        use_key_binding=use_key_binding,
    )
    return {
        "question": query,
        "backend": backend,
        "intent": context.get("intent"),
        "intent_hits": list(context.get("intent_hits", [])),
        "value_hits": list(context.get("value_hits", [])),
        "grade_code": context.get("grade_code"),
        "eval_grade": context.get("eval_grade"),
        "country_name": context.get("country_name"),
        "position_name": context.get("position_name"),
        "track_name": context.get("track_name"),
        "live_catalog_enabled": bool(context.get("live_catalog_enabled")),
        "key_binding_enabled": bool(context.get("key_binding_enabled")),
        "selected_entries": {
            "grade": serialize_entry(context.get("grade_entry")),
            "position": serialize_entry(context.get("position_entry")),
            "eval": serialize_entry(context.get("eval_entry")),
            "country": serialize_entry(context.get("country_entry")),
            "track": serialize_entry(context.get("track_entry")),
            "starting_rule": serialize_entry(context.get("starting_rule_entry")),
            "position_pay_rule": serialize_entry(context.get("position_pay_rule_entry")),
            "bonus_rule": serialize_entry(context.get("bonus_rule_entry")),
        },
    }


def maybe_write_query_trace(
    query: str,
    *,
    backend: str,
    trace_context: Dict[str, object],
    plan: Optional[Dict[str, object]] = None,
    error: Optional[str] = None,
) -> Optional[str]:
    trace_dir = os.getenv("BOK_QUERY_TRACE_DIR", "").strip()
    if not trace_dir:
        return None

    output_dir = Path(trace_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    slug = normalize_text(query)[:40] or backend
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    file_path = output_dir / f"{timestamp}_{backend}_{slug}.json"
    payload = {
        "timestamp": timestamp,
        "question": query,
        "backend": backend,
        "trace": trace_context,
        "plan": plan,
        "error": error,
    }
    file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(file_path)