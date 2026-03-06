"""
Neo4j 스키마 제약조건 및 인덱스 생성

TypeDB의 엔티티 → Neo4j 노드 레이블
TypeDB의 관계(N-ary) → Neo4j 관계 또는 중간 노드
"""

from .config import Neo4jConfig
from .connection import get_driver


CONSTRAINTS = [
    # 노드 유니크 제약
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:규정) REQUIRE n.규정번호 IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:직렬) REQUIRE n.직렬코드 IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:직급) REQUIRE n.직급코드 IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:직위) REQUIRE n.직위코드 IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:수당) REQUIRE n.수당코드 IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:보수기준) REQUIRE n.코드 IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:직책급기준) REQUIRE n.코드 IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:상여금기준) REQUIRE n.코드 IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:연봉차등액기준) REQUIRE n.코드 IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:연봉상한액기준) REQUIRE n.코드 IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:임금피크제기준) REQUIRE n.코드 IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:국외본봉기준) REQUIRE n.코드 IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:초임호봉기준) REQUIRE n.코드 IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:평가결과) REQUIRE n.평가등급 IS UNIQUE",
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS FOR (n:호봉) ON (n.호봉번호)",
    "CREATE INDEX IF NOT EXISTS FOR (n:조문) ON (n.조번호)",
    "CREATE INDEX IF NOT EXISTS FOR (n:개정이력) ON (n.개정일)",
]


def create_schema():
    config = Neo4jConfig()
    driver = get_driver(config)

    with driver.session(database=config.database) as session:
        for c in CONSTRAINTS:
            session.run(c)
            print(f"  [OK] {c[:60]}...")

        for idx in INDEXES:
            session.run(idx)
            print(f"  [OK] {idx[:60]}...")

    driver.close()
    print("\nNeo4j 스키마(제약조건/인덱스) 생성 완료")


if __name__ == "__main__":
    create_schema()
