"""
한국은행 보수규정 온톨로지 - TypeDB 스키마 로더
TypeDB 서버에 스키마를 정의하고 샘플 데이터를 삽입합니다.
"""

from typedb.driver import TypeDB, SessionType, TransactionType
import os

# ============================================================
# 설정
# ============================================================
TYPEDB_ADDRESS = os.getenv("TYPEDB_ADDRESS", "localhost:1729")
DATABASE_NAME = os.getenv("TYPEDB_DATABASE", "bok-compensation")
SCHEMA_FILE = os.path.join(os.path.dirname(__file__), "..", "schema", "compensation_regulation.tql")


def create_database(driver):
    """데이터베이스 생성 (이미 존재하면 삭제 후 재생성)"""
    if driver.databases.contains(DATABASE_NAME):
        print(f"  기존 데이터베이스 '{DATABASE_NAME}' 삭제...")
        driver.databases.get(DATABASE_NAME).delete()
    driver.databases.create(DATABASE_NAME)
    print(f"  데이터베이스 '{DATABASE_NAME}' 생성 완료")


def load_schema(driver):
    """TypeQL 스키마 파일 로드"""
    schema_path = os.path.abspath(SCHEMA_FILE)
    print(f"  스키마 파일: {schema_path}")

    with open(schema_path, "r", encoding="utf-8") as f:
        schema_query = f.read()

    with driver.session(DATABASE_NAME, SessionType.SCHEMA) as session:
        with session.transaction(TransactionType.WRITE) as tx:
            tx.query.define(schema_query)
            tx.commit()
    print("  스키마 로드 완료")


def insert_sample_data(driver):
    """샘플 데이터 삽입"""
    with driver.session(DATABASE_NAME, SessionType.DATA) as session:
        with session.transaction(TransactionType.WRITE) as tx:

            # --- 규정 ---
            tx.query.insert("""
                insert
                $reg isa 규정,
                    has 규정번호 "BOK-COMP-001",
                    has 명칭 "한국은행 보수규정",
                    has 설명 "한국은행 직원의 보수에 관한 사항을 규정",
                    has 시행일 2024-01-01T00:00:00,
                    has 활성여부 true;
            """)

            # --- 조문 (주요 조항) ---
            tx.query.insert("""
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
            """)

            # --- 직급 ---
            tx.query.insert("""
                insert
                $g1 isa 직급, has 직급코드 "G1", has 직급명 "1급", has 서열 1;
                $g2 isa 직급, has 직급코드 "G2", has 직급명 "2급", has 서열 2;
                $g3 isa 직급, has 직급코드 "G3", has 직급명 "3급", has 서열 3;
                $g4 isa 직급, has 직급코드 "G4", has 직급명 "4급", has 서열 4;
                $g5 isa 직급, has 직급코드 "G5", has 직급명 "5급", has 서열 5;
            """)

            # --- 직위 ---
            tx.query.insert("""
                insert
                $t1 isa 직위, has 직위코드 "T01", has 직위명 "부총재", has 서열 1;
                $t2 isa 직위, has 직위코드 "T02", has 직위명 "부총재보", has 서열 2;
                $t3 isa 직위, has 직위코드 "T03", has 직위명 "국장", has 서열 3;
                $t4 isa 직위, has 직위코드 "T04", has 직위명 "부장", has 서열 4;
                $t5 isa 직위, has 직위코드 "T05", has 직위명 "차장", has 서열 5;
                $t6 isa 직위, has 직위코드 "T06", has 직위명 "과장", has 서열 6;
                $t7 isa 직위, has 직위코드 "T07", has 직위명 "대리", has 서열 7;
                $t8 isa 직위, has 직위코드 "T08", has 직위명 "주임", has 서열 8;
            """)

            # --- 부서 ---
            tx.query.insert("""
                insert
                $d1 isa 부서, has 부서코드 "D001", has 부서명 "통화정책국", has 활성여부 true;
                $d2 isa 부서, has 부서코드 "D002", has 부서명 "금융안정국", has 활성여부 true;
                $d3 isa 부서, has 부서코드 "D003", has 부서명 "경제통계국", has 활성여부 true;
                $d4 isa 부서, has 부서코드 "D004", has 부서명 "인사부", has 활성여부 true;
            """)

            # --- 수당 유형 ---
            tx.query.insert("""
                insert
                $a1 isa 수당,
                    has 수당코드 "A001", has 수당명 "직무수당", has 수당유형 "정액",
                    has 설명 "직무의 곤란도와 책임도에 따라 지급", has 지급조건 "직무등급에 따름";
                $a2 isa 수당,
                    has 수당코드 "A002", has 수당명 "가족수당", has 수당유형 "정액",
                    has 설명 "부양가족 수에 따라 지급", has 지급조건 "부양가족 등록";
                $a3 isa 수당,
                    has 수당코드 "A003", has 수당명 "시간외근무수당", has 수당유형 "비율",
                    has 설명 "정규 근무시간 초과 근무에 대한 수당", has 지급률 1.5;
                $a4 isa 수당,
                    has 수당코드 "A004", has 수당명 "특별근무수당", has 수당유형 "정액",
                    has 설명 "휴일 또는 야간 근무에 대한 수당";
                $a5 isa 수당,
                    has 수당코드 "A005", has 수당명 "정근수당", has 수당유형 "비율",
                    has 설명 "근속연수에 따라 지급하는 수당", has 지급률 0.5;
            """)

            # --- 근무형태 ---
            tx.query.insert("""
                insert
                $w1 isa 근무형태, has 코드 "W01", has 근무형태명 "정규근무", has 근무시간 8.0,
                    has 설명 "09:00~18:00 정규 근무";
                $w2 isa 근무형태, has 코드 "W02", has 근무형태명 "탄력근무", has 근무시간 8.0,
                    has 설명 "출퇴근 시간 자율 조정 (총 8시간)";
                $w3 isa 근무형태, has 코드 "W03", has 근무형태명 "시간선택제", has 근무시간 4.0,
                    has 설명 "일 4시간 단축근무";
            """)

            # --- 호봉 (3급 기준 샘플) ---
            tx.query.insert("""
                insert
                $h1 isa 호봉, has 호봉번호 1, has 호봉금액 3200000.0,
                    has 적용시작일 2024-01-01T00:00:00;
                $h2 isa 호봉, has 호봉번호 2, has 호봉금액 3400000.0,
                    has 적용시작일 2024-01-01T00:00:00;
                $h3 isa 호봉, has 호봉번호 3, has 호봉금액 3600000.0,
                    has 적용시작일 2024-01-01T00:00:00;
                $h4 isa 호봉, has 호봉번호 4, has 호봉금액 3800000.0,
                    has 적용시작일 2024-01-01T00:00:00;
                $h5 isa 호봉, has 호봉번호 5, has 호봉금액 4000000.0,
                    has 적용시작일 2024-01-01T00:00:00;
            """)

            tx.commit()
    print("  샘플 데이터 삽입 완료")


def main():
    print("=" * 60)
    print("한국은행 보수규정 온톨로지 - TypeDB 로더")
    print("=" * 60)
    print(f"\n[1] TypeDB 연결: {TYPEDB_ADDRESS}")

    with TypeDB.core_driver(TYPEDB_ADDRESS) as driver:
        print("[2] 데이터베이스 생성")
        create_database(driver)

        print("[3] 스키마 로드")
        load_schema(driver)

        print("[4] 샘플 데이터 삽입")
        insert_sample_data(driver)

    print("\n✅ 모든 작업이 완료되었습니다.")
    print(f"   데이터베이스: {DATABASE_NAME}")
    print(f"   TypeDB Studio에서 '{DATABASE_NAME}' 데이터베이스를 열어 확인하세요.")


if __name__ == "__main__":
    main()
