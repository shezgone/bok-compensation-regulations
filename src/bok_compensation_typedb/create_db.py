"""
한국은행 보수규정 온톨로지 - TypeDB 3.x 스키마 로더
데이터베이스 생성 및 스키마 정의
"""

from typedb.driver import TransactionType

from .config import TypeDBConfig
from .connection import get_driver

config = TypeDBConfig()
driver = get_driver(config)

# 1. 데이터베이스 생성
if driver.databases.contains(config.database):
    print(f"기존 '{config.database}' 삭제 후 재생성...")
    driver.databases.get(config.database).delete()
driver.databases.create(config.database)
print(f"데이터베이스 '{config.database}' 생성 완료")

# 2. 스키마 로드
import os
schema_path = os.path.abspath(config.schema_file)
with open(schema_path, "r", encoding="utf-8") as f:
    schema_query = f.read()

tx = driver.transaction(config.database, TransactionType.SCHEMA)
tx.query(schema_query).resolve()
tx.commit()
print("스키마 정의 완료")

# 3. 검증
tx = driver.transaction(config.database, TransactionType.READ)
result = tx.query("match entity $x;").resolve()
answers = list(result)
print(f"\n등록된 엔티티 타입 수: {len(answers)}")
for row in answers:
    print(f"  - {row.get('x').get_label()}")
tx.close()

driver.close()
print("\n모든 작업 완료!")
