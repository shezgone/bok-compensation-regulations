"""Live DB catalog extraction for retrieval-guided query planning."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence

from typedb.driver import TransactionType

from bok_compensation.config import TypeDBConfig
from bok_compensation.connection import get_driver as get_typedb_driver
from bok_compensation_neo4j.config import Neo4jConfig
from bok_compensation_neo4j.connection import get_driver as get_neo4j_driver


@dataclass(frozen=True)
class LiveBinding:
    kind: str
    label: str
    key_name: str
    key_value: str
    aliases: tuple[str, ...] = ()
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


def _typedb_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    return value.get_value()


def _typedb_integer(value: Any) -> Optional[int]:
    if value is None:
        return None
    return value.get_integer()


def _typedb_double(value: Any) -> Optional[float]:
    if value is None:
        return None
    return value.get_double()


def _read_typedb_rows(query: str, variables: Dict[str, str]) -> List[Dict[str, Any]]:
    config = TypeDBConfig()
    driver = get_typedb_driver(config)
    tx = None
    rows: List[Dict[str, Any]] = []
    try:
        tx = driver.transaction(config.database, TransactionType.READ)
        for row in tx.query(query).resolve():
            record: Dict[str, Any] = {}
            for name, value_type in variables.items():
                concept = row.get(name)
                if value_type == "string":
                    record[name] = _typedb_string(concept)
                elif value_type == "integer":
                    record[name] = _typedb_integer(concept)
                elif value_type == "double":
                    record[name] = _typedb_double(concept)
                else:
                    record[name] = concept
            rows.append(record)
    except Exception:
        return []
    finally:
        if tx is not None:
            tx.close()
        driver.close()
    return rows


def _read_neo4j_rows(query: str) -> List[Dict[str, Any]]:
    config = Neo4jConfig()
    driver = get_neo4j_driver(config)
    try:
        with driver.session(database=config.database) as session:
            return [record.data() for record in session.run(query)]
    except Exception:
        return []
    finally:
        driver.close()


def _starting_salary_grade(track_code: str, description: str, available_step_grades: Sequence[str]) -> Optional[str]:
    fixed_map = {
        "CT-GA": "GA",
        "CT-CL": "CL",
        "CT-PO": "PO",
    }
    if track_code in fixed_map and fixed_map[track_code] in available_step_grades:
        return fixed_map[track_code]

    if track_code == "CT-GP":
        for candidate in ("5급", "6급", "4급", "3급", "2급", "1급"):
            if candidate in description and candidate in available_step_grades:
                return candidate
    return None


@lru_cache(maxsize=1)
def get_typedb_live_bindings() -> List[LiveBinding]:
    step_grade_rows = _read_typedb_rows(
        """
        match
            $g isa 직급, has 직급코드 $code;
            (소속직급: $g, 구성호봉: $step) isa 호봉체계구성;
        """,
        {"code": "string"},
    )
    available_step_grades = sorted({row["code"] for row in step_grade_rows if row.get("code")})

    bindings: List[LiveBinding] = []

    for row in _read_typedb_rows(
        """
        match
            $track isa 직렬, has 직렬코드 $code, has 직렬명 $name;
        sort $name;
        """,
        {"code": "string", "name": "string"},
    ):
        code = row["code"]
        name = row["name"]
        aliases = tuple(alias for alias in (name.replace("직원", ""),) if alias and alias != name)
        bindings.append(LiveBinding("track", name, "직렬코드", code, aliases, f"직렬 {name}"))

    for row in _read_typedb_rows(
        """
        match
            $grade isa 직급, has 직급코드 $code, has 직급명 $name;
        sort $code;
        """,
        {"code": "string", "name": "string"},
    ):
        bindings.append(
            LiveBinding(
                "grade",
                row["code"],
                "직급코드",
                row["code"],
                tuple(alias for alias in (row["name"],) if alias and alias != row["code"]),
                f"직급 {row['code']}",
            )
        )

    for row in _read_typedb_rows(
        """
        match
            $position isa 직위, has 직위코드 $code, has 직위명 $name;
        sort $code;
        """,
        {"code": "string", "name": "string"},
    ):
        aliases = tuple(alias for alias in (row["code"], row["name"].replace("(", " ").replace(")", " ")) if alias and alias != row["name"])
        bindings.append(LiveBinding("position", row["name"], "직위명", row["name"], aliases, f"직위 {row['name']}", {"position_code": row["code"]}))

    for row in _read_typedb_rows(
        """
        match
            $evaluation isa 평가결과, has 평가등급 $grade;
        sort $grade;
        """,
        {"grade": "string"},
    ):
        bindings.append(LiveBinding("eval", row["grade"], "평가등급", row["grade"], (row["grade"].lower(),), f"평가등급 {row['grade']}"))

    for row in _read_typedb_rows(
        """
        match
            $rule isa 국외본봉기준, has 국가코드 $country_code, has 국가명 $country_name, has 통화단위 $currency;
        sort $country_name;
        """,
        {"country_code": "string", "country_name": "string", "currency": "string"},
    ):
        bindings.append(
            LiveBinding(
                "country",
                row["country_name"],
                "국가명",
                row["country_name"],
                tuple(alias for alias in (row["country_code"],) if alias and alias != row["country_name"]),
                f"국가 {row['country_name']} ({row['currency']})",
                {"currency": row["currency"]},
            )
        )

    track_grade_rows = _read_typedb_rows(
        """
        match
            $track isa 직렬, has 직렬코드 $track_code, has 직렬명 $track_name;
            $grade isa 직급, has 직급코드 $grade_code;
            (분류직렬: $track, 분류직급: $grade) isa 직렬분류;
        """,
        {"track_code": "string", "track_name": "string", "grade_code": "string"},
    )
    track_grade_map: Dict[str, List[str]] = {}
    for row in track_grade_rows:
        track_grade_map.setdefault(row["track_code"], []).append(row["grade_code"])

    for row in _read_typedb_rows(
        """
        match
            $track isa 직렬, has 직렬코드 $track_code, has 직렬명 $track_name;
            $rule isa 초임호봉기준, has 초임호봉코드 $rule_code, has 초임호봉번호 $step_no, has 초임호봉기준설명 $desc;
            (대상직렬: $track, 적용기준: $rule) isa 초임호봉결정;
        """,
        {"track_code": "string", "track_name": "string", "rule_code": "string", "step_no": "integer", "desc": "string"},
    ):
        salary_grade_code = _starting_salary_grade(row["track_code"], row["desc"], available_step_grades)
        if salary_grade_code is None:
            unique_grades = track_grade_map.get(row["track_code"], [])
            if len(unique_grades) == 1 and unique_grades[0] in available_step_grades:
                salary_grade_code = unique_grades[0]

        bindings.append(
            LiveBinding(
                "starting-rule",
                f"{row['track_name']} 초임호봉 {row['step_no']}",
                "초임호봉코드",
                row["rule_code"],
                (row["track_name"], row["desc"]),
                row["desc"],
                {
                    "track_code": row["track_code"],
                    "track_name": row["track_name"],
                    "initial_step_no": row["step_no"],
                    "salary_grade_code": salary_grade_code,
                },
            )
        )

    for row in _read_typedb_rows(
        """
        match
            $position isa 직위, has 직위코드 $position_code, has 직위명 $position_name;
            $grade isa 직급, has 직급코드 $grade_code;
            $rule isa 직책급기준, has 직책급코드 $rule_code, has 직책급액 $amount;
            (적용기준: $rule, 해당직급: $grade, 해당직위: $position) isa 직책급결정;
        """,
        {"position_code": "string", "position_name": "string", "grade_code": "string", "rule_code": "string", "amount": "double"},
    ):
        bindings.append(
            LiveBinding(
                "position-pay-rule",
                f"{row['grade_code']} {row['position_name']} 직책급",
                "직책급코드",
                row["rule_code"],
                (row["position_name"], row["grade_code"], "직책급"),
                f"직책급 {row['amount']}",
                {
                    "position_code": row["position_code"],
                    "position_name": row["position_name"],
                    "grade_code": row["grade_code"],
                    "amount": row["amount"],
                },
            )
        )

    for row in _read_typedb_rows(
        """
        match
            $position isa 직위, has 직위코드 $position_code, has 직위명 $position_name;
            $evaluation isa 평가결과, has 평가등급 $eval_grade;
            $rule isa 상여금기준, has 상여금코드 $rule_code, has 상여금지급률 $rate;
            (적용기준: $rule, 해당직책구분: $position, 해당등급: $evaluation) isa 상여금결정;
        """,
        {"position_code": "string", "position_name": "string", "eval_grade": "string", "rule_code": "string", "rate": "double"},
    ):
        bindings.append(
            LiveBinding(
                "bonus-rule",
                f"{row['position_name']} {row['eval_grade']} 상여금지급률",
                "상여금코드",
                row["rule_code"],
                (row["position_name"], row["eval_grade"], "상여금", "지급률"),
                f"상여금지급률 {row['rate']}",
                {
                    "position_code": row["position_code"],
                    "position_name": row["position_name"],
                    "eval_grade": row["eval_grade"],
                    "rate": row["rate"],
                },
            )
        )

    return bindings


@lru_cache(maxsize=1)
def get_neo4j_live_bindings() -> List[LiveBinding]:
    step_grade_rows = _read_neo4j_rows("MATCH (g:직급)-[:호봉체계구성]->(:호봉) RETURN DISTINCT g.직급코드 AS code")
    available_step_grades = sorted({row["code"] for row in step_grade_rows if row.get("code")})

    bindings: List[LiveBinding] = []

    for row in _read_neo4j_rows("MATCH (n:직렬) RETURN n.직렬코드 AS code, n.직렬명 AS name ORDER BY name"):
        name = row["name"]
        aliases = tuple(alias for alias in (name.replace("직원", ""),) if alias and alias != name)
        bindings.append(LiveBinding("track", name, "직렬코드", row["code"], aliases, f"직렬 {name}"))

    for row in _read_neo4j_rows("MATCH (n:직급) RETURN n.직급코드 AS code, n.직급명 AS name ORDER BY code"):
        bindings.append(
            LiveBinding(
                "grade",
                row["code"],
                "직급코드",
                row["code"],
                tuple(alias for alias in (row["name"],) if alias and alias != row["code"]),
                f"직급 {row['code']}",
            )
        )

    for row in _read_neo4j_rows("MATCH (n:직위) RETURN n.직위코드 AS code, n.직위명 AS name ORDER BY code"):
        aliases = tuple(alias for alias in (row["code"], row["name"].replace("(", " ").replace(")", " ")) if alias and alias != row["name"])
        bindings.append(LiveBinding("position", row["name"], "직위명", row["name"], aliases, f"직위 {row['name']}", {"position_code": row["code"]}))

    for row in _read_neo4j_rows("MATCH (n:평가결과) RETURN n.평가등급 AS grade ORDER BY grade"):
        bindings.append(LiveBinding("eval", row["grade"], "평가등급", row["grade"], (row["grade"].lower(),), f"평가등급 {row['grade']}"))

    for row in _read_neo4j_rows("MATCH (n:국외본봉기준) RETURN DISTINCT n.국가코드 AS country_code, n.국가명 AS country_name, n.통화단위 AS currency ORDER BY country_name"):
        bindings.append(
            LiveBinding(
                "country",
                row["country_name"],
                "국가명",
                row["country_name"],
                tuple(alias for alias in (row["country_code"],) if alias and alias != row["country_name"]),
                f"국가 {row['country_name']} ({row['currency']})",
                {"currency": row["currency"]},
            )
        )

    track_grade_rows = _read_neo4j_rows(
        "MATCH (track:직렬)-[:직렬분류]->(grade:직급) RETURN track.직렬코드 AS track_code, track.직렬명 AS track_name, grade.직급코드 AS grade_code"
    )
    track_grade_map: Dict[str, List[str]] = {}
    for row in track_grade_rows:
        track_grade_map.setdefault(row["track_code"], []).append(row["grade_code"])

    for row in _read_neo4j_rows(
        "MATCH (rule:초임호봉기준)-[:대상직렬]->(track:직렬) RETURN elementId(rule) AS element_id, rule.초임호봉코드 AS rule_code, rule.초임호봉번호 AS step_no, rule.설명 AS desc, track.직렬코드 AS track_code, track.직렬명 AS track_name"
    ):
        salary_grade_code = _starting_salary_grade(row["track_code"], row["desc"], available_step_grades)
        if salary_grade_code is None:
            unique_grades = track_grade_map.get(row["track_code"], [])
            if len(unique_grades) == 1 and unique_grades[0] in available_step_grades:
                salary_grade_code = unique_grades[0]

        bindings.append(
            LiveBinding(
                "starting-rule",
                f"{row['track_name']} 초임호봉 {row['step_no']}",
                "초임호봉코드",
                row.get("rule_code") or row["element_id"],
                (row["track_name"], row["desc"]),
                row["desc"],
                {
                    "track_code": row["track_code"],
                    "track_name": row["track_name"],
                    "initial_step_no": row["step_no"],
                    "salary_grade_code": salary_grade_code,
                    "element_id": row["element_id"],
                },
            )
        )

    for row in _read_neo4j_rows(
        "MATCH (rule:직책급기준)-[:해당직위]->(position:직위) MATCH (rule)-[:해당직급]->(grade:직급) RETURN elementId(rule) AS element_id, rule.직책급코드 AS rule_code, position.직위코드 AS position_code, position.직위명 AS position_name, grade.직급코드 AS grade_code, rule.직책급액 AS amount"
    ):
        bindings.append(
            LiveBinding(
                "position-pay-rule",
                f"{row['grade_code']} {row['position_name']} 직책급",
                "직책급코드",
                row.get("rule_code") or row["element_id"],
                (row["position_name"], row["grade_code"], "직책급"),
                f"직책급 {row['amount']}",
                {
                    "position_code": row["position_code"],
                    "position_name": row["position_name"],
                    "grade_code": row["grade_code"],
                    "amount": row["amount"],
                    "element_id": row["element_id"],
                },
            )
        )

    for row in _read_neo4j_rows(
        "MATCH (rule:상여금기준)-[:해당직책구분]->(position:직위) MATCH (rule)-[:해당등급]->(evaluation:평가결과) WHERE rule.상여금지급률 IS NOT NULL RETURN elementId(rule) AS element_id, rule.상여금코드 AS rule_code, position.직위코드 AS position_code, position.직위명 AS position_name, evaluation.평가등급 AS eval_grade, rule.상여금지급률 AS rate"
    ):
        bindings.append(
            LiveBinding(
                "bonus-rule",
                f"{row['position_name']} {row['eval_grade']} 상여금지급률",
                "상여금코드",
                row.get("rule_code") or row["element_id"],
                (row["position_name"], row["eval_grade"], "상여금", "지급률"),
                f"상여금지급률 {row['rate']}",
                {
                    "position_code": row["position_code"],
                    "position_name": row["position_name"],
                    "eval_grade": row["eval_grade"],
                    "rate": row["rate"],
                    "element_id": row["element_id"],
                },
            )
        )

    return bindings