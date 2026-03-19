import sys

class CuratedQuestionCase:
    def __init__(self, case_id, category, difficulty, question, answer):
        self.case_id = case_id
        self.category = category
        self.difficulty = difficulty
        self.question = question
        self.expected_answer = answer

CURATED_QUESTION_CASES = [
    CuratedQuestionCase("Q01", "규정검색", "하", "보수규정의 목적은 무엇인가?", "한국은행법과 한국은행정관에 따라 위원, 집행간부, 감사 및 직원의 보수와 상여금에 관한 사항을 규정하는 것이다."),
    CuratedQuestionCase("Q02", "규정검색", "하", "직원에게서 말하는 보수는 무엇을 뜻하는가?", "직원에게서 보수는 기본급과 제수당을 뜻한다."),
    CuratedQuestionCase("Q03", "규정검색", "하", "기본급은 무엇으로 구성되는가?", "기본급은 본봉과 직책급으로 구성된다."),
    CuratedQuestionCase("Q04", "규정검색", "하", "해외직원의 정의는 무엇인가?", "국외사무소에 근무하는 본부 집행간부 및 직원을 말한다."),
    CuratedQuestionCase("Q05", "규정검색", "하", "승급이란 무엇인가?", "현재의 호봉보다 높은 호봉을 부여하는 것을 말한다."),
    CuratedQuestionCase("Q06", "규정검색", "하", "보수 계산 기간은 어떻게 정해지는가?", "보수는 월급 또는 연봉으로 하되 필요한 경우 일급으로 할 수 있다."),
    CuratedQuestionCase("Q07", "규정검색", "중", "연봉제본봉 적용 대상은 누구인가?", "1급 및 G1, 2급 및 G2, 반장 이상의 직책을 담당하는 3급 및 G3 종합기획직원 이다."),
    CuratedQuestionCase("Q08", "규정검색", "중", "임금피크제본봉 적용 대상은 누구인가?", "잔여근무기간이 3년 이하인 직원이다."),
    CuratedQuestionCase("Q09", "규정검색", "중", "기한부 고용계약자에게 제2장 보수와 제3장 상여금 규정이 적용되는가?", "적용되지 않는다."),
    CuratedQuestionCase("Q10", "규정검색", "하", "직원은 다른 직원의 보수를 알려고 해도 되는가?", "안 된다. 자신의 보수를 알리거나 다른 직원의 보수를 알려는 행위를 해서는 안 된다."),
    CuratedQuestionCase("Q11", "규정검색", "하", "월급의 지급일은 언제인가?", "매월 21일에 지급하되, 휴일인 경우 그 전일에 지급한다."),
    CuratedQuestionCase("Q12", "규정검색", "중", "결근한 직원에 대해 보수를 어떻게 감액하는가?", "결근일수 매1일에 대하여 월급액을 당해월의 일수로 나눈 금액을 감액한다."),
    CuratedQuestionCase("Q13", "규정검색", "상", "직위해제 또는 정직된 직원의 보수는 어떻게 지급하는가?", "처분일로부터 3개월 이내는 본봉 또는 연봉월액의 100분의 40을 지급하고, 3개월 초과 시 100분의 20을 지급한다."),
    CuratedQuestionCase("Q14", "규정검색", "중", "제수당에는 어떤 것들이 있는가?", "가족수당, 특수작업수당, 시간외근무수당, 야간근무수당, 휴일근무수당 등이 있다."),
    CuratedQuestionCase("Q15", "규정검색", "하", "상여금은 언제 지급하는가?", "지급 목적과 기준에 따라 지급 시기가 다를 수 있다."),
    CuratedQuestionCase("Q16", "규정검색", "중", "상여금 지급 대상자는 누구인가?", "지급일 현재 재직 중인 자, 휴직 중인 자, 퇴직 및 사망한 자 등이다."),
    CuratedQuestionCase("Q17", "규정검색", "하", "시간외근무수당은 어떤 경우에 지급되는가?", "정상근무시간 외에 근무한 경우 지급된다."),
    CuratedQuestionCase("Q18", "규정검색", "하", "가족수당은 누구에게 지급되는가?", "부양가족이 있는 직원에게 지급된다."),
    CuratedQuestionCase("Q19", "규정검색", "하", "특수작업수당은 어떤 경우에 지급되는가?", "특수한 작업 환경이나 조건에서 근무하는 직원에게 지급된다."),
    CuratedQuestionCase("Q20", "규정검색", "상", "연봉제본봉 적용 직원의 연봉차등액 산정 기준은 무엇인가?", "직전 연봉제본봉에 직급별, 평가등급별 연봉차등금액을 가감하여 산정한다."),
    CuratedQuestionCase("Q21", "계산", "하", "G5 직원의 초봉은 얼마인가?", "11호봉, 1,554,000원"),
    CuratedQuestionCase("Q22", "계산", "하", "6급 일반사무직원의 초봉은 얼마인가?", "11호봉, 1,554,000원"),
    CuratedQuestionCase("Q23", "계산", "중", "4급 직원의 10호봉은 얼마인가?", "1,554,000원"),
    CuratedQuestionCase("Q24", "계산", "중", "5급 직원의 20호봉은 얼마인가?", "2,130,000원"),
    CuratedQuestionCase("Q25", "계산", "하", "1급 직원의 직책급은 얼마인가?", "2,832,000원"),
    CuratedQuestionCase("Q26", "계산", "하", "2급 직원의 직책급은 얼마인가?", "2,268,000원"),
    CuratedQuestionCase("Q27", "계산", "하", "3급 직원의 일반 직책급은 얼마인가?", "1,392,000원"),
    CuratedQuestionCase("Q28", "계산", "상", "3급 직원이 팀장인 경우 직책급은 얼마인가?", "1,956,000원"),
    CuratedQuestionCase("Q29", "계산", "중", "1급 EX 등급의 연봉차등액은 얼마인가?", "3,672,000원"),
    CuratedQuestionCase("Q30", "계산", "중", "2급 EE 등급의 연봉차등액은 얼마인가?", "2,232,000원"),
    CuratedQuestionCase("Q31", "계산", "중", "3급 ME 등급의 연봉차등액은 얼마인가?", "-1,008,000원"),
    CuratedQuestionCase("Q32", "계산", "상", "1급 직원의 연봉상한액은 얼마인가?", "103,404,000원"),
    CuratedQuestionCase("Q33", "계산", "상", "3급 직원의 연봉상한액은 얼마인가?", "77,724,000원"),
    CuratedQuestionCase("Q34", "계산", "하", "미국 주재 1급 직원의 국외본봉은 얼마인가?", "10,780 USD"),
    CuratedQuestionCase("Q35", "계산", "하", "영국 주재 3급 직원의 국외본봉은 얼마인가?", "7,810 GBP"),
    CuratedQuestionCase("Q36", "계산", "하", "일본 주재 4급 직원의 국외본봉은 얼마인가?", "7,000 USD (또는 JPY 기준)"),
    CuratedQuestionCase("Q37", "계산", "중", "임금피크제 1년차의 임금피크제본봉 지급기준은?", "직전 연봉제본봉의 0.90"),
    CuratedQuestionCase("Q38", "계산", "상", "임금피크제 4년차의 제수당 등 지급률은?", "0.55"),
    CuratedQuestionCase("Q39", "계산", "중", "호봉제본봉 대상 직원의 승급 시 본봉 차액은?", "호봉표에 따른 차액 계산이 필요함."),
    CuratedQuestionCase("Q40", "계산", "상", "결근 5일인 경우 감액되는 보수 금액을 계산하는 공식은?", "(결근월의 월급액 / 당해월의 일수) * 5"),
    CuratedQuestionCase("Q41", "복합", "상", "기한부 고용계약자가 상여금을 받을 수 있는지와 G5 직원의 초봉을 함께 알려줘.", "기한부 고용계약자는 상여금 없음, G5 직원 초봉은 11호봉(1,554,000원)."),
    CuratedQuestionCase("Q42", "복합", "상", "G5 직원의 초봉과 미국 주재 2급 직원의 국외본봉을 함께 알려줘.", "G5 초봉: 11호봉(1,554,000원), 미 주재 2급 국외본봉: 9,760 USD."),
    CuratedQuestionCase("Q43", "복합", "상", "보수규정의 목적을 설명하고, 1급 직원의 연봉상한액을 알려줘.", "목적: 보수/상여금 규정. 1급 연봉상한액: 103,404,000원."),
    CuratedQuestionCase("Q44", "복합", "상", "임금피크제본봉 적용 대상자와 1년차 지급기준을 알려줘.", "대상: 잔여근무 3년 이하. 1년차 지급기준: 0.90."),
    CuratedQuestionCase("Q45", "복합", "중", "기본급의 구성요소 2가지를 말하고, 1급 직원의 직책급을 알려줘.", "구성: 본봉, 직책급. 1급 직책급: 2,832,000원."),
    CuratedQuestionCase("Q46", "복합", "상", "직위해제 처분을 받은 직원이 처분 후 4개월째 받는 본봉의 비율은 얼마인가?", "처분 후 3개월 초과 시 100분의 20 (20%)."),
    CuratedQuestionCase("Q47", "복합", "상", "해외직원의 정의를 밝히고, 영국에 주재하는 집행간부의 국외본봉을 알려줘.", "해외직원: 국외본부 직원 등. 영국 주재 집행간부 국외본봉: 11,280 GBP."),
    CuratedQuestionCase("Q48", "복합", "상", "연봉제본봉 적용 대상자를 설명하고, 2급 직원의 연봉상한액을 나열해줘.", "적용대상: 1급~3급 지정직원 등. 2급 연봉상한액: 90,816,000원."),
    CuratedQuestionCase("Q49", "복합", "상", "시간외근무수당 지급 조건과 결근 시 보수 감액 공식을 함께 설명해줘.", "시간외: 정상근무 외. 결근감액: (월급액 / 당월일수) * 결근일."),
    CuratedQuestionCase("Q50", "복합", "상", "상여금 지급 대상자와 기한부 고용계약자의 상여금 적용 여부를 비교해줘.", "대상자: 재직 중인 자 등. 기한부: 적용되지 않음.")
]

def main():
    backend_choice = sys.argv[1] if len(sys.argv) > 1 else "context"
    
    runners = {}
    if backend_choice in ["all", "neo4j"]:
        from src.bok_compensation_neo4j.agent import run_query as n_run
        runners["neo4j"] = n_run
    if backend_choice in ["all", "typedb"]:
        from src.bok_compensation_typedb.agent import run_query as t_run
        runners["typedb"] = t_run
    if backend_choice in ["all", "context"]:
        from src.bok_compensation_context.context_query import run_with_trace as c_run
        runners["context"] = c_run

    print("==================================================")
    print(f"  50 Test Cases Execution ({backend_choice.upper()})")
    print("==================================================")

    for backend_name, runner in runners.items():
        print(f"\n[{backend_name.upper()}] 평가 시작...")
        success_count = 0
        error_count = 0
        results_log = []

        for case in CURATED_QUESTION_CASES:
            try:
                res = runner(case.question)
                print(f"[✓] {case.case_id} 정상 응답")
                success_count += 1
            except Exception as e:
                error_count += 1
                results_log.append(f"[X] {case.case_id} Error: {str(e)[:50]}")
                print(f"[X] {case.case_id} 실패")
                
        print(f"\n>>> {backend_name.upper()} 결과 요약 <<<")
        print(f"총 문항: {len(CURATED_QUESTION_CASES)}")
        print(f"정상응답: {success_count}")
        print(f"에러/실패: {error_count}")
        for err in results_log:
             print(err)
        print("--------------------------------------------------")

if __name__ == "__main__":
    main()
