def _get_role_summary(func_name: str, module: str) -> str:
    summary_map = {
        "extract_entities": "질문에서 주요 개체(직급, 평가점수 등) 및 의도(Intent) 추출",
        "_determine_hop_depth": "그래프 탐색 깊이 판단",
        "fetch_subgraph_typedb": "TypeDB 지식 그래프에서 조건에 맞는 서브그래프(조견표 연결망) 도출",
        "fetch_relevant_rules": "Vector DB/Context에서 관련된 원문 규정 조항 텍스트를 검색",
        "try_execute_regulation": "파이썬으로 구현된 Rule-Engine을 통해 하드코딩된 급여 계산 실행",
        "generate_answer": "검색/계산된 최종 데이터를 종합하여 자연어 답변 생성",
        "run_query": "에이전트 판단 루프 시작 (데이터 추론)",
        "execute_cypher": "Agent가 동적 생성한 Graph Query로 Neo4j에서 HR 규칙/값 직접 조회 연산",
        "route_with_context": "조회 모드 분기 (내용 질의 vs 수치 계산)",
        "build_answer_with_context": "원문 컨텍스트 텍스트만 사용하여 순수 LLM 답변 예측"
    }
    for k, v in summary_map.items():
        if k in func_name:
            return v
    if "Agent" in module or "agent" in module:
        return "자율적 판단 에이전트 구동"
    return "기본 파이프라인 함수 실행"

def _render_execution_chain(trace: dict) -> None:
    calls = trace.get("function_calls", [])
    if not calls:
        if trace.get("mode") == "direct_llm":
            st.info("Chain: base_llm.invoke(질문) -> 모델 내재 지식 답변 : 사전학습 지식으로만 응답 생성")
            return
        st.write("실행 체인 정보가 없습니다.")
        return
        
    for i, call in enumerate(calls):
        mod = call.get("module", "unknown").split("/")[-1].replace(".py", "")
        func = call.get("function", "unknown")
        args = call.get("arguments", {})
        result = call.get("result", "완료")
        
        args_str = str(args)[:200] + ("..." if len(str(args)) > 200 else "")
        res_str = str(result)[:200] + ("..." if len(str(result)) > 200 else "")
        
        summary = _get_role_summary(func, mod)
        
        st.markdown(f"**Step {i+1}: `{mod}.{func}()`**")
        st.caption(f"💡 **역할**: {summary}")
        
        col1, col2 = st.columns([1, 1])
        with col1:
            st.markdown("*입력 (Input)*")
            st.code(args_str, language="json")
        with col2:
            st.markdown("*출력 (Output)*")
            st.code(res_str, language="json")
        
        if i < len(calls) - 1:
            st.markdown("<div style='text-align: center; color: #888;'>⬇️ 전달</div>", unsafe_allow_html=True)
