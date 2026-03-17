"""부칙 + 규정_대체 데이터 검증 스크립트"""
from typedb.driver import TransactionType
from src.bok_compensation.config import TypeDBConfig
from src.bok_compensation.connection import get_driver

config = TypeDBConfig()
driver = get_driver(config)
db = config.database

# 1) 부칙 전체 조회
print("=== 부칙 엔티티 ===")
with driver.transaction(db, TransactionType.READ) as tx:
    results = list(tx.query(
        "match $b isa 부칙, has 부칙조번호 $jo, has 부칙내용 $c, has 우선순위 $p;"
    ).resolve())
    for r in results:
        jo = r.get("jo").get_value()
        content = r.get("c").get_value()[:80]
        pri = r.get("p").get_value()
        print(f"  부칙 제{jo}조 [우선순위={pri}] {content}...")

# 2) 규정_대체 관계 전체 조회
print()
print("=== 규정_대체 관계 ===")
with driver.transaction(db, TransactionType.READ) as tx:
    results = list(tx.query(
        "match $rel isa 규정_대체, has 대체사유 $reason;"
    ).resolve())
    print(f"총 {len(results)}건")
    for r in results:
        reason = r.get("reason").get_value()[:100]
        print(f"  -> {reason}")

# 3) 부칙 제3조 → 별표7 대체 확인
print()
print("=== 부칙 제3조 → 별표7(연봉차등액기준) 대체 ===")
with driver.transaction(db, TransactionType.READ) as tx:
    results = list(tx.query("""
        match
            $buchik isa 부칙, has 부칙조번호 3, has 부칙항번호 1;
            $rel (대체규정: $buchik, 피대체대상: $diff) isa 규정_대체,
                has 대체사유 $reason;
            $diff isa 연봉차등액기준, has 연봉차등액코드 $code, has 차등액 $amt;
    """).resolve())
    for r in results:
        code = r.get("code").get_value()
        amt = r.get("amt").get_value()
        reason = r.get("reason").get_value()[:70]
        print(f"  {code}: {int(amt):,}원 | {reason}")

# 4) 부칙 제3조 → 본문 제4조제2항 대체 확인
print()
print("=== 부칙 제3조 → 본문 제4조제2항 대체 ===")
with driver.transaction(db, TransactionType.READ) as tx:
    results = list(tx.query("""
        match
            $buchik isa 부칙, has 부칙조번호 3;
            $rel (대체규정: $buchik, 피대체대상: $article) isa 규정_대체,
                has 대체사유 $reason;
            $article isa 조문, has 조번호 $jo, has 항번호 $hang;
    """).resolve())
    for r in results:
        jo = r.get("jo").get_value()
        hang = r.get("hang").get_value()
        reason = r.get("reason").get_value()[:80]
        print(f"  제{jo}조 제{hang}항 -> {reason}")

# 5) 부칙 차등액 데이터 (ADIFF) 조회
print()
print("=== 부칙 제3조 경과조치 차등액 (ADIFF) ===")
with driver.transaction(db, TransactionType.READ) as tx:
    results = list(tx.query("""
        match
            $d isa 연봉차등액기준, has 연봉차등액코드 $code, has 차등액 $amt,
                has 연봉차등기준설명 $desc;
            $code contains "ADIFF";
    """).resolve())
    for r in results:
        code = r.get("code").get_value()
        amt = r.get("amt").get_value()
        desc = r.get("desc").get_value()
        print(f"  {code}: {int(amt):,}원 | {desc}")

# 6) 부칙 제2조 → 본문 제4조 대체 확인
print()
print("=== 부칙 제2조 → 본문 제4조(보수 경과조치) ===")
with driver.transaction(db, TransactionType.READ) as tx:
    results = list(tx.query("""
        match
            $buchik isa 부칙, has 부칙조번호 2;
            $rel (대체규정: $buchik, 피대체대상: $article) isa 규정_대체,
                has 대체사유 $reason;
            $article isa 조문, has 조번호 $jo;
    """).resolve())
    for r in results:
        jo = r.get("jo").get_value()
        reason = r.get("reason").get_value()[:80]
        print(f"  제{jo}조 -> {reason}")

driver.close()
print()
print("✅ 검증 완료!")
