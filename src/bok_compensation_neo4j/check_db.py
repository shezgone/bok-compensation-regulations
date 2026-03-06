"""Neo4j DB 데이터 확인 스크립트"""
from bok_compensation_neo4j.config import Neo4jConfig
from bok_compensation_neo4j.connection import get_driver

config = Neo4jConfig()
driver = get_driver(config)

print(f"Neo4j URI: {config.uri}")
print(f"Database: {config.database}")
print()

labels = [
    "규정", "조문", "개정이력", "직렬", "직급", "직위", "호봉", "수당",
    "보수기준", "직책급기준", "상여금기준", "연봉차등액기준", "연봉상한액기준",
    "임금피크제기준", "국외본봉기준", "초임호봉기준", "평가결과",
]

with driver.session(database=config.database) as session:
    total = 0
    for label in labels:
        result = session.run(f"MATCH (n:`{label}`) RETURN count(n) AS cnt")
        cnt = result.single()["cnt"]
        total += cnt
        print(f"  {label}: {cnt}건")

    print(f"\n총 노드 인스턴스: {total}건")
    print()

    # 관계 확인
    rels = [
        "규정구성", "규정개정", "직렬분류", "호봉체계구성",
        "해당직급", "해당직위", "해당직책구분", "해당등급", "대상직렬",
    ]
    rtotal = 0
    for rel in rels:
        result = session.run(f"MATCH ()-[r:`{rel}`]->() RETURN count(r) AS cnt")
        cnt = result.single()["cnt"]
        rtotal += cnt
        print(f"  [{rel}]: {cnt}건")
    print(f"\n총 관계 인스턴스: {rtotal}건")

driver.close()
