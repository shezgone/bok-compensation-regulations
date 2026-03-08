"""
한국은행 보수규정 온톨로지 - 샘플 쿼리
스키마 로드 후 TypeDB에서 데이터를 조회하는 예시 쿼리 모음
"""

from typedb.driver import TypeDB, SessionType, TransactionType
import os

TYPEDB_ADDRESS = os.getenv("TYPEDB_ADDRESS", "localhost:1729")
DATABASE_NAME = os.getenv("TYPEDB_DATABASE", "bok-compensation")


def run_query(session, title, query):
    """쿼리 실행 및 결과 출력"""
    print(f"\n{'─' * 50}")
    print(f"📋 {title}")
    print(f"{'─' * 50}")
    print(f"Query: {query.strip()}\n")

    with session.transaction(TransactionType.READ) as tx:
        results = list(tx.query.fetch(query))
        if results:
            for i, result in enumerate(results, 1):
                print(f"  [{i}] {result}")
        else:
            print("  (결과 없음)")
    return results


def main():
    print("=" * 60)
    print("한국은행 보수규정 온톨로지 - 샘플 쿼리")
    print("=" * 60)

    with TypeDB.core_driver(TYPEDB_ADDRESS) as driver:
        with driver.session(DATABASE_NAME, SessionType.DATA) as session:

            # 1. 전체 직급 조회
            run_query(session, "전체 직급 목록", """
                match $g isa 직급, has 직급명 $name, has 서열 $order;
                fetch $g: 직급명, 서열;
                sort $order asc;
            """)

            # 2. 전체 직위 조회
            run_query(session, "전체 직위 목록", """
                match $t isa 직위, has 직위명 $name, has 서열 $order;
                fetch $t: 직위명, 서열;
                sort $order asc;
            """)

            # 3. 수당 유형별 조회
            run_query(session, "수당 목록", """
                match $a isa 수당, has 수당명 $name, has 수당유형 $type;
                fetch $a: 수당명, 수당유형, 수당설명;
            """)

            # 4. 호봉 금액 조회
            run_query(session, "호봉별 금액", """
                match $h isa 호봉, has 호봉번호 $num, has 호봉금액 $amount;
                fetch $h: 호봉번호, 호봉금액;
                sort $num asc;
            """)

            # 5. 부서 목록
            run_query(session, "부서 목록", """
                match $d isa 부서, has 부서명 $name, has 활성여부 true;
                fetch $d: 부서명, 부서코드;
            """)

            # 6. 규정 조문 조회
            run_query(session, "규정 조문", """
                match $a isa 조문, has 조번호 $num, has 조문내용 $content;
                fetch $a: 조번호, 조문내용;
                sort $num asc;
            """)

            # 7. 근무형태 조회
            run_query(session, "근무형태", """
                match $w isa 근무형태, has 근무형태명 $name;
                fetch $w: 근무형태명, 근무시간, 보수기준설명;
            """)

    print(f"\n{'=' * 60}")
    print("쿼리 실행 완료")


if __name__ == "__main__":
    main()
