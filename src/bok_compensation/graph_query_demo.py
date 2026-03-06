"""
RDB로는 어려운 그래프 탐색 질문 — TypeDB 단일 쿼리 예시

질문:
  "3급 직원이 팀장 직책을 맡고, EX 평가를 받은 경우
   — 해당 직급의 최고 호봉 본봉은 얼마이고,
   — 직책급은 얼마이며,
   — 평가상여금 지급률은 몇 %이고,
   — 연봉제 차등액은 얼마이며,
   — 연봉제 상한액은 얼마인가?"

왜 RDB로 어려운가:
  RDB에서는 5개 이상의 테이블을 JOIN해야 하고,
  각 테이블의 관계가 서로 다른 복합키(직급+직위, 직급+평가등급 등)로 연결되므로
  쿼리가 복잡해지고 스키마 변경에 취약합니다.

  TypeDB에서는 하나의 match 패턴으로 그래프를 따라가며
  자연스럽게 다차원 관계를 탐색할 수 있습니다.
"""

from typedb.driver import TransactionType
from bok_compensation.config import TypeDBConfig
from bok_compensation.connection import get_driver

TARGET_GRADE = "3급"
TARGET_POSITION = "팀장"
TARGET_EVAL = "EX"


def main():
    config = TypeDBConfig()
    driver = get_driver(config)
    db = config.database

    tx = driver.transaction(db, TransactionType.READ)

    print("=" * 70)
    print(f'질문: "{TARGET_GRADE} 직원이 {TARGET_POSITION} 직책을 맡고')
    print(f'       {TARGET_EVAL} 평가를 받은 경우,')
    print('       본봉·직책급·상여금지급률·연봉차등액·연봉상한액은?"')
    print("=" * 70)

    # ================================================================
    # 핵심: 하나의 match 패턴으로 5개 관계를 동시에 그래프 탐색
    #
    #  직급("3급") ──→ 호봉체계구성 ──→ 호봉(본봉)
    #       │
    #       ├── + 직위("팀장") ──→ 직책급결정 ──→ 직책급액
    #       │
    #       ├── + 평가("EX")  ──→ 연봉차등   ──→ 차등액
    #       │
    #       └────────────────→ 연봉상한   ──→ 상한액
    #
    #  직위("팀장") + 평가("EX") ──→ 상여금결정 ──→ 지급률
    # ================================================================

    QUERY = f"""
        match
            $grade isa 직급, has 직급코드 "{TARGET_GRADE}";
            $pos isa 직위, has 직위명 $posname;
            {{ $posname == "{TARGET_POSITION}"; }};
            $eval isa 평가결과, has 평가등급 "{TARGET_EVAL}";

            (소속직급: $grade, 구성호봉: $step) isa 호봉체계구성;
            $step has 호봉번호 $n, has 호봉금액 $salary;

            (적용기준: $ppstd, 해당직급: $grade, 해당직위: $pos) isa 직책급결정;
            $ppstd has 직책급액 $ppay;

            (적용기준: $bstd, 해당직책구분: $pos, 해당등급: $eval) isa 상여금결정;
            $bstd has 지급률 $brate;

            (적용기준: $dstd, 해당직급: $grade, 해당등급: $eval) isa 연봉차등;
            $dstd has 차등액 $diff;

            (적용기준: $cstd, 해당직급: $grade) isa 연봉상한;
            $cstd has 상한액 $cap;
        sort $n desc;
        limit 1;
    """

    print("\n[TypeQL 쿼리]")
    print(QUERY)
    print("-" * 70)

    result = tx.query(QUERY).resolve()
    rows = list(result)

    if not rows:
        print("  결과 없음")
    else:
        row = rows[0]
        n = row.get("n").get_integer()
        salary = row.get("salary").get_double()
        ppay = row.get("ppay").get_double()
        brate = row.get("brate").get_double()
        diff = row.get("diff").get_double()
        cap = row.get("cap").get_double()

        monthly_ppay = ppay / 12
        monthly_basic = salary + monthly_ppay
        annual_basic = monthly_basic * 12
        bonus_amount = annual_basic * brate
        annual_diff = diff * 12
        annual_total = annual_basic + bonus_amount + annual_diff

        print(f"\n[결과] {TARGET_GRADE} · {TARGET_POSITION} · {TARGET_EVAL} 평가")
        print(f"  ┌─ 본봉 ({n}호봉):      월 {salary:>12,.0f}원")
        print(f"  ├─ 직책급:              월 {monthly_ppay:>12,.0f}원  (연 {ppay:,.0f})")
        print(f"  ├─ 기본급 합계:         월 {monthly_basic:>12,.0f}원  (연 {annual_basic:,.0f})")
        print(f"  ├─ 평가상여금 지급률:         {brate*100:>7.0f}%")
        print(f"  │   → 연간 상여금:          {bonus_amount:>12,.0f}원  (기본급×{brate*100:.0f}%)")
        print(f"  ├─ 연봉제 차등액:       월 {diff:>12,.0f}원  (연 {annual_diff:,.0f})")
        print(f"  ├─ 연봉제 상한액:       월 {cap:>12,.0f}원")
        print(f"  └─ 추정 연간 총보수:        {annual_total:>12,.0f}원")
        print(f"     (기본급 {annual_basic:,.0f} + 상여 {bonus_amount:,.0f} + 차등 {annual_diff:,.0f})")

    tx.close()
    driver.close()


if __name__ == "__main__":
    main()
