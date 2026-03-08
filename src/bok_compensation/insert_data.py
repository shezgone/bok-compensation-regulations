"""
한국은행 보수규정 - 문서 기반 데이터 삽입 (v2)
보수규정 전문(20250213).pdf 기반 — 전면 개정 스키마 대응
"""

from typedb.driver import TransactionType
from .config import TypeDBConfig
from .connection import get_driver


# ============================================================
# 별표1 본봉표 데이터 (단위: 천원)
# ============================================================
SALARY_TABLE = {
    "3급": {
        "start": 21,
        "amounts": [
            3188, 3300, 3642, 3752, 3869, 3984, 4102, 4419, 4530, 4654,
            4763, 5006, 5187, 5312, 5430, 5555, 5690, 5821, 5925, 6032,
            6142, 6229, 6316, 6399, 6495, 6583, 6657, 6738, 6812, 6890,
        ],
    },
    "4급": {
        "start": 16,
        "amounts": [
            2343, 2642, 2754, 2867, 2980, 3093, 3204, 3542, 3662, 3780,
            3893, 4095, 4417, 4529, 4650, 4762, 4882, 5057, 5183, 5300,
            5421, 5539, 5669, 5778, 5889, 5992, 6082, 6170, 6257, 6340,
            6428, 6499, 6576, 6657, 6733,
        ],
    },
    "5급": {
        "start": 1,
        "amounts": [
            579, 651, 715, 787, 862, 936, 1011, 1096, 1181, 1265,
            1554, 1689, 1837, 1977, 2127, 2307, 2579, 2753, 2858, 2973,
            3081, 3196, 3535, 3658, 3770, 3889, 4002, 4323, 4440, 4549,
            4669, 4780, 4962, 5089, 5209, 5326, 5448, 5574, 5678, 5788,
            5894, 5983, 6063, 6153, 6236, 6327, 6400, 6476, 6555, 6635,
        ],
    },
    "6급": {
        "start": 1,
        "amounts": [
            559, 620, 675, 743, 805, 871, 944, 1000, 1045, 1090,
            1509, 1591, 1672, 1757, 1835, 2106, 2196, 2286, 2372, 2462,
            2640, 2730, 2818, 2909, 2999, 3175, 3267, 3353, 3440, 3523,
            3610, 3695, 3782, 3867, 3953, 4035, 4123, 4207, 4290, 4372,
            4451, 4537, 4615, 4699, 4781, 4849, 4914, 4982, 5052, 5122,
        ],
    },
    # ── 별표1의 3. 일반사무직원 본봉표 (단위: 천원) ──
    "GA": {
        "start": 1,
        "amounts": [
            531, 589, 641, 706, 765, 827, 897, 950, 993, 1036,
            1434, 1511, 1588, 1669, 1743, 2001, 2086, 2172, 2253, 2339,
            2508, 2594, 2677, 2763, 2849, 3016, 3104, 3185, 3268, 3347,
        ],
    },
    # ── 별표1의 4. 서무직원 본봉표 (단위: 천원) ──
    "CL": {
        "start": 1,
        "amounts": [
            475, 527, 574, 631, 684, 740, 802, 850, 888, 927,
            1283, 1352, 1421, 1493, 1560, 1790, 1867, 1943, 2016, 2093,
            2244, 2321, 2395, 2473, 2549,
        ],
    },
    # ── 별표1의 4. 청원경찰 본봉표 (서무직원과 동일, 단위: 천원) ──
    "PO": {
        "start": 1,
        "amounts": [
            475, 527, 574, 631, 684, 740, 802, 850, 888, 927,
            1283, 1352, 1421, 1493, 1560, 1790, 1867, 1943, 2016, 2093,
            2244, 2321, 2395, 2473, 2549,
        ],
    },
}

# ============================================================
# 별표1-1 직책급표 (종합기획직원, 단위: 천원/연간)
# (직위코드, 직급코드) → 연간 직책급액
# ============================================================
POSITION_PAY_TABLE = [
    # 부서장(가)
    ("P01", "1급", 18192), ("P01", "2급", 16236),
    # 부서장(나)
    ("P02", "1급", 15792), ("P02", "2급", 13836),
    # 국소속실장
    ("P03", "1급", 7692), ("P03", "2급", 5736),
    # 부장
    ("P04", "2급", 4824), ("P04", "3급", 2868),
    # 팀장
    ("P05", "3급", 1956), ("P05", "4급", 0),
    # 조사역
    ("P07", "2급", 3012), ("P07", "3급", 1056),
    # 주임조사역(C1)
    ("P08", "3급", 1956), ("P08", "4급", 0),
    # 조사역(C2)
    ("P09", "4급", 1044), ("P09", "5급", 0),
    # 조사역(C3)
    ("P10", "5급", 1044), ("P10", "6급", 0),
]

# ============================================================
# 별표7 연봉제본봉 차등액표 (단위: 천원/월)
# (직급코드, 평가등급) → 차등액
# ============================================================
SALARY_DIFF_TABLE = [
    ("1급", "EX", 3672), ("1급", "EE", 2448), ("1급", "ME", 1224), ("1급", "BE", 0),
    ("2급", "EX", 3348), ("2급", "EE", 2232), ("2급", "ME", 1116), ("2급", "BE", 0),
    ("3급", "EX", 3024), ("3급", "EE", 2016), ("3급", "ME", 1008), ("3급", "BE", 0),
]

# ============================================================
# 별표8 연봉제본봉 상한액표 (단위: 천원/월)
# ============================================================
SALARY_CAP_TABLE = [
    ("1급", 85728),
    ("2급", 78540),
    ("3급", 77724),
]

# ============================================================
# 별표9 임금피크제 기본급지급률
# ============================================================
WAGE_PEAK_TABLE = [
    (1, 0.9),   # 1년차 90%
    (2, 0.8),   # 2년차 80%
    (3, 0.7),   # 3년차 70%
]

# ============================================================
# 별표1-5 해외직원 국외본봉 (종합기획직원, 단위: 현지통화/월)
# ============================================================
OVERSEAS_SALARY = [
    ("US", "미국", "1급", 10780.0, "USD"),
    ("US", "미국", "2급", 9760.0, "USD"),
    ("US", "미국", "3급", 8620.0, "USD"),
    ("DE", "독일", "1급", 9100.0, "EUR"),
    ("DE", "독일", "2급", 8240.0, "EUR"),
    ("DE", "독일", "3급", 7280.0, "EUR"),
    ("JP", "일본", "1급", 1210000.0, "JPY"),
    ("JP", "일본", "2급", 1097000.0, "JPY"),
    ("JP", "일본", "3급", 969000.0, "JPY"),
    ("GB", "영국", "1급", 7930.0, "GBP"),
    ("GB", "영국", "2급", 7180.0, "GBP"),
    ("GB", "영국", "3급", 6350.0, "GBP"),
    ("HK", "홍콩", "1급", 83100.0, "HKD"),
    ("HK", "홍콩", "2급", 75250.0, "HKD"),
    ("CN", "중국", "1급", 64720.0, "CNY"),
    ("CN", "중국", "2급", 58630.0, "CNY"),
]

# ============================================================
# 별표1-2 평가상여금 지급률표 (직책구분, 평가등급 → 지급률%)
# ============================================================
BONUS_RATE_TABLE = [
    ("P01", "EX", 1.0), ("P01", "EE", 0.85), ("P01", "ME", 0.70), ("P01", "BE", 0.0),
    ("P02", "EX", 1.0), ("P02", "EE", 0.85), ("P02", "ME", 0.70), ("P02", "BE", 0.0),
    ("P05", "EX", 0.85), ("P05", "EE", 0.70), ("P05", "ME", 0.55), ("P05", "BE", 0.0),
    ("P08", "EX", 0.70), ("P08", "EE", 0.55), ("P08", "ME", 0.40), ("P08", "BE", 0.0),
    ("P09", "EX", 0.60), ("P09", "EE", 0.45), ("P09", "ME", 0.30), ("P09", "BE", 0.0),
    ("P10", "EX", 0.60), ("P10", "EE", 0.45), ("P10", "ME", 0.30), ("P10", "BE", 0.0),
]


def run_query(driver, db, query):
    """Write 트랜잭션 실행 후 커밋"""
    tx = driver.transaction(db, TransactionType.WRITE)
    tx.query(query).resolve()
    tx.commit()


# ────────────────────────────────────────────────────────────
# 삽입 함수들
# ────────────────────────────────────────────────────────────

def insert_regulation(driver, db):
    """규정 본체"""
    run_query(driver, db, """
        insert $reg isa 규정,
            has 규정번호 "BOK-COMP-2025",
            has 규정명 "보수규정",
            has 규정설명 "한국은행법과 한국은행정관에 따라 금융통화위원회 위원, 집행간부, 감사 및 직원의 보수 및 상여금에 관한 사항을 규정",
            has 시행일 1998-04-16T00:00:00,
            has 활성여부 true;
    """)


def insert_amendment_history(driver, db):
    """개정이력 (주요 개정일 + 규정개정 관계)"""
    amendments = [
        ("1998-04-16", "보수규정 제정"),
        ("2000-01-01", "보수규정 개정"),
        ("2005-01-01", "보수규정 개정"),
        ("2010-01-01", "보수규정 개정"),
        ("2015-01-01", "보수규정 개정"),
        ("2019-01-01", "보수규정 개정 (직책급표 반영)"),
        ("2023-01-01", "보수규정 개정"),
        ("2024-01-18", "보수규정 개정"),
        ("2025-02-13", "보수규정 최종 개정 (현행)"),
    ]
    for date_str, desc in amendments:
        desc_esc = desc.replace('"', '\\"')
        run_query(driver, db, f"""
            match $reg isa 규정, has 규정번호 "BOK-COMP-2025";
            insert
                $h isa 개정이력,
                    has 개정일 {date_str}T00:00:00,
                    has 개정이력설명 "{desc_esc}";
                (대상규정: $reg, 이력: $h) isa 규정개정;
        """)


def insert_articles(driver, db):
    """조문 (제1조~제15조)"""
    articles = [
        (1, None, "(목적) 이 규정은 한국은행법과 한국은행정관에 따라 금융통화위원회 위원, 집행간부, 감사 및 직원의 보수 및 상여금에 관한 사항을 규정함을 목적으로 한다."),
        (2, None, "(정의) 보수란 위원·집행간부·감사에 대하여는 기본급을 말하며, 직원에 대하여는 기본급 및 제수당을 말한다. 기본급이란 본봉과 직책급을 말한다. 제수당이란 국내직원의 경우 업무수당 및 시간외근무수당을 말하며, 해외직원의 경우에는 조정수당을 말한다."),
        (3, None, "(보수계산기간) 보수는 월급 또는 연봉으로 한다. 다만, 필요한 경우에는 일급으로 할 수 있다."),
        (4, None, "(본봉) 위원, 집행간부, 감사의 본봉은 별표1의 1.로 한다. 직원의 본봉은 직급 및 호봉에 따라 결정되는 별표1의 2.부터 5.의 본봉, 성과평가결과를 기준으로 결정되는 연봉제본봉 및 잔여근무기간을 기준으로 결정되는 임금피크제본봉으로 한다."),
        (4, 2, "(연봉제본봉) 연봉제본봉은 직전 연봉제본봉에 별표7의 평가등급별 차등액을 합한 금액으로 하되, 평가등급은 매년 1회 산출된 성과평가결과를 기준으로 정한다."),
        (4, 3, "(임금피크제본봉) 임금피크제본봉은 적용 직전 월말일 현재의 본봉에 별표9의 임금피크제 적용연차별 기본급지급률을 곱한 금액으로 한다."),
        (4, 4, "(직책급) 직원에 대한 직책급은 직책 및 직급에 따라 결정되는 별표1-1의 직책급과 잔여근무기간을 기준으로 결정되는 임금피크제직책급으로 한다."),
        (5, None, "(승급) 1개 호봉간의 승급에 필요한 최저근무기간은 1년을 원칙으로 한다. 승급의 제한 또는 조정은 총재가 정한다."),
        (6, None, "(초임호봉 및 연봉제본봉) 신규채용자의 초임호봉은 별표2와 같다. 다만, 총재는 학력이나 경력 또는 자격을 고려하여 초임호봉을 조정할 수 있다."),
        (7, None, "(업무수당) 종사업무별로 해당 업무 또는 기술분야에 직접 종사하는 직원에 대하여는 별표3의 업무수당을 지급한다. 다만, 장기근속자에 대하여는 가산 지급할 수 있다."),
        (9, None, "(시간외근무수당) 은행업무와 관련하여 시간외근무에 대해서는 동 근무 매시간에 대하여 시간당 보수의 1.5배에 해당하는 금액을 지급한다. 시간당 보수는 통상임금 월지급액의 209분의 1로 한다."),
        (11, None, "(조정수당) 해외직원이 국내외에서 납부하는 소득세가 국내 근무 시 납세액을 초과할 때에는 그 초과분의 범위에서 총재가 정하는 바에 따라 조정수당을 지급할 수 있다."),
        (12, None, "(상여금의 지급) 위원, 집행간부, 감사 및 직원에 대하여 상여금을 지급한다. 직원에 대한 상여금은 정기상여금 및 평가상여금으로 구분하고, 지급기준일 현재의 기본급에 지급률을 곱한 금액을 지급한다."),
        (12, 2, "(상여금 지급률) 정기상여금은 연간지급률 380%로서 6월, 12월의 초일을 지급기준일로 하여 각각 150%, 설·추석 연휴시작일의 2영업일 전일을 지급기준일로 하여 각각 40%를 지급한다."),
        (12, 3, "(평가상여금) 평가상여금은 직전년도 성과평가결과에 의한 평가등급에 따라 별표1-2의 지급률을 기본급에 곱한 금액을 지급한다."),
        (13, None, "(비밀유지) 직원은 자신의 보수를 다른 직원에게 알려주거나 다른 직원의 보수를 알려는 행위를 하여서는 아니 된다."),
        (14, None, "(일반기능직원등의 보수) 일반기능직원, 전문직원 및 종합기획직원 중 기한부 고용계약자에 대하여는 제2장 보수 및 제3장 상여금에 관한 규정을 적용하지 아니한다."),
        (15, None, "(위임) 파견자, 휴직자, 휴가자, 전근자, 해외현지채용직원 및 인사경영국 소속직원의 보수 등에 관한 사항 및 이 규정 시행에 필요한 세부사항은 총재가 정한다."),
    ]
    for jo, hang, content in articles:
        c = content.replace('"', '\\"')
        if hang is not None:
            run_query(driver, db, f'insert $a isa 조문, has 조번호 {jo}, has 항번호 {hang}, has 조문내용 "{c}";')
        else:
            run_query(driver, db, f'insert $a isa 조문, has 조번호 {jo}, has 조문내용 "{c}";')


def insert_article_relations(driver, db):
    """규정-조문 관계"""
    run_query(driver, db, """
        match
            $reg isa 규정, has 규정번호 "BOK-COMP-2025";
            $a isa 조문;
        insert (상위규정: $reg, 하위조문: $a) isa 규정구성;
    """)


def insert_career_tracks(driver, db):
    """직렬 (NEW)"""
    run_query(driver, db, """
        insert
        $ct1 isa 직렬, has 직렬코드 "CT-GP", has 직렬명 "종합기획직원",
            has 직렬설명 "1급~6급 및 G1~G5 적용";
        $ct2 isa 직렬, has 직렬코드 "CT-GA", has 직렬명 "일반사무직원",
            has 직렬설명 "별표1의 3. 일반사무직원 본봉표 적용";
        $ct3 isa 직렬, has 직렬코드 "CT-SP", has 직렬명 "별정직원",
            has 직렬설명 "별도 보수체계 적용";
        $ct4 isa 직렬, has 직렬코드 "CT-CL", has 직렬명 "서무직원",
            has 직렬설명 "별표1의 4. 서무직원 본봉표 적용";
        $ct5 isa 직렬, has 직렬코드 "CT-PO", has 직렬명 "청원경찰",
            has 직렬설명 "별표1의 4. 청원경찰 본봉표 적용";
    """)


def insert_grades(driver, db):
    """직급 + 직렬분류 관계"""
    # 종합기획 직급 (1~6급, G1~G5)
    run_query(driver, db, """
        insert
        $g1 isa 직급, has 직급코드 "1급", has 직급명 "1급", has 서열 1;
        $g2 isa 직급, has 직급코드 "2급", has 직급명 "2급", has 서열 2;
        $g3 isa 직급, has 직급코드 "3급", has 직급명 "3급", has 서열 3;
        $g4 isa 직급, has 직급코드 "4급", has 직급명 "4급", has 서열 4;
        $g5 isa 직급, has 직급코드 "5급", has 직급명 "5급", has 서열 5;
        $g6 isa 직급, has 직급코드 "6급", has 직급명 "6급", has 서열 6;
        $gg1 isa 직급, has 직급코드 "G1", has 직급명 "G1", has 서열 7;
        $gg2 isa 직급, has 직급코드 "G2", has 직급명 "G2", has 서열 8;
        $gg3 isa 직급, has 직급코드 "G3", has 직급명 "G3", has 서열 9;
        $gg4 isa 직급, has 직급코드 "G4", has 직급명 "G4", has 서열 10;
        $gg5 isa 직급, has 직급코드 "G5", has 직급명 "G5", has 서열 11;
    """)
    # 일반사무 / 서무 / 청원경찰용 대표 직급
    run_query(driver, db, """
        insert
        $ga isa 직급, has 직급코드 "GA", has 직급명 "일반사무", has 서열 12;
        $cl isa 직급, has 직급코드 "CL", has 직급명 "서무", has 서열 13;
        $po isa 직급, has 직급코드 "PO", has 직급명 "청원경찰", has 서열 14;
    """)
    # 직렬분류 관계: 종합기획 ↔ 1~6급, G1~G5
    for code in ["1급", "2급", "3급", "4급", "5급", "6급",
                 "G1", "G2", "G3", "G4", "G5"]:
        run_query(driver, db, f"""
            match
                $ct isa 직렬, has 직렬코드 "CT-GP";
                $g isa 직급, has 직급코드 "{code}";
            insert (분류직렬: $ct, 분류직급: $g) isa 직렬분류;
        """)
    # 일반사무 ↔ GA, 서무 ↔ CL, 청원경찰 ↔ PO
    for ct_code, g_code in [("CT-GA", "GA"), ("CT-CL", "CL"), ("CT-PO", "PO")]:
        run_query(driver, db, f"""
            match
                $ct isa 직렬, has 직렬코드 "{ct_code}";
                $g isa 직급, has 직급코드 "{g_code}";
            insert (분류직렬: $ct, 분류직급: $g) isa 직렬분류;
        """)


def insert_positions(driver, db):
    """직위"""
    run_query(driver, db, """
        insert
        $t1 isa 직위, has 직위코드 "P01", has 직위명 "부서장(가)", has 서열 1;
        $t2 isa 직위, has 직위코드 "P02", has 직위명 "부서장(나)", has 서열 2;
        $t3 isa 직위, has 직위코드 "P03", has 직위명 "국소속실장", has 서열 3;
        $t4 isa 직위, has 직위코드 "P04", has 직위명 "부장", has 서열 4;
        $t5 isa 직위, has 직위코드 "P05", has 직위명 "팀장", has 서열 5;
        $t6 isa 직위, has 직위코드 "P06", has 직위명 "반장", has 서열 6;
        $t7 isa 직위, has 직위코드 "P07", has 직위명 "조사역", has 서열 7;
        $t8 isa 직위, has 직위코드 "P08", has 직위명 "주임조사역(C1)", has 서열 8;
        $t9 isa 직위, has 직위코드 "P09", has 직위명 "조사역(C2)", has 서열 9;
        $t10 isa 직위, has 직위코드 "P10", has 직위명 "조사역(C3)", has 서열 10;
    """)


def insert_salary_table(driver, db):
    """별표1 본봉표 — 호봉 + 호봉체계구성"""
    for grade_code, data in SALARY_TABLE.items():
        start = data["start"]
        for idx, amount_1000 in enumerate(data["amounts"]):
            hobong = start + idx
            amount = float(amount_1000 * 1000)
            run_query(driver, db, f"""
                match $g isa 직급, has 직급코드 "{grade_code}";
                insert
                    $h isa 호봉,
                        has 호봉번호 {hobong},
                        has 호봉금액 {amount},
                        has 적용시작일 2025-01-01T00:00:00;
                    (소속직급: $g, 구성호봉: $h) isa 호봉체계구성;
            """)


def insert_position_pay(driver, db):
    """별표1-1 직책급표 (NEW) — 직책급기준 + 직책급결정 관계"""
    for pos_code, grade_code, amount_1000 in POSITION_PAY_TABLE:
        code = f"PP-{pos_code}-{grade_code}"
        amount = float(amount_1000 * 1000)
        run_query(driver, db, f"""
            match
                $pos isa 직위, has 직위코드 "{pos_code}";
                $g isa 직급, has 직급코드 "{grade_code}";
            insert
                $pp isa 직책급기준, has 직책급코드 "{code}",
                    has 직책급액 {amount},
                    has 적용시작일 2025-01-01T00:00:00,
                    has 직책급기준설명 "별표1-1 종합기획직원 직책급";
                (적용기준: $pp, 해당직급: $g, 해당직위: $pos) isa 직책급결정;
        """)


def insert_allowances(driver, db):
    """수당 (별표3 + 시간외근무수당)"""
    # 출납업무
    run_query(driver, db, """
        insert
        $s1 isa 수당, has 수당코드 "BIZ-CASH-23",
            has 수당명 "출납업무수당(2~3급)", has 수당유형 "정액",
            has 수당액 60000.0,
            has 지급조건 "출납업무 직접 종사 종합기획 2급~3급, G2~G3",
            has 수당설명 "별표3 1.출납업무";
        $s2 isa 수당, has 수당코드 "BIZ-CASH-46",
            has 수당명 "출납업무수당(4~6급)", has 수당유형 "정액",
            has 수당액 70000.0,
            has 지급조건 "출납업무 직접 종사 종합기획 4급~6급, G4~G5, 일반사무직원",
            has 수당설명 "별표3 1.출납업무";
        $s3 isa 수당, has 수당코드 "BIZ-CASH-SM",
            has 수당명 "출납업무수당(서무)", has 수당유형 "정액",
            has 수당액 50000.0,
            has 지급조건 "출납업무 직접 종사 서무직원",
            has 수당설명 "별표3 1.출납업무";
    """)
    # 전산정보업무
    run_query(driver, db, """
        insert
        $s4 isa 수당, has 수당코드 "BIZ-IT-10Y-23",
            has 수당명 "전산정보업무수당(2~3급,10년이상)", has 수당유형 "정액",
            has 수당액 160000.0,
            has 지급조건 "전산정보업무 10년↑ 종합기획 2급~3급",
            has 수당설명 "별표3 2.전산정보업무";
        $s5 isa 수당, has 수당코드 "BIZ-IT-10Y-45",
            has 수당명 "전산정보업무수당(4~5급,10년이상)", has 수당유형 "정액",
            has 수당액 170000.0,
            has 지급조건 "전산정보업무 10년↑ 종합기획 4급~5급, G4~G5",
            has 수당설명 "별표3 2.전산정보업무";
        $s6 isa 수당, has 수당코드 "BIZ-IT-5Y-23",
            has 수당명 "전산정보업무수당(2~3급,5~10년)", has 수당유형 "정액",
            has 수당액 120000.0,
            has 지급조건 "전산정보업무 5~10년 종합기획 2급~3급",
            has 수당설명 "별표3 2.전산정보업무";
        $s7 isa 수당, has 수당코드 "BIZ-IT-5Y-45",
            has 수당명 "전산정보업무수당(4~5급,5~10년)", has 수당유형 "정액",
            has 수당액 130000.0,
            has 지급조건 "전산정보업무 5~10년 종합기획 4급~5급",
            has 수당설명 "별표3 2.전산정보업무";
    """)
    # 기술업무
    run_query(driver, db, """
        insert
        $s8 isa 수당, has 수당코드 "BIZ-TECH-23",
            has 수당명 "기술업무수당(2~3급)", has 수당유형 "정액",
            has 수당액 90000.0,
            has 지급조건 "기술분야 종사 종합기획 2급~3급, G2~G3",
            has 수당설명 "별표3 3.기술업무";
        $s9 isa 수당, has 수당코드 "BIZ-TECH-45",
            has 수당명 "기술업무수당(4~6급)", has 수당유형 "정액",
            has 수당액 100000.0,
            has 지급조건 "기술분야 종사 종합기획 4급~6급, G4~G5, 일반사무직원",
            has 수당설명 "별표3 3.기술업무";
        $s10 isa 수당, has 수당코드 "BIZ-TECH-SM",
            has 수당명 "기술업무수당(서무)", has 수당유형 "정액",
            has 수당액 60000.0,
            has 지급조건 "기술분야 종사 서무직원",
            has 수당설명 "별표3 3.기술업무";
    """)
    # 조사연구업무
    run_query(driver, db, """
        insert
        $s11 isa 수당, has 수당코드 "BIZ-RES-G2",
            has 수당명 "조사연구업무수당(G2)", has 수당유형 "정액",
            has 수당액 20000.0,
            has 지급조건 "조사연구업무 종사 종합기획 2급, G2",
            has 수당설명 "별표3 4.조사연구업무";
        $s12 isa 수당, has 수당코드 "BIZ-RES-G3",
            has 수당명 "조사연구업무수당(G3)", has 수당유형 "정액",
            has 수당액 30000.0,
            has 지급조건 "조사연구업무 종사 종합기획 3급, G3",
            has 수당설명 "별표3 4.조사연구업무";
        $s13 isa 수당, has 수당코드 "BIZ-RES-G4",
            has 수당명 "조사연구업무수당(G4)", has 수당유형 "정액",
            has 수당액 80000.0,
            has 지급조건 "조사연구업무 종사 종합기획 4급, G4",
            has 수당설명 "별표3 4.조사연구업무";
        $s14 isa 수당, has 수당코드 "BIZ-RES-G5",
            has 수당명 "조사연구업무수당(G5)", has 수당유형 "정액",
            has 수당액 150000.0,
            has 지급조건 "조사연구업무 종사 종합기획 5급, G5",
            has 수당설명 "별표3 4.조사연구업무";
    """)
    # 시간외근무수당
    run_query(driver, db, """
        insert $ot isa 수당, has 수당코드 "OT-WORK",
            has 수당명 "시간외근무수당", has 수당유형 "비율",
            has 지급률 1.5,
            has 지급조건 "시간외근무 시 시간당 보수의 1.5배",
            has 수당설명 "제9조. 시간당보수=통상임금월지급액/209";
    """)


def insert_exec_compensation(driver, db):
    """보수기준 (별표1 1. 위원/집행간부/감사)"""
    run_query(driver, db, """
        insert
        $b1 isa 보수기준, has 보수코드 "EXEC-GOV",
            has 보수기준명 "총재 본봉", has 기본급액 336710000.0,
            has 적용시작일 2025-01-01T00:00:00,
            has 보수기준설명 "별표1 1. 연간총액 - 총재";
        $b2 isa 보수기준, has 보수코드 "EXEC-VICE",
            has 보수기준명 "위원·부총재 본봉", has 기본급액 309770000.0,
            has 적용시작일 2025-01-01T00:00:00,
            has 보수기준설명 "별표1 1. 연간총액 - 위원·부총재";
        $b3 isa 보수기준, has 보수코드 "EXEC-AUDIT",
            has 보수기준명 "감사 본봉", has 기본급액 296310000.0,
            has 적용시작일 2025-01-01T00:00:00,
            has 보수기준설명 "별표1 1. 연간총액 - 감사";
        $b4 isa 보수기준, has 보수코드 "EXEC-SVICE",
            has 보수기준명 "부총재보 본봉", has 기본급액 249190000.0,
            has 적용시작일 2025-01-01T00:00:00,
            has 보수기준설명 "별표1 1. 연간총액 - 부총재보";
    """)


def insert_evaluations(driver, db):
    """평가등급 (별표1-2, 별표1-3, 별표7)"""
    run_query(driver, db, """
        insert
        $e1 isa 평가결과, has 평가등급 "EX", has 평가년도 2025,
            has 승급호봉수 2, has 배분율 0.10;
        $e2 isa 평가결과, has 평가등급 "EE", has 평가년도 2025,
            has 승급호봉수 1, has 배분율 0.25;
        $e3 isa 평가결과, has 평가등급 "ME", has 평가년도 2025,
            has 승급호봉수 1, has 배분율 0.40;
        $e4 isa 평가결과, has 평가등급 "BE", has 평가년도 2025,
            has 승급호봉수 0, has 배분율 0.20;
        $e5 isa 평가결과, has 평가등급 "NI", has 평가년도 2025,
            has 승급호봉수 0, has 배분율 0.05;
    """)


def insert_bonus_standards(driver, db):
    """상여금기준 (NEW: 제12조, 별표1-2) + 상여금결정 관계"""
    # 정기상여금 (단독 엔티티 — 직위/평가 무관)
    run_query(driver, db, """
        insert $b isa 상여금기준, has 상여금코드 "BONUS-REG",
            has 상여유형 "정기", has 상여금기준명 "정기상여금",
            has 연간지급률 3.8,
            has 상여금기준설명 "연간 380%. 6·12월 각 150%, 설·추석 각 40%";
    """)
    # 평가상여금 — 직책구분 × 평가등급별 지급률
    for pos_code, eval_grade, rate in BONUS_RATE_TABLE:
        code = f"BONUS-EVAL-{pos_code}-{eval_grade}"
        run_query(driver, db, f"""
            match
                $pos isa 직위, has 직위코드 "{pos_code}";
                $ev isa 평가결과, has 평가등급 "{eval_grade}";
            insert
                $b isa 상여금기준, has 상여금코드 "{code}",
                    has 상여유형 "평가", has 상여금기준명 "평가상여금",
                    has 지급률 {rate},
                    has 상여금기준설명 "별표1-2 평가상여금지급률표";
                (적용기준: $b, 해당직책구분: $pos, 해당등급: $ev) isa 상여금결정;
        """)


def insert_salary_diff(driver, db):
    """별표7 연봉차등액기준 (NEW) + 연봉차등 관계"""
    for grade_code, eval_grade, diff_1000 in SALARY_DIFF_TABLE:
        code = f"DIFF-{grade_code}-{eval_grade}"
        diff = float(diff_1000 * 1000)
        run_query(driver, db, f"""
            match
                $g isa 직급, has 직급코드 "{grade_code}";
                $ev isa 평가결과, has 평가등급 "{eval_grade}";
            insert
                $d isa 연봉차등액기준, has 연봉차등액코드 "{code}",
                    has 차등액 {diff},
                    has 적용시작일 2025-01-01T00:00:00,
                    has 연봉차등기준설명 "별표7 연봉제본봉 차등액";
                (적용기준: $d, 해당직급: $g, 해당등급: $ev) isa 연봉차등;
        """)


def insert_salary_cap(driver, db):
    """별표8 연봉상한액기준 (NEW) + 연봉상한 관계"""
    for grade_code, cap_1000 in SALARY_CAP_TABLE:
        code = f"CAP-{grade_code}"
        cap = float(cap_1000 * 1000)
        run_query(driver, db, f"""
            match $g isa 직급, has 직급코드 "{grade_code}";
            insert
                $c isa 연봉상한액기준, has 연봉상한액코드 "{code}",
                    has 상한액 {cap},
                    has 적용시작일 2025-01-01T00:00:00,
                    has 연봉상한기준설명 "별표8 연봉제본봉 상한액";
                (적용기준: $c, 해당직급: $g) isa 연봉상한;
        """)


def insert_wage_peak(driver, db):
    """별표9 임금피크제기준 (NEW)"""
    for year, rate in WAGE_PEAK_TABLE:
        code = f"WP-Y{year}"
        run_query(driver, db, f"""
            insert $w isa 임금피크제기준, has 임금피크제코드 "{code}",
                has 적용연차 {year}, has 지급률 {rate},
                has 임금피크제설명 "별표9 임금피크제 적용연차 {year}년차 기본급지급률 {int(rate*100)}%";
        """)


def insert_overseas_salary(driver, db):
    """별표1-5 국외본봉기준 (NEW) + 국외본봉결정 관계"""
    for country_code, country_name, grade_code, amount, currency in OVERSEAS_SALARY:
        code = f"OVS-{country_code}-{grade_code}"
        run_query(driver, db, f"""
            match $g isa 직급, has 직급코드 "{grade_code}";
            insert
                $o isa 국외본봉기준, has 국외본봉코드 "{code}",
                    has 국가코드 "{country_code}",
                    has 국가명 "{country_name}",
                    has 기본급액 {amount},
                    has 통화단위 "{currency}",
                    has 적용시작일 2025-01-01T00:00:00,
                    has 국외본봉기준설명 "별표1-5 해외직원 국외본봉";
                (적용기준: $o, 해당직급: $g) isa 국외본봉결정;
        """)


def insert_starting_step(driver, db):
    """별표2 초임호봉기준 (NEW) + 초임호봉결정 관계"""
    # 별표2 초임호봉표 원본 기준
    starting = [
        ("CT-GP-5", "CT-GP", 11, "종합기획 5급(G5) 초임호봉"),
        ("CT-GP-6", "CT-GP", 6,  "종합기획 6급 초임호봉"),
        ("CT-GA",   "CT-GA", 1,  "일반사무직원 초임호봉"),
        ("CT-SP",   "CT-SP", 4,  "별정직원 초임호봉"),
        ("CT-CL",   "CT-CL", 6,  "서무직원 초임호봉"),
        ("CT-PO",   "CT-PO", 6,  "청원경찰 초임호봉"),
    ]
    for st_code, ct_code, hobong, desc in starting:
        code = f"START-{st_code}"
        run_query(driver, db, f"""
            match $ct isa 직렬, has 직렬코드 "{ct_code}";
            insert
                $s isa 초임호봉기준, has 초임호봉코드 "{code}",
                    has 초임호봉번호 {hobong},
                    has 초임호봉기준설명 "별표2 {desc}";
                (적용기준: $s, 대상직렬: $ct) isa 초임호봉결정;
        """)


# ────────────────────────────────────────────────────────────
# 검증 & 메인
# ────────────────────────────────────────────────────────────

def verify_data(driver, db):
    """삽입 결과 검증"""
    checks = [
        ("규정",         "match $x isa 규정;"),
        ("조문",         "match $x isa 조문;"),
        ("개정이력",     "match $x isa 개정이력;"),
        ("직렬",         "match $x isa 직렬;"),
        ("직급",         "match $x isa 직급;"),
        ("직위",         "match $x isa 직위;"),
        ("호봉",         "match $x isa 호봉;"),
        ("수당",         "match $x isa 수당;"),
        ("보수기준",     "match $x isa 보수기준;"),
        ("직책급기준",   "match $x isa 직책급기준;"),
        ("상여금기준",   "match $x isa 상여금기준;"),
        ("연봉차등액기준", "match $x isa 연봉차등액기준;"),
        ("연봉상한액기준", "match $x isa 연봉상한액기준;"),
        ("임금피크제기준", "match $x isa 임금피크제기준;"),
        ("국외본봉기준",  "match $x isa 국외본봉기준;"),
        ("초임호봉기준",  "match $x isa 초임호봉기준;"),
        ("평가결과",     "match $x isa 평가결과;"),
        ("---------",   ""),
        ("규정구성",     "match $r isa 규정구성;"),
        ("규정개정",     "match $r isa 규정개정;"),
        ("직렬분류",     "match $r isa 직렬분류;"),
        ("호봉체계구성", "match $r isa 호봉체계구성;"),
        ("직책급결정",   "match $r isa 직책급결정;"),
        ("상여금결정",   "match $r isa 상여금결정;"),
        ("연봉차등",     "match $r isa 연봉차등;"),
        ("연봉상한",     "match $r isa 연봉상한;"),
        ("국외본봉결정", "match $r isa 국외본봉결정;"),
        ("초임호봉결정", "match $r isa 초임호봉결정;"),
    ]
    for label, q in checks:
        if not q:
            print(f"  {label}")
            continue
        tx = driver.transaction(db, TransactionType.READ)
        count = len(list(tx.query(q).resolve()))
        print(f"  {label}: {count}건")
        tx.close()


def main():
    config = TypeDBConfig()
    driver = get_driver(config)
    db = config.database

    print("=" * 60)
    print("한국은행 보수규정 — 데이터 삽입 (v2: 전면 개정 스키마)")
    print("=" * 60)

    # DB 재생성
    if driver.databases.contains(db):
        print(f"\n기존 '{db}' 삭제 후 재생성...")
        driver.databases.get(db).delete()
    driver.databases.create(db)

    # 스키마 로드
    import os
    schema_path = os.path.abspath(config.schema_file)
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_query = f.read()
    tx = driver.transaction(db, TransactionType.SCHEMA)
    tx.query(schema_query).resolve()
    tx.commit()
    print("스키마 로드 완료\n")

    # 데이터 삽입
    steps = [
        ("규정 본체",                    insert_regulation),
        ("개정이력 (규정개정 관계)",      insert_amendment_history),
        ("조문 (제1조~제15조)",          insert_articles),
        ("규정-조문 관계",               insert_article_relations),
        ("직렬 (5개 직렬)",              insert_career_tracks),
        ("직급 + 직렬분류",              insert_grades),
        ("직위/직책",                    insert_positions),
        ("호봉 본봉표 (별표1)",          insert_salary_table),
        ("직책급 (별표1-1)",             insert_position_pay),
        ("수당 (별표3 + 시간외)",        insert_allowances),
        ("보수기준 (위원/집행간부/감사)", insert_exec_compensation),
        ("평가등급 + 배분율",            insert_evaluations),
        ("상여금기준 (별표1-2)",          insert_bonus_standards),
        ("연봉차등액 (별표7)",           insert_salary_diff),
        ("연봉상한액 (별표8)",           insert_salary_cap),
        ("임금피크제 (별표9)",           insert_wage_peak),
        ("국외본봉 (별표1-5)",           insert_overseas_salary),
        ("초임호봉 (별표2)",             insert_starting_step),
    ]

    for i, (name, func) in enumerate(steps, 1):
        print(f"  [{i:2d}/{len(steps)}] {name}...")
        func(driver, db)

    # 검증
    print("\n--- 삽입 결과 검증 ---")
    verify_data(driver, db)

    driver.close()
    print("\n완료!")


if __name__ == "__main__":
    main()
