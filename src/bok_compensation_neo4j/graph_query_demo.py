"""
RDB로는 어려운 그래프 탐색 질문 — Neo4j Cypher 예시

질문:
  "3급 직원이 팀장 직책을 맡고, EX 평가를 받은 경우
   — 해당 직급의 최고 호봉 본봉은 얼마이고,
   — 직책급은 얼마이며,
   — 평가상여금 지급률은 몇 %이고,
   — 연봉제 차등액은 얼마이며,
   — 연봉제 상한액은 얼마인가?"

Neo4j에서는 하나의 Cypher 쿼리로 다중 패턴 매칭을 수행하여
5개 관계를 동시에 탐색할 수 있습니다.
"""

from bok_compensation_neo4j.config import Neo4jConfig
from bok_compensation_neo4j.connection import get_driver

TARGET_GRADE = "3급"
TARGET_POSITION = "팀장"
TARGET_EVAL = "EX"


def main():
    config = Neo4jConfig()
    driver = get_driver(config)

    print("=" * 70)
    print(f'질문: "{TARGET_GRADE} 직원이 {TARGET_POSITION} 직책을 맡고')
    print(f'       {TARGET_EVAL} 평가를 받은 경우,')
    print('       본봉·직책급·상여금지급률·연봉차등액·연봉상한액은?"')
    print("=" * 70)

    # ================================================================
    # 핵심: 하나의 Cypher 쿼리로 5개 관계를 동시에 그래프 탐색
    #
    #  직급("3급") <-[:호봉체계구성]- 호봉(본봉)
    #       ↑
    #       ├── 직책급기준 -[:해당직급]-> 직급
    #       │              -[:해당직위]-> 직위("팀장")
    #       │
    #       ├── 연봉차등액기준 -[:해당직급]-> 직급
    #       │                 -[:해당등급]-> 평가("EX")
    #       │
    #       └── 연봉상한액기준 -[:해당직급]-> 직급
    #
    #  상여금기준 -[:해당직책구분]-> 직위("팀장")
    #            -[:해당등급]-> 평가("EX")
    # ================================================================

    QUERY = f"""
        MATCH (grade:직급 {{직급코드: '{TARGET_GRADE}'}})-[:호봉체계구성]->(step:호봉)
        MATCH (pos:직위 {{직위명: '{TARGET_POSITION}'}})
        MATCH (eval:평가결과 {{평가등급: '{TARGET_EVAL}'}})
        MATCH (pp:직책급기준)-[:해당직급]->(grade), (pp)-[:해당직위]->(pos)
        MATCH (b:상여금기준)-[:해당직책구분]->(pos), (b)-[:해당등급]->(eval)
        MATCH (d:연봉차등액기준)-[:해당직급]->(grade), (d)-[:해당등급]->(eval)
        MATCH (c:연봉상한액기준)-[:해당직급]->(grade)
        RETURN step.호봉번호 AS n, step.호봉금액 AS salary,
               pp.직책급액 AS ppay, b.지급률 AS brate,
               d.차등액 AS diff, c.상한액 AS cap
        ORDER BY n DESC
        LIMIT 1
    """

    print("\n[Cypher 쿼리]")
    print(QUERY)
    print("-" * 70)

    with driver.session(database=config.database) as session:
        result = session.run(QUERY)
        record = result.single()

        if not record:
            print("  결과 없음")
        else:
            n = record["n"]
            salary = record["salary"]
            ppay = record["ppay"]
            brate = record["brate"]
            diff = record["diff"]
            cap = record["cap"]

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

    driver.close()


if __name__ == "__main__":
    main()
