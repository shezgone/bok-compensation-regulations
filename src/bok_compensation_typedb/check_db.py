"""DB 데이터 확인 스크립트"""
from typedb.driver import TransactionType
from bok_compensation_typedb.config import TypeDBConfig
from bok_compensation_typedb.connection import get_driver

config = TypeDBConfig()
driver = get_driver(config)
db = config.database

print(f"DB: {db}")
print(f"Exists: {driver.databases.contains(db)}")
print()

queries = [
    ("직렬", "match $x isa 직렬;"),
    ("직급", "match $x isa 직급;"),
    ("직위", "match $x isa 직위;"),
    ("호봉", "match $x isa 호봉;"),
    ("수당", "match $x isa 수당;"),
    ("보수기준", "match $x isa 보수기준;"),
    ("직책급기준", "match $x isa 직책급기준;"),
    ("상여금기준", "match $x isa 상여금기준;"),
    ("연봉차등액기준", "match $x isa 연봉차등액기준;"),
    ("연봉상한액기준", "match $x isa 연봉상한액기준;"),
    ("임금피크제기준", "match $x isa 임금피크제기준;"),
    ("국외본봉기준", "match $x isa 국외본봉기준;"),
    ("초임호봉기준", "match $x isa 초임호봉기준;"),
    ("평가결과", "match $x isa 평가결과;"),
]

total = 0
for label, q in queries:
    tx = driver.transaction(db, TransactionType.READ)
    count = len(list(tx.query(q).resolve()))
    total += count
    print(f"  {label}: {count}건")
    tx.close()

print(f"\n총 엔티티 인스턴스: {total}건")
print()

# 관계 확인
rel_queries = [
    ("직렬분류", "match $r isa 직렬분류;"),
    ("호봉체계구성", "match $r isa 호봉체계구성;"),
    ("직책급결정", "match $r isa 직책급결정;"),
    ("상여금결정", "match $r isa 상여금결정;"),
    ("연봉차등", "match $r isa 연봉차등;"),
    ("연봉상한", "match $r isa 연봉상한;"),
    ("국외본봉결정", "match $r isa 국외본봉결정;"),
    ("초임호봉결정", "match $r isa 초임호봉결정;"),
]

rtotal = 0
for label, q in rel_queries:
    tx = driver.transaction(db, TransactionType.READ)
    count = len(list(tx.query(q).resolve()))
    rtotal += count
    print(f"  {label}: {count}건")
    tx.close()

print(f"\n총 관계 인스턴스: {rtotal}건")
driver.close()
