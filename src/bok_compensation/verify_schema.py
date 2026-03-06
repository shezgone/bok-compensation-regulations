"""TypeDB 3.x 스키마 검증 쿼리 테스트"""

from typedb.driver import TransactionType

from .config import TypeDBConfig
from .connection import get_driver

config = TypeDBConfig()
driver = get_driver(config)

print("=== TypeDB 3.x 스키마 검증 ===\n")


def query_types(label, query_str):
    tx = driver.transaction(config.database, TransactionType.READ)
    try:
        answer = tx.query(query_str).resolve()
        # answer itself may be iterable
        rows = list(answer)
        print(f"{label} 수: {len(rows)}")
        for row in rows:
            try:
                t = row.get("x")
                print(f"  - {t.get_label()}")
            except Exception:
                print(f"  - {row}")
    except Exception as ex:
        print(f"{label} 조회 실패: {ex}")
    tx.close()


query_types("엔티티 타입", "match entity $x;")
query_types("관계 타입", "match relation $x;")
query_types("속성 타입", "match attribute $x;")

driver.close()
print("\n검증 완료!")
