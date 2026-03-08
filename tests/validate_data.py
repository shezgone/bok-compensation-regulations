"""
DB 데이터 전수 검증 스크립트 — PDF 원본 별표 기대값 vs 실제 DB 값 비교

사용법:
    PYTHONPATH=src python tests/validate_data.py neo4j
    PYTHONPATH=src python tests/validate_data.py typedb
    PYTHONPATH=src python tests/validate_data.py all
"""

import sys
from dataclasses import dataclass

# ============================================================
# PDF 원본 기대값 (별표 기준)
# ============================================================

# 별표1 본봉표 — 샘플 검증 (경계값 + 중간값)
EXPECTED_SALARY_SAMPLES = [
    # (직급코드, 호봉번호, 호봉금액)
    ("3급", 21, 3188000), ("3급", 30, 4654000), ("3급", 50, 6890000),
    ("4급", 16, 2343000), ("4급", 25, 3780000), ("4급", 50, 6733000),
    ("5급", 1, 579000),   ("5급", 11, 1554000), ("5급", 25, 3770000), ("5급", 50, 6635000),
    ("6급", 1, 559000),   ("6급", 11, 1509000), ("6급", 50, 5122000),
    # 별표1의 3. 일반사무직원
    ("GA", 1, 531000),   ("GA", 15, 1743000),  ("GA", 30, 3347000),
    # 별표1의 4. 서무직원/청원경찰
    ("CL", 1, 475000),   ("CL", 15, 1560000),  ("CL", 25, 2549000),
    ("PO", 1, 475000),   ("PO", 25, 2549000),
]

# 별표1 호봉 수
EXPECTED_SALARY_COUNTS = [
    ("3급", 30),  # 21~50
    ("4급", 35),  # 16~50
    ("5급", 50),  # 1~50
    ("6급", 50),  # 1~50
    ("GA", 30),  # 1~30 일반사무직원
    ("CL", 25),  # 1~25 서무직원
    ("PO", 25),  # 1~25 청원경찰
]

# 별표1-1 직책급표 — 전건
EXPECTED_POSITION_PAY = [
    ("부서장(가)", "1급", 18192000), ("부서장(가)", "2급", 16236000),
    ("부서장(나)", "1급", 15792000), ("부서장(나)", "2급", 13836000),
    ("국소속실장", "1급", 7692000),  ("국소속실장", "2급", 5736000),
    ("부장", "2급", 4824000),       ("부장", "3급", 2868000),
    ("팀장", "3급", 1956000),       ("팀장", "4급", 0),
    ("조사역", "2급", 3012000),    ("조사역", "3급", 1056000),
    ("주임조사역(C1)", "3급", 1956000), ("주임조사역(C1)", "4급", 0),
    ("조사역(C2)", "4급", 1044000), ("조사역(C2)", "5급", 0),
    ("조사역(C3)", "5급", 1044000), ("조사역(C3)", "6급", 0),
]

# 별표7 연봉차등액 — 전건
EXPECTED_SALARY_DIFF = [
    ("1급", "EX", 3672000), ("1급", "EE", 2448000), ("1급", "ME", 1224000), ("1급", "BE", 0),
    ("2급", "EX", 3348000), ("2급", "EE", 2232000), ("2급", "ME", 1116000), ("2급", "BE", 0),
    ("3급", "EX", 3024000), ("3급", "EE", 2016000), ("3급", "ME", 1008000), ("3급", "BE", 0),
]

# 별표8 연봉상한액 — 전건
EXPECTED_SALARY_CAP = [
    ("1급", 85728000),
    ("2급", 78540000),
    ("3급", 77724000),
]

# 별표9 임금피크제 — 전건
EXPECTED_WAGE_PEAK = [
    (1, 0.9),
    (2, 0.8),
    (3, 0.7),
]

# 별표2 초임호봉표 — 전건
EXPECTED_STARTING = [
    ("종합기획직원", "5급", 11),
    ("종합기획직원", "6급", 6),
    ("일반사무직원", None, 1),
    ("별정직원", None, 4),
    ("서무직원", None, 6),
    ("청원경찰", None, 6),
]

# 별표1-2 평가상여금 지급률 — 샘플
EXPECTED_BONUS_RATE = [
    ("부서장(가)", "EX", 1.0),  ("부서장(가)", "BE", 0.0),
    ("팀장",       "EX", 0.85), ("팀장",       "ME", 0.55),
    ("조사역(C3)", "EX", 0.60), ("조사역(C3)", "ME", 0.30),
]

# 별표1-5 국외본봉 — 샘플
EXPECTED_OVERSEAS = [
    ("미국", "1급", 10780.0, "USD"),
    ("일본", "1급", 1210000.0, "JPY"),
    ("독일", "2급", 8240.0, "EUR"),
    ("영국", "3급", 6350.0, "GBP"),
]

# 보수기준 (위원/집행간부)
EXPECTED_EXEC = [
    ("총재 본봉", 336710000.0),
    ("위원·부총재 본봉", 309770000.0),
    ("감사 본봉", 296310000.0),
    ("부총재보 본봉", 249190000.0),
]

# 노드/관계 수
EXPECTED_COUNTS = {
    "규정": 1, "조문": 18, "개정이력": 9, "직렬": 5, "직급": 14, "직위": 10,
    "호봉": 245, "수당": 15, "보수기준": 4, "직책급기준": 18, "상여금기준": 25,
    "연봉차등액기준": 12, "연봉상한액기준": 3, "임금피크제기준": 3,
    "국외본봉기준": 16, "초임호봉기준": 6, "평가결과": 5,
}


# ============================================================
# 검증 엔진
# ============================================================

@dataclass
class TestResult:
    category: str
    description: str
    passed: bool
    detail: str = ""


def run_neo4j_validation():
    """Neo4j 데이터 전수 검증"""
    from bok_compensation_neo4j.config import Neo4jConfig
    from bok_compensation_neo4j.connection import get_driver

    config = Neo4jConfig()
    driver = get_driver(config)
    results = []

    with driver.session(database=config.database) as s:
        # 1. 노드 수 검증
        for label, expected in EXPECTED_COUNTS.items():
            r = s.run(f"MATCH (n:`{label}`) RETURN count(n) AS cnt")
            actual = r.single()["cnt"]
            ok = actual == expected
            results.append(TestResult(
                "노드수", f"{label}: {expected}건",
                ok, f"실제={actual}" if not ok else ""
            ))

        # 2. 본봉표 샘플
        for grade, hobong, expected_amt in EXPECTED_SALARY_SAMPLES:
            r = s.run("""
                MATCH (g:직급 {직급코드: $g})-[:호봉체계구성]->(h:호봉 {호봉번호: $n})
                RETURN h.호봉금액 AS amt
            """, g=grade, n=hobong)
            rec = r.single()
            if rec is None:
                results.append(TestResult("본봉표", f"{grade} {hobong}호봉", False, "데이터 없음"))
            else:
                actual = int(rec["amt"])
                ok = actual == expected_amt
                results.append(TestResult(
                    "본봉표", f"{grade} {hobong}호봉: {expected_amt:,}",
                    ok, f"실제={actual:,}" if not ok else ""
                ))

        # 3. 호봉 수
        for grade, expected_cnt in EXPECTED_SALARY_COUNTS:
            r = s.run("""
                MATCH (g:직급 {직급코드: $g})-[:호봉체계구성]->(h:호봉)
                RETURN count(h) AS cnt
            """, g=grade)
            actual = r.single()["cnt"]
            ok = actual == expected_cnt
            results.append(TestResult(
                "호봉수", f"{grade}: {expected_cnt}개",
                ok, f"실제={actual}" if not ok else ""
            ))

        # 4. 직책급표
        for pos_name, grade, expected_amt in EXPECTED_POSITION_PAY:
            r = s.run("""
                MATCH (pp:직책급기준)-[:해당직위]->(pos:직위 {직위명: $pos})
                MATCH (pp)-[:해당직급]->(g:직급 {직급코드: $grade})
                RETURN pp.직책급액 AS amt
            """, pos=pos_name, grade=grade)
            rec = r.single()
            if rec is None:
                results.append(TestResult("직책급", f"{pos_name}+{grade}", False, "데이터 없음"))
            else:
                actual = int(rec["amt"])
                ok = actual == expected_amt
                results.append(TestResult(
                    "직책급", f"{pos_name}+{grade}: {expected_amt:,}",
                    ok, f"실제={actual:,}" if not ok else ""
                ))

        # 5. 연봉차등액
        for grade, eval_g, expected_diff in EXPECTED_SALARY_DIFF:
            r = s.run("""
                MATCH (d:연봉차등액기준)-[:해당직급]->(g:직급 {직급코드: $grade})
                MATCH (d)-[:해당등급]->(ev:평가결과 {평가등급: $eval})
                RETURN d.차등액 AS diff
            """, grade=grade, eval=eval_g)
            rec = r.single()
            if rec is None:
                results.append(TestResult("연봉차등", f"{grade}+{eval_g}", False, "데이터 없음"))
            else:
                actual = int(rec["diff"])
                ok = actual == expected_diff
                results.append(TestResult(
                    "연봉차등", f"{grade}+{eval_g}: {expected_diff:,}",
                    ok, f"실제={actual:,}" if not ok else ""
                ))

        # 6. 연봉상한액
        for grade, expected_cap in EXPECTED_SALARY_CAP:
            r = s.run("""
                MATCH (c:연봉상한액기준)-[:해당직급]->(g:직급 {직급코드: $grade})
                RETURN c.연봉상한액 AS cap
            """, grade=grade)
            rec = r.single()
            if rec is None:
                results.append(TestResult("연봉상한", f"{grade}", False, "데이터 없음"))
            else:
                actual = int(rec["cap"])
                ok = actual == expected_cap
                results.append(TestResult(
                    "연봉상한", f"{grade}: {expected_cap:,}",
                    ok, f"실제={actual:,}" if not ok else ""
                ))

        # 7. 임금피크제
        for year, expected_rate in EXPECTED_WAGE_PEAK:
            r = s.run("""
                MATCH (w:임금피크제기준 {적용연차: $year})
                RETURN w.임금피크지급률 AS rate
            """, year=year)
            rec = r.single()
            if rec is None:
                results.append(TestResult("임금피크제", f"{year}년차", False, "데이터 없음"))
            else:
                actual = rec["rate"]
                ok = abs(actual - expected_rate) < 0.001
                results.append(TestResult(
                    "임금피크제", f"{year}년차: {expected_rate}",
                    ok, f"실제={actual}" if not ok else ""
                ))

        # 8. 초임호봉
        for track_name, grade_hint, expected_hobong in EXPECTED_STARTING:
            if grade_hint:
                r = s.run("""
                    MATCH (st:초임호봉기준)-[:대상직렬]->(ct:직렬 {직렬명: $track})
                    WHERE st.설명 CONTAINS $hint
                    RETURN st.초임호봉번호 AS n
                """, track=track_name, hint=grade_hint)
            else:
                r = s.run("""
                    MATCH (st:초임호봉기준)-[:대상직렬]->(ct:직렬 {직렬명: $track})
                    RETURN st.초임호봉번호 AS n
                """, track=track_name)
            rec = r.single()
            label = f"{track_name}" + (f" {grade_hint}" if grade_hint else "")
            if rec is None:
                results.append(TestResult("초임호봉", label, False, "데이터 없음"))
            else:
                actual = rec["n"]
                ok = actual == expected_hobong
                results.append(TestResult(
                    "초임호봉", f"{label}: {expected_hobong}호봉",
                    ok, f"실제={actual}" if not ok else ""
                ))

        # 9. 평가상여금 지급률
        for pos_name, eval_g, expected_rate in EXPECTED_BONUS_RATE:
            r = s.run("""
                MATCH (b:상여금기준)-[:해당직책구분]->(pos:직위 {직위명: $pos})
                MATCH (b)-[:해당등급]->(ev:평가결과 {평가등급: $eval})
                RETURN b.상여금지급률 AS rate
            """, pos=pos_name, eval=eval_g)
            rec = r.single()
            if rec is None:
                results.append(TestResult("상여금", f"{pos_name}+{eval_g}", False, "데이터 없음"))
            else:
                actual = rec["rate"]
                ok = abs(actual - expected_rate) < 0.001
                results.append(TestResult(
                    "상여금", f"{pos_name}+{eval_g}: {expected_rate}",
                    ok, f"실제={actual}" if not ok else ""
                ))

        # 10. 국외본봉
        for country, grade, expected_amt, expected_cur in EXPECTED_OVERSEAS:
            r = s.run("""
                MATCH (o:국외본봉기준 {국가명: $country})-[:해당직급]->(g:직급 {직급코드: $grade})
                RETURN o.국외기본급액 AS amt, o.통화단위 AS cur
            """, country=country, grade=grade)
            rec = r.single()
            if rec is None:
                results.append(TestResult("국외본봉", f"{country}+{grade}", False, "데이터 없음"))
            else:
                actual_amt = rec["amt"]
                actual_cur = rec["cur"]
                ok = abs(actual_amt - expected_amt) < 0.01 and actual_cur == expected_cur
                results.append(TestResult(
                    "국외본봉", f"{country}+{grade}: {expected_amt} {expected_cur}",
                    ok, f"실제={actual_amt} {actual_cur}" if not ok else ""
                ))

        # 11. 보수기준
        for name, expected_amt in EXPECTED_EXEC:
            r = s.run("""
                MATCH (b:보수기준 {보수기준명: $name})
                RETURN b.보수기본급액 AS amt
            """, name=name)
            rec = r.single()
            if rec is None:
                results.append(TestResult("보수기준", name, False, "데이터 없음"))
            else:
                actual = rec["amt"]
                ok = abs(actual - expected_amt) < 0.01
                results.append(TestResult(
                    "보수기준", f"{name}: {expected_amt:,.0f}",
                    ok, f"실제={actual:,.0f}" if not ok else ""
                ))

    driver.close()
    return results


def run_typedb_validation():
    """TypeDB 데이터 전수 검증"""
    from typedb.driver import TransactionType
    from bok_compensation.config import TypeDBConfig
    from bok_compensation.connection import get_driver as get_typedb_driver

    config = TypeDBConfig()
    driver = get_typedb_driver()
    results = []

    def query(q):
        tx = driver.transaction(config.database, TransactionType.READ)
        rows = list(tx.query(q).resolve())
        tx.close()
        return rows

    # 1. 엔티티 수 검증
    for label, expected in EXPECTED_COUNTS.items():
        rows = query(f"match $x isa {label};")
        actual = len(rows)
        ok = actual == expected
        results.append(TestResult(
            "엔티티수", f"{label}: {expected}건",
            ok, f"실제={actual}" if not ok else ""
        ))

    # 2. 본봉표 샘플
    for grade, hobong, expected_amt in EXPECTED_SALARY_SAMPLES:
        rows = query(f"""
            match
                $g isa 직급, has 직급코드 "{grade}";
                (소속직급: $g, 구성호봉: $h) isa 호봉체계구성;
                $h has 호봉번호 {hobong}, has 호봉금액 $amt;
        """)
        if not rows:
            results.append(TestResult("본봉표", f"{grade} {hobong}호봉", False, "데이터 없음"))
        else:
            actual = int(rows[0].get("amt").get_double())
            ok = actual == expected_amt
            results.append(TestResult(
                "본봉표", f"{grade} {hobong}호봉: {expected_amt:,}",
                ok, f"실제={actual:,}" if not ok else ""
            ))

    # 3. 호봉 수
    for grade, expected_cnt in EXPECTED_SALARY_COUNTS:
        rows = query(f"""
            match
                $g isa 직급, has 직급코드 "{grade}";
                (소속직급: $g, 구성호봉: $h) isa 호봉체계구성;
        """)
        actual = len(rows)
        ok = actual == expected_cnt
        results.append(TestResult(
            "호봉수", f"{grade}: {expected_cnt}개",
            ok, f"실제={actual}" if not ok else ""
        ))

    # 4. 직책급표
    for pos_name, grade, expected_amt in EXPECTED_POSITION_PAY:
        rows = query(f"""
            match
                $pos isa 직위, has 직위명 $posname;
                {{ $posname == "{pos_name}"; }};
                $g isa 직급, has 직급코드 "{grade}";
                (적용기준: $pp, 해당직급: $g, 해당직위: $pos) isa 직책급결정;
                $pp has 직책급액 $amt;
        """)
        if not rows:
            results.append(TestResult("직책급", f"{pos_name}+{grade}", False, "데이터 없음"))
        else:
            actual = int(rows[0].get("amt").get_double())
            ok = actual == expected_amt
            results.append(TestResult(
                "직책급", f"{pos_name}+{grade}: {expected_amt:,}",
                ok, f"실제={actual:,}" if not ok else ""
            ))

    # 5. 연봉차등액
    for grade, eval_g, expected_diff in EXPECTED_SALARY_DIFF:
        rows = query(f"""
            match
                $g isa 직급, has 직급코드 "{grade}";
                $ev isa 평가결과, has 평가등급 "{eval_g}";
                (적용기준: $d, 해당직급: $g, 해당등급: $ev) isa 연봉차등;
                $d has 차등액 $diff;
        """)
        if not rows:
            results.append(TestResult("연봉차등", f"{grade}+{eval_g}", False, "데이터 없음"))
        else:
            actual = int(rows[0].get("diff").get_double())
            ok = actual == expected_diff
            results.append(TestResult(
                "연봉차등", f"{grade}+{eval_g}: {expected_diff:,}",
                ok, f"실제={actual:,}" if not ok else ""
            ))

    # 6. 연봉상한액
    for grade, expected_cap in EXPECTED_SALARY_CAP:
        rows = query(f"""
            match
                $g isa 직급, has 직급코드 "{grade}";
                (적용기준: $c, 해당직급: $g) isa 연봉상한;
                $c has 연봉상한액 $cap;
        """)
        if not rows:
            results.append(TestResult("연봉상한", f"{grade}", False, "데이터 없음"))
        else:
            actual = int(rows[0].get("cap").get_double())
            ok = actual == expected_cap
            results.append(TestResult(
                "연봉상한", f"{grade}: {expected_cap:,}",
                ok, f"실제={actual:,}" if not ok else ""
            ))

    # 7. 임금피크제
    for year, expected_rate in EXPECTED_WAGE_PEAK:
        rows = query(f"""
            match
                $w isa 임금피크제기준, has 적용연차 {year}, has 임금피크지급률 $rate;
        """)
        if not rows:
            results.append(TestResult("임금피크제", f"{year}년차", False, "데이터 없음"))
        else:
            actual = rows[0].get("rate").get_double()
            ok = abs(actual - expected_rate) < 0.001
            results.append(TestResult(
                "임금피크제", f"{year}년차: {expected_rate}",
                ok, f"실제={actual}" if not ok else ""
            ))

    # 8. 초임호봉
    for track_name, grade_hint, expected_hobong in EXPECTED_STARTING:
        if grade_hint:
            rows = query(f"""
                match
                    $ct isa 직렬, has 직렬명 "{track_name}";
                    (대상직렬: $ct, 적용기준: $std) isa 초임호봉결정;
                    $std has 초임호봉번호 $n, has 초임호봉기준설명 $desc;
                    $desc contains "{grade_hint}";
            """)
        else:
            rows = query(f"""
                match
                    $ct isa 직렬, has 직렬명 "{track_name}";
                    (대상직렬: $ct, 적용기준: $std) isa 초임호봉결정;
                    $std has 초임호봉번호 $n;
            """)
        label = f"{track_name}" + (f" {grade_hint}" if grade_hint else "")
        if not rows:
            results.append(TestResult("초임호봉", label, False, "데이터 없음"))
        else:
            actual = rows[0].get("n").get_integer()
            ok = actual == expected_hobong
            results.append(TestResult(
                "초임호봉", f"{label}: {expected_hobong}호봉",
                ok, f"실제={actual}" if not ok else ""
            ))

    # 9. 보수기준
    for name, expected_amt in EXPECTED_EXEC:
        rows = query(f"""
            match
                $b isa 보수기준, has 보수기준명 "{name}", has 보수기본급액 $amt;
        """)
        if not rows:
            results.append(TestResult("보수기준", name, False, "데이터 없음"))
        else:
            actual = rows[0].get("amt").get_double()
            ok = abs(actual - expected_amt) < 0.01
            results.append(TestResult(
                "보수기준", f"{name}: {expected_amt:,.0f}",
                ok, f"실제={actual:,.0f}" if not ok else ""
            ))

    # 10. 평가상여금 지급률
    for pos_name, eval_g, expected_rate in EXPECTED_BONUS_RATE:
        rows = query(f"""
            match
                $pos isa 직위, has 직위명 $posname;
                {{ $posname == "{pos_name}"; }};
                $ev isa 평가결과, has 평가등급 "{eval_g}";
                (적용기준: $b, 해당직책구분: $pos, 해당등급: $ev) isa 상여금결정;
                $b has 상여금지급률 $rate;
        """)
        if not rows:
            results.append(TestResult("상여금", f"{pos_name}+{eval_g}", False, "데이터 없음"))
        else:
            actual = rows[0].get("rate").get_double()
            ok = abs(actual - expected_rate) < 0.001
            results.append(TestResult(
                "상여금", f"{pos_name}+{eval_g}: {expected_rate}",
                ok, f"실제={actual}" if not ok else ""
            ))

    # 11. 국외본봉
    for country, grade, expected_amt, expected_cur in EXPECTED_OVERSEAS:
        rows = query(f"""
            match
                $g isa 직급, has 직급코드 "{grade}";
                (적용기준: $os, 해당직급: $g) isa 국외본봉결정;
                $os has 국가명 "{country}", has 국외기본급액 $amt, has 통화단위 $cur;
        """)
        if not rows:
            results.append(TestResult("국외본봉", f"{country}+{grade}", False, "데이터 없음"))
        else:
            actual_amt = rows[0].get("amt").get_double()
            actual_cur = rows[0].get("cur").get_value()
            ok = abs(actual_amt - expected_amt) < 0.01 and actual_cur == expected_cur
            results.append(TestResult(
                "국외본봉", f"{country}+{grade}: {expected_amt} {expected_cur}",
                ok, f"실제={actual_amt} {actual_cur}" if not ok else ""
            ))

    driver.close()
    return results


# ============================================================
# 출력
# ============================================================

def print_results(db_name: str, results: list):
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    total = len(results)

    print(f"\n{'='*60}")
    print(f"  {db_name} 데이터 검증 결과: {passed}/{total} 통과")
    print(f"{'='*60}")

    # 카테고리별 그룹
    cats = {}
    for r in results:
        cats.setdefault(r.category, []).append(r)

    for cat, items in cats.items():
        cat_pass = sum(1 for i in items if i.passed)
        cat_total = len(items)
        status = "✅" if cat_pass == cat_total else "❌"
        print(f"\n  {status} [{cat}] {cat_pass}/{cat_total}")
        for i in items:
            if not i.passed:
                print(f"     ❌ {i.description}  → {i.detail}")

    if failed > 0:
        print(f"\n  ⚠️  {failed}건 실패!")
    else:
        print(f"\n  ✅ 모든 검증 통과!")
    print()


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "all"

    if target in ("neo4j", "all"):
        try:
            results = run_neo4j_validation()
            print_results("Neo4j", results)
        except Exception as e:
            print(f"Neo4j 검증 실패: {e}")

    if target in ("typedb", "all"):
        try:
            results = run_typedb_validation()
            print_results("TypeDB", results)
        except Exception as e:
            print(f"TypeDB 검증 실패: {e}")


if __name__ == "__main__":
    main()
