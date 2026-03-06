"""
한국은행 보수규정 — Neo4j 데이터 삽입
보수규정 전문(20250213).pdf 기반
TypeDB 구현과 동일한 데이터를 Neo4j 그래프로 적재합니다.

모델링 차이점:
  - TypeDB N-ary 관계 (직책급결정, 상여금결정, 연봉차등)
    → Neo4j: 중간 노드(:직책급기준, :상여금기준, :연봉차등액기준)에서
      각 참여 엔티티로 관계를 연결
  - TypeDB 속성(owns) → Neo4j 프로퍼티
"""

from .config import Neo4jConfig
from .connection import get_driver

# ============================================================
# 데이터 테이블 (TypeDB insert_data.py 와 동일)
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

POSITION_PAY_TABLE = [
    ("P01", "1급", 18192), ("P01", "2급", 16236),
    ("P02", "1급", 15792), ("P02", "2급", 13836),
    ("P03", "1급", 7692), ("P03", "2급", 5736),
    ("P04", "2급", 4824), ("P04", "3급", 2868),
    ("P05", "3급", 1956), ("P05", "4급", 0),
    ("P07", "2급", 3012), ("P07", "3급", 1056),
    ("P08", "3급", 1956), ("P08", "4급", 0),
    ("P09", "4급", 1044), ("P09", "5급", 0),
    ("P10", "5급", 1044), ("P10", "6급", 0),
]

SALARY_DIFF_TABLE = [
    ("1급", "EX", 3672), ("1급", "EE", 2448), ("1급", "ME", 1224), ("1급", "BE", 0),
    ("2급", "EX", 3348), ("2급", "EE", 2232), ("2급", "ME", 1116), ("2급", "BE", 0),
    ("3급", "EX", 3024), ("3급", "EE", 2016), ("3급", "ME", 1008), ("3급", "BE", 0),
]

SALARY_CAP_TABLE = [
    ("1급", 85728),
    ("2급", 78540),
    ("3급", 77724),
]

WAGE_PEAK_TABLE = [
    (1, 0.9),
    (2, 0.8),
    (3, 0.7),
]

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

BONUS_RATE_TABLE = [
    ("P01", "EX", 1.0), ("P01", "EE", 0.85), ("P01", "ME", 0.70), ("P01", "BE", 0.0),
    ("P02", "EX", 1.0), ("P02", "EE", 0.85), ("P02", "ME", 0.70), ("P02", "BE", 0.0),
    ("P05", "EX", 0.85), ("P05", "EE", 0.70), ("P05", "ME", 0.55), ("P05", "BE", 0.0),
    ("P08", "EX", 0.70), ("P08", "EE", 0.55), ("P08", "ME", 0.40), ("P08", "BE", 0.0),
    ("P09", "EX", 0.60), ("P09", "EE", 0.45), ("P09", "ME", 0.30), ("P09", "BE", 0.0),
    ("P10", "EX", 0.60), ("P10", "EE", 0.45), ("P10", "ME", 0.30), ("P10", "BE", 0.0),
]


# ────────────────────────────────────────────────────────────
# 삽입 함수들
# ────────────────────────────────────────────────────────────

def clear_db(session):
    """기존 데이터 전체 삭제"""
    session.run("MATCH (n) DETACH DELETE n")


def insert_regulation(session):
    """규정 본체"""
    session.run("""
        CREATE (:규정 {
            규정번호: 'BOK-COMP-2025',
            명칭: '보수규정',
            설명: '한국은행법과 한국은행정관에 따라 금융통화위원회 위원, 집행간부, 감사 및 직원의 보수 및 상여금에 관한 사항을 규정',
            시행일: date('1998-04-16'),
            활성여부: true
        })
    """)


def insert_amendment_history(session):
    """개정이력 + 규정-개정이력 관계"""
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
        session.run("""
            MATCH (reg:규정 {규정번호: 'BOK-COMP-2025'})
            CREATE (h:개정이력 {개정일: date($date), 설명: $desc})
            CREATE (reg)-[:규정개정]->(h)
        """, date=date_str, desc=desc)


def insert_articles(session):
    """조문 (제1조~제15조) + 규정-조문 관계"""
    articles = [
        (1, None, "(목적) 이 규정은 한국은행법과 한국은행정관에 따라 금융통화위원회 위원, 집행간부, 감사 및 직원의 보수 및 상여금에 관한 사항을 규정함을 목적으로 한다."),
        (2, None, "(정의) 보수란 위원·집행간부·감사에 대하여는 기본급을 말하며, 직원에 대하여는 기본급 및 제수당을 말한다."),
        (3, None, "(보수계산기간) 보수는 월급 또는 연봉으로 한다."),
        (4, None, "(본봉) 위원, 집행간부, 감사의 본봉은 별표1의 1.로 한다."),
        (4, 2, "(연봉제본봉) 연봉제본봉은 직전 연봉제본봉에 별표7의 평가등급별 차등액을 합한 금액으로 한다."),
        (4, 3, "(임금피크제본봉) 임금피크제본봉은 적용 직전 월말일 현재의 본봉에 별표9의 기본급지급률을 곱한 금액으로 한다."),
        (4, 4, "(직책급) 직원에 대한 직책급은 직책 및 직급에 따라 결정되는 별표1-1의 직책급과 임금피크제직책급으로 한다."),
        (5, None, "(승급) 1개 호봉간의 승급에 필요한 최저근무기간은 1년을 원칙으로 한다."),
        (6, None, "(초임호봉 및 연봉제본봉) 신규채용자의 초임호봉은 별표2와 같다."),
        (7, None, "(업무수당) 종사업무별로 해당 업무 또는 기술분야에 직접 종사하는 직원에 대하여는 별표3의 업무수당을 지급한다."),
        (9, None, "(시간외근무수당) 시간외근무에 대해서는 시간당 보수의 1.5배에 해당하는 금액을 지급한다."),
        (11, None, "(조정수당) 해외직원이 소득세 초과분에 대해 조정수당을 지급할 수 있다."),
        (12, None, "(상여금의 지급) 위원, 집행간부, 감사 및 직원에 대하여 상여금을 지급한다."),
        (12, 2, "(상여금 지급률) 정기상여금은 연간지급률 380%로 지급한다."),
        (12, 3, "(평가상여금) 평가상여금은 별표1-2의 지급률을 기본급에 곱한 금액을 지급한다."),
        (13, None, "(비밀유지) 직원은 자신의 보수를 다른 직원에게 알려주는 행위를 하여서는 아니 된다."),
        (14, None, "(일반기능직원등의 보수) 기한부 고용계약자에 대하여는 보수 및 상여금 규정을 적용하지 아니한다."),
        (15, None, "(위임) 파견자, 휴직자 등의 보수에 관한 세부사항은 총재가 정한다."),
    ]
    for jo, hang, content in articles:
        params = {"jo": jo, "content": content}
        if hang is not None:
            params["hang"] = hang
            session.run("""
                MATCH (reg:규정 {규정번호: 'BOK-COMP-2025'})
                CREATE (a:조문 {조번호: $jo, 항번호: $hang, 조문내용: $content})
                CREATE (reg)-[:규정구성]->(a)
            """, **params)
        else:
            session.run("""
                MATCH (reg:규정 {규정번호: 'BOK-COMP-2025'})
                CREATE (a:조문 {조번호: $jo, 조문내용: $content})
                CREATE (reg)-[:규정구성]->(a)
            """, **params)


def insert_career_tracks(session):
    """직렬"""
    tracks = [
        ("CT-GP", "종합기획직원", "1급~6급 및 G1~G5 적용"),
        ("CT-GA", "일반사무직원", "별표1의 3. 일반사무직원 본봉표 적용"),
        ("CT-SP", "별정직원", "별도 보수체계 적용"),
        ("CT-CL", "서무직원", "별표1의 4. 서무직원 본봉표 적용"),
        ("CT-PO", "청원경찰", "별표1의 4. 청원경찰 본봉표 적용"),
    ]
    for code, name, desc in tracks:
        session.run("""
            CREATE (:직렬 {직렬코드: $code, 직렬명: $name, 설명: $desc})
        """, code=code, name=name, desc=desc)


def insert_grades(session):
    """직급 + 직렬분류 관계"""
    # 종합기획 직급 (1~6급, G1~G5)
    grades = [
        ("1급", "1급", 1), ("2급", "2급", 2), ("3급", "3급", 3),
        ("4급", "4급", 4), ("5급", "5급", 5), ("6급", "6급", 6),
        ("G1", "G1", 7), ("G2", "G2", 8), ("G3", "G3", 9),
        ("G4", "G4", 10), ("G5", "G5", 11),
    ]
    for code, name, rank in grades:
        session.run("""
            CREATE (:직급 {직급코드: $code, 직급명: $name, 서열: $rank})
        """, code=code, name=name, rank=rank)

    # 특수 직급
    for code, name, rank in [("GA", "일반사무", 12), ("CL", "서무", 13), ("PO", "청원경찰", 14)]:
        session.run("""
            CREATE (:직급 {직급코드: $code, 직급명: $name, 서열: $rank})
        """, code=code, name=name, rank=rank)

    # 직렬분류: 종합기획 ↔ 1~6급, G1~G5
    for code in ["1급", "2급", "3급", "4급", "5급", "6급",
                 "G1", "G2", "G3", "G4", "G5"]:
        session.run("""
            MATCH (ct:직렬 {직렬코드: 'CT-GP'})
            MATCH (g:직급 {직급코드: $code})
            CREATE (ct)-[:직렬분류]->(g)
        """, code=code)

    # 일반사무 ↔ GA, 서무 ↔ CL, 청원경찰 ↔ PO
    for ct_code, g_code in [("CT-GA", "GA"), ("CT-CL", "CL"), ("CT-PO", "PO")]:
        session.run("""
            MATCH (ct:직렬 {직렬코드: $ct_code})
            MATCH (g:직급 {직급코드: $g_code})
            CREATE (ct)-[:직렬분류]->(g)
        """, ct_code=ct_code, g_code=g_code)


def insert_positions(session):
    """직위"""
    positions = [
        ("P01", "부서장(가)", 1), ("P02", "부서장(나)", 2),
        ("P03", "국소속실장", 3), ("P04", "부장", 4),
        ("P05", "팀장", 5), ("P06", "반장", 6),
        ("P07", "조사역", 7), ("P08", "주임조사역(C1)", 8),
        ("P09", "조사역(C2)", 9), ("P10", "조사역(C3)", 10),
    ]
    for code, name, rank in positions:
        session.run("""
            CREATE (:직위 {직위코드: $code, 직위명: $name, 서열: $rank})
        """, code=code, name=name, rank=rank)


def insert_salary_table(session):
    """별표1 본봉표 — 호봉 노드 + 호봉체계구성 관계"""
    for grade_code, data in SALARY_TABLE.items():
        start = data["start"]
        for idx, amount_1000 in enumerate(data["amounts"]):
            hobong = start + idx
            amount = float(amount_1000 * 1000)
            session.run("""
                MATCH (g:직급 {직급코드: $grade})
                CREATE (h:호봉 {호봉번호: $hobong, 호봉금액: $amount, 적용시작일: date('2025-01-01')})
                CREATE (g)-[:호봉체계구성]->(h)
            """, grade=grade_code, hobong=hobong, amount=amount)


def insert_position_pay(session):
    """별표1-1 직책급표 — 직책급기준 노드 + 해당직급/해당직위 관계"""
    for pos_code, grade_code, amount_1000 in POSITION_PAY_TABLE:
        code = f"PP-{pos_code}-{grade_code}"
        amount = float(amount_1000 * 1000)
        session.run("""
            MATCH (pos:직위 {직위코드: $pos_code})
            MATCH (g:직급 {직급코드: $grade_code})
            CREATE (pp:직책급기준 {코드: $code, 직책급액: $amount,
                    적용시작일: date('2025-01-01'), 설명: '별표1-1 종합기획직원 직책급'})
            CREATE (pp)-[:해당직급]->(g)
            CREATE (pp)-[:해당직위]->(pos)
        """, pos_code=pos_code, grade_code=grade_code, code=code, amount=amount)


def insert_allowances(session):
    """수당 (별표3 + 시간외근무수당)"""
    allowances = [
        ("BIZ-CASH-23", "출납업무수당(2~3급)", "정액", 60000.0,
         "출납업무 직접 종사 종합기획 2급~3급, G2~G3", "별표3 1.출납업무"),
        ("BIZ-CASH-46", "출납업무수당(4~6급)", "정액", 70000.0,
         "출납업무 직접 종사 종합기획 4급~6급, G4~G5, 일반사무직원", "별표3 1.출납업무"),
        ("BIZ-CASH-SM", "출납업무수당(서무)", "정액", 50000.0,
         "출납업무 직접 종사 서무직원", "별표3 1.출납업무"),
        ("BIZ-IT-10Y-23", "전산정보업무수당(2~3급,10년이상)", "정액", 160000.0,
         "전산정보업무 10년↑ 종합기획 2급~3급", "별표3 2.전산정보업무"),
        ("BIZ-IT-10Y-45", "전산정보업무수당(4~5급,10년이상)", "정액", 170000.0,
         "전산정보업무 10년↑ 종합기획 4급~5급, G4~G5", "별표3 2.전산정보업무"),
        ("BIZ-IT-5Y-23", "전산정보업무수당(2~3급,5~10년)", "정액", 120000.0,
         "전산정보업무 5~10년 종합기획 2급~3급", "별표3 2.전산정보업무"),
        ("BIZ-IT-5Y-45", "전산정보업무수당(4~5급,5~10년)", "정액", 130000.0,
         "전산정보업무 5~10년 종합기획 4급~5급", "별표3 2.전산정보업무"),
        ("BIZ-TECH-23", "기술업무수당(2~3급)", "정액", 90000.0,
         "기술분야 종사 종합기획 2급~3급, G2~G3", "별표3 3.기술업무"),
        ("BIZ-TECH-45", "기술업무수당(4~6급)", "정액", 100000.0,
         "기술분야 종사 종합기획 4급~6급, G4~G5, 일반사무직원", "별표3 3.기술업무"),
        ("BIZ-TECH-SM", "기술업무수당(서무)", "정액", 60000.0,
         "기술분야 종사 서무직원", "별표3 3.기술업무"),
        ("BIZ-RES-G2", "조사연구업무수당(G2)", "정액", 20000.0,
         "조사연구업무 종사 종합기획 2급, G2", "별표3 4.조사연구업무"),
        ("BIZ-RES-G3", "조사연구업무수당(G3)", "정액", 30000.0,
         "조사연구업무 종사 종합기획 3급, G3", "별표3 4.조사연구업무"),
        ("BIZ-RES-G4", "조사연구업무수당(G4)", "정액", 80000.0,
         "조사연구업무 종사 종합기획 4급, G4", "별표3 4.조사연구업무"),
        ("BIZ-RES-G5", "조사연구업무수당(G5)", "정액", 150000.0,
         "조사연구업무 종사 종합기획 5급, G5", "별표3 4.조사연구업무"),
    ]
    for code, name, atype, amount, cond, desc in allowances:
        session.run("""
            CREATE (:수당 {수당코드: $code, 수당명: $name, 수당유형: $atype,
                    수당액: $amount, 지급조건: $cond, 설명: $desc})
        """, code=code, name=name, atype=atype, amount=amount, cond=cond, desc=desc)

    # 시간외근무수당 (비율형)
    session.run("""
        CREATE (:수당 {수당코드: 'OT-WORK', 수당명: '시간외근무수당', 수당유형: '비율',
                지급률: 1.5, 지급조건: '시간외근무 시 시간당 보수의 1.5배',
                설명: '제9조. 시간당보수=통상임금월지급액/209'})
    """)


def insert_exec_compensation(session):
    """보수기준 (별표1 1. 위원/집행간부/감사)"""
    execs = [
        ("EXEC-GOV", "총재 본봉", 336710000.0, "별표1 1. 연간총액 - 총재"),
        ("EXEC-VICE", "위원·부총재 본봉", 309770000.0, "별표1 1. 연간총액 - 위원·부총재"),
        ("EXEC-AUDIT", "감사 본봉", 296310000.0, "별표1 1. 연간총액 - 감사"),
        ("EXEC-SVICE", "부총재보 본봉", 249190000.0, "별표1 1. 연간총액 - 부총재보"),
    ]
    for code, name, amount, desc in execs:
        session.run("""
            CREATE (:보수기준 {코드: $code, 명칭: $name, 기본급액: $amount,
                    적용시작일: date('2025-01-01'), 설명: $desc})
        """, code=code, name=name, amount=amount, desc=desc)


def insert_evaluations(session):
    """평가등급 (별표1-2, 별표1-3, 별표7)"""
    evals = [
        ("EX", 2025, 2, 0.10),
        ("EE", 2025, 1, 0.25),
        ("ME", 2025, 1, 0.40),
        ("BE", 2025, 0, 0.20),
        ("NI", 2025, 0, 0.05),
    ]
    for grade, year, steps, ratio in evals:
        session.run("""
            CREATE (:평가결과 {평가등급: $grade, 평가년도: $year,
                    승급호봉수: $steps, 배분율: $ratio})
        """, grade=grade, year=year, steps=steps, ratio=ratio)


def insert_bonus_standards(session):
    """상여금기준 (제12조, 별표1-2) + 상여금결정 관계"""
    # 정기상여금
    session.run("""
        CREATE (:상여금기준 {코드: 'BONUS-REG', 상여유형: '정기', 명칭: '정기상여금',
                연간지급률: 3.8, 설명: '연간 380%. 6·12월 각 150%, 설·추석 각 40%'})
    """)
    # 평가상여금
    for pos_code, eval_grade, rate in BONUS_RATE_TABLE:
        code = f"BONUS-EVAL-{pos_code}-{eval_grade}"
        session.run("""
            MATCH (pos:직위 {직위코드: $pos_code})
            MATCH (ev:평가결과 {평가등급: $eval_grade})
            CREATE (b:상여금기준 {코드: $code, 상여유형: '평가', 명칭: '평가상여금',
                    지급률: $rate, 설명: '별표1-2 평가상여금지급률표'})
            CREATE (b)-[:해당직책구분]->(pos)
            CREATE (b)-[:해당등급]->(ev)
        """, pos_code=pos_code, eval_grade=eval_grade, code=code, rate=rate)


def insert_salary_diff(session):
    """별표7 연봉차등액기준 + 연봉차등 관계"""
    for grade_code, eval_grade, diff_1000 in SALARY_DIFF_TABLE:
        code = f"DIFF-{grade_code}-{eval_grade}"
        diff = float(diff_1000 * 1000)
        session.run("""
            MATCH (g:직급 {직급코드: $grade_code})
            MATCH (ev:평가결과 {평가등급: $eval_grade})
            CREATE (d:연봉차등액기준 {코드: $code, 차등액: $diff,
                    적용시작일: date('2025-01-01'), 설명: '별표7 연봉제본봉 차등액'})
            CREATE (d)-[:해당직급]->(g)
            CREATE (d)-[:해당등급]->(ev)
        """, grade_code=grade_code, eval_grade=eval_grade, code=code, diff=diff)


def insert_salary_cap(session):
    """별표8 연봉상한액기준 + 연봉상한 관계"""
    for grade_code, cap_1000 in SALARY_CAP_TABLE:
        code = f"CAP-{grade_code}"
        cap = float(cap_1000 * 1000)
        session.run("""
            MATCH (g:직급 {직급코드: $grade_code})
            CREATE (c:연봉상한액기준 {코드: $code, 상한액: $cap,
                    적용시작일: date('2025-01-01'), 설명: '별표8 연봉제본봉 상한액'})
            CREATE (c)-[:해당직급]->(g)
        """, grade_code=grade_code, code=code, cap=cap)


def insert_wage_peak(session):
    """별표9 임금피크제기준"""
    for year, rate in WAGE_PEAK_TABLE:
        code = f"WP-Y{year}"
        session.run("""
            CREATE (:임금피크제기준 {코드: $code, 적용연차: $year, 지급률: $rate,
                    설명: $desc})
        """, code=code, year=year, rate=rate,
             desc=f"별표9 임금피크제 적용연차 {year}년차 기본급지급률 {int(rate*100)}%")


def insert_overseas_salary(session):
    """별표1-5 국외본봉기준 + 국외본봉결정 관계"""
    for country_code, country_name, grade_code, amount, currency in OVERSEAS_SALARY:
        code = f"OVS-{country_code}-{grade_code}"
        session.run("""
            MATCH (g:직급 {직급코드: $grade_code})
            CREATE (o:국외본봉기준 {코드: $code, 국가코드: $cc, 국가명: $cn,
                    기본급액: $amount, 통화단위: $cur,
                    적용시작일: date('2025-01-01'), 설명: '별표1-5 해외직원 국외본봉'})
            CREATE (o)-[:해당직급]->(g)
        """, grade_code=grade_code, code=code, cc=country_code,
             cn=country_name, amount=amount, cur=currency)


def insert_starting_step(session):
    """별표2 초임호봉기준 + 초임호봉결정 관계"""
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
        session.run("""
            MATCH (ct:직렬 {직렬코드: $ct_code})
            CREATE (s:초임호봉기준 {코드: $code, 초임호봉번호: $hobong,
                    설명: $desc_full})
            CREATE (s)-[:대상직렬]->(ct)
        """, ct_code=ct_code, code=code, hobong=hobong,
             desc_full=f"별표2 {desc}")


# ────────────────────────────────────────────────────────────
# 검증 & 메인
# ────────────────────────────────────────────────────────────

def verify_data(session):
    """삽입 결과 검증"""
    labels = [
        "규정", "조문", "개정이력", "직렬", "직급", "직위", "호봉", "수당",
        "보수기준", "직책급기준", "상여금기준", "연봉차등액기준", "연봉상한액기준",
        "임금피크제기준", "국외본봉기준", "초임호봉기준", "평가결과",
    ]
    total = 0
    for label in labels:
        result = session.run(f"MATCH (n:`{label}`) RETURN count(n) AS cnt")
        cnt = result.single()["cnt"]
        total += cnt
        print(f"  {label}: {cnt}건")

    print(f"\n  총 노드: {total}건")

    # 관계 카운트
    rels = [
        "규정구성", "규정개정", "직렬분류", "호봉체계구성",
        "해당직급", "해당직위", "해당직책구분", "해당등급", "대상직렬",
    ]
    print()
    rtotal = 0
    for rel in rels:
        result = session.run(f"MATCH ()-[r:`{rel}`]->() RETURN count(r) AS cnt")
        cnt = result.single()["cnt"]
        rtotal += cnt
        print(f"  [{rel}]: {cnt}건")
    print(f"\n  총 관계: {rtotal}건")


def main():
    config = Neo4jConfig()
    driver = get_driver(config)

    print("=" * 60)
    print("한국은행 보수규정 — Neo4j 데이터 삽입")
    print("=" * 60)

    with driver.session(database=config.database) as session:
        print("\n기존 데이터 삭제...")
        clear_db(session)

        steps = [
            ("규정 본체", insert_regulation),
            ("개정이력 (규정개정 관계)", insert_amendment_history),
            ("조문 (제1조~제15조)", insert_articles),
            ("직렬 (5개 직렬)", insert_career_tracks),
            ("직급 + 직렬분류", insert_grades),
            ("직위/직책", insert_positions),
            ("호봉 본봉표 (별표1)", insert_salary_table),
            ("직책급 (별표1-1)", insert_position_pay),
            ("수당 (별표3 + 시간외)", insert_allowances),
            ("보수기준 (위원/집행간부/감사)", insert_exec_compensation),
            ("평가등급 + 배분율", insert_evaluations),
            ("상여금기준 (별표1-2)", insert_bonus_standards),
            ("연봉차등액 (별표7)", insert_salary_diff),
            ("연봉상한액 (별표8)", insert_salary_cap),
            ("임금피크제 (별표9)", insert_wage_peak),
            ("국외본봉 (별표1-5)", insert_overseas_salary),
            ("초임호봉 (별표2)", insert_starting_step),
        ]

        for i, (name, func) in enumerate(steps, 1):
            print(f"  [{i:2d}/{len(steps)}] {name}...")
            func(session)

        print("\n--- 삽입 결과 검증 ---")
        verify_data(session)

    driver.close()
    print("\n완료!")


if __name__ == "__main__":
    main()
