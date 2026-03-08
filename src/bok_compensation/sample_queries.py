"""
한국은행 보수규정 온톨로지 - 샘플 쿼리
스키마 로드 후 TypeDB에서 데이터를 조회하는 예시 쿼리 모음
"""

from typedb.driver import TransactionType

from .config import TypeDBConfig
from .connection import get_driver

config = TypeDBConfig()


def run_query(driver, title, query):
    """쿼리 실행 및 결과 출력"""
    print(f"\n{'─' * 50}")
    print(f"📋 {title}")
    print(f"{'─' * 50}")
    print(f"Query: {query.strip()}\n")

    tx = driver.transaction(config.database, TransactionType.READ)
    try:
        results = list(tx.query(query).resolve())
        if results:
            for i, result in enumerate(results, 1):
                print(f"  [{i}] {result}")
        else:
            print("  (결과 없음)")
    finally:
        tx.close()
    return results


def main():
    print("=" * 60)
    print("한국은행 보수규정 온톨로지 - 샘플 쿼리")
    print("=" * 60)

    driver = get_driver(config)
    try:

        # 1. 전체 직급 조회
        run_query(driver, "전체 직급 목록", """
                match $g isa 직급, has 직급명 $name, has 직급서열 $order;
                sort $order asc;
            """)

        # 2. 전체 직위 조회
        run_query(driver, "전체 직위 목록", """
                match $t isa 직위, has 직위명 $name, has 직위서열 $order;
                sort $order asc;
            """)

        # 3. 수당 유형별 조회
        run_query(driver, "수당 목록", """
                match $a isa 수당, has 수당명 $name, has 수당유형 $type;
                $a has 수당설명 $desc;
            """)

        # 4. 호봉 금액 조회
        run_query(driver, "호봉별 금액", """
                match $h isa 호봉, has 호봉번호 $num, has 호봉금액 $amount;
                sort $num asc;
            """)

        # 5. 규정 조문 조회
        run_query(driver, "규정 조문", """
                match $a isa 조문, has 조번호 $num, has 조문내용 $content;
                sort $num asc;
            """)
    finally:
        driver.close()

    print(f"\n{'=' * 60}")
    print("쿼리 실행 완료")


if __name__ == "__main__":
    main()
