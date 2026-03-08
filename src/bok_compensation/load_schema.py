"""
한국은행 보수규정 온톨로지 - TypeDB 스키마 로더
TypeDB 서버에 스키마를 정의하고 샘플 데이터를 삽입합니다.
"""

from typedb.driver import TransactionType

from .config import TypeDBConfig
from .connection import get_driver

config = TypeDBConfig()


def create_database(driver):
    """데이터베이스 생성 (이미 존재하면 삭제 후 재생성)"""
    if driver.databases.contains(config.database):
        print(f"  기존 데이터베이스 '{config.database}' 삭제...")
        driver.databases.get(config.database).delete()
    driver.databases.create(config.database)
    print(f"  데이터베이스 '{config.database}' 생성 완료")


def load_schema(driver):
    """TypeQL 스키마 파일 로드"""
    print(f"  스키마 파일: {config.schema_file}")

    with open(config.schema_file, "r", encoding="utf-8") as f:
        schema_query = f.read()

    tx = driver.transaction(config.database, TransactionType.SCHEMA)
    tx.query(schema_query).resolve()
    tx.commit()
    print("  스키마 로드 완료")


def insert_sample_data(driver):
    """샘플 데이터 삽입"""
    tx = driver.transaction(config.database, TransactionType.WRITE)

    # --- 규정 ---
    tx.query("""
                insert
                $reg isa 규정,
                    has 규정번호 "BOK-COMP-001",
                    has 규정명 "한국은행 보수규정",
                    has 규정설명 "한국은행 직원의 보수에 관한 사항을 규정",
                    has 시행일 2024-01-01T00:00:00,
                    has 활성여부 true;
            """).resolve()

    # --- 조문 (주요 조항) ---
    tx.query("""
                insert
                $art1 isa 조문,
                    has 조번호 1,
                    has 조문내용 "이 규정은 한국은행 직원의 보수에 관한 사항을 규정함을 목적으로 한다.";
                $art2 isa 조문,
                    has 조번호 2,
                    has 조문내용 "보수라 함은 기본급과 수당을 합산한 금액을 말한다.";
                $art3 isa 조문,
                    has 조번호 3,
                    has 조문내용 "기본급은 직급별 호봉에 따라 지급한다.";
            """).resolve()

    # --- 직급 ---
    tx.query("""
                insert
                $g1 isa 직급, has 직급코드 "G1", has 직급명 "1급", has 직급서열 1;
                $g2 isa 직급, has 직급코드 "G2", has 직급명 "2급", has 직급서열 2;
                $g3 isa 직급, has 직급코드 "G3", has 직급명 "3급", has 직급서열 3;
                $g4 isa 직급, has 직급코드 "G4", has 직급명 "4급", has 직급서열 4;
                $g5 isa 직급, has 직급코드 "G5", has 직급명 "5급", has 직급서열 5;
            """).resolve()

    # --- 직위 ---
    tx.query("""
                insert
                $t1 isa 직위, has 직위코드 "T01", has 직위명 "부총재", has 직위서열 1;
                $t2 isa 직위, has 직위코드 "T02", has 직위명 "부총재보", has 직위서열 2;
                $t3 isa 직위, has 직위코드 "T03", has 직위명 "국장", has 직위서열 3;
                $t4 isa 직위, has 직위코드 "T04", has 직위명 "부장", has 직위서열 4;
                $t5 isa 직위, has 직위코드 "T05", has 직위명 "차장", has 직위서열 5;
                $t6 isa 직위, has 직위코드 "T06", has 직위명 "과장", has 직위서열 6;
                $t7 isa 직위, has 직위코드 "T07", has 직위명 "대리", has 직위서열 7;
                $t8 isa 직위, has 직위코드 "T08", has 직위명 "주임", has 직위서열 8;
            """).resolve()

    # --- 수당 유형 ---
    tx.query("""
                insert
                $a1 isa 수당,
                    has 수당코드 "A001", has 수당명 "직무수당", has 수당유형 "정액",
                    has 수당설명 "직무의 곤란도와 책임도에 따라 지급", has 지급조건 "직무등급에 따름";
                $a2 isa 수당,
                    has 수당코드 "A002", has 수당명 "가족수당", has 수당유형 "정액",
                    has 수당설명 "부양가족 수에 따라 지급", has 지급조건 "부양가족 등록";
                $a3 isa 수당,
                    has 수당코드 "A003", has 수당명 "시간외근무수당", has 수당유형 "비율",
                    has 수당설명 "정규 근무시간 초과 근무에 대한 수당", has 수당지급률 1.5;
                $a4 isa 수당,
                    has 수당코드 "A004", has 수당명 "특별근무수당", has 수당유형 "정액",
                    has 수당설명 "휴일 또는 야간 근무에 대한 수당";
                $a5 isa 수당,
                    has 수당코드 "A005", has 수당명 "정근수당", has 수당유형 "비율",
                    has 수당설명 "근속연수에 따라 지급하는 수당", has 수당지급률 0.5;
            """).resolve()

    # --- 호봉 (3급 기준 샘플) ---
    tx.query("""
                insert
                $h1 isa 호봉, has 호봉번호 1, has 호봉금액 3200000.0,
                    has 호봉적용시작일 2024-01-01T00:00:00;
                $h2 isa 호봉, has 호봉번호 2, has 호봉금액 3400000.0,
                    has 호봉적용시작일 2024-01-01T00:00:00;
                $h3 isa 호봉, has 호봉번호 3, has 호봉금액 3600000.0,
                    has 호봉적용시작일 2024-01-01T00:00:00;
                $h4 isa 호봉, has 호봉번호 4, has 호봉금액 3800000.0,
                    has 호봉적용시작일 2024-01-01T00:00:00;
                $h5 isa 호봉, has 호봉번호 5, has 호봉금액 4000000.0,
                    has 호봉적용시작일 2024-01-01T00:00:00;
            """).resolve()

    tx.commit()
    print("  샘플 데이터 삽입 완료")


def main():
    print("=" * 60)
    print("한국은행 보수규정 온톨로지 - TypeDB 로더")
    print("=" * 60)
    print(f"\n[1] TypeDB 연결: {config.address}")

    driver = get_driver(config)
    try:
        print("[2] 데이터베이스 생성")
        create_database(driver)

        print("[3] 스키마 로드")
        load_schema(driver)

        print("[4] 샘플 데이터 삽입")
        insert_sample_data(driver)
    finally:
        driver.close()

    print("\n✅ 모든 작업이 완료되었습니다.")
    print(f"   데이터베이스: {config.database}")
    print(f"   TypeDB Studio에서 '{config.database}' 데이터베이스를 열어 확인하세요.")


if __name__ == "__main__":
    main()
