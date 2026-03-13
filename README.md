# 한국은행 보수규정 질의 비교 프로젝트

한국은행 보수규정 문서를 대상으로 같은 자연어 질문을 세 가지 방식으로 비교하는 저장소입니다.

- `TypeDB`: 스키마와 relation 중심 모델로 구조화 질의
- `Neo4j`: LPG 기반으로 구조화 질의
- `Context`: 전처리한 규정 텍스트와 마크다운 표만으로 LLM 추론

핵심 목표는 특정 구현 하나를 설명하는 것이 아니라, 같은 질문을 세 경로에 통과시켜 결과 안정성과 유지비용을 비교하는 것입니다.

## 비교 대상 요약

| 경로 | 구현 위치 | 강점 | 약점 |
|------|-----------|------|------|
| TypeDB | `src/bok_compensation/` | 엄격한 스키마, 관계 의미 보존, 정합성 검증에 유리 | TypeQL 생성 난이도가 높아 LLM 자유 생성에 불리 |
| Neo4j | `src/bok_compensation_neo4j/` | Cypher 생성이 비교적 안정적, 계산/디버깅 편함 | 스키마 강제가 약해 모델링 엄밀성은 상대적으로 낮음 |
| Context | `src/bok_compensation_context/` | DB 없이 바로 비교 가능, 규정 해석형 질문에 빠름 | 계산형/조인형 질의는 전처리 문서 품질에 크게 의존 |

## 가장 중요한 실행 명령

```bash
# TypeDB 경로
PYTHONPATH=src python -m bok_compensation.langgraph_query "G5 직원의 초봉은?"

# Neo4j 경로
PYTHONPATH=src python -m bok_compensation_neo4j.langgraph_query "G5 직원의 초봉은?"

# Context 경로
PYTHONPATH=src python -m bok_compensation_context.langgraph_query "G5 직원의 초봉은?"

# 세 경로 비교표
PYTHONPATH=src python tests/test_nl_pipeline.py compare
```

`tests/test_nl_pipeline.py compare`가 이 저장소의 핵심 출력입니다. 복합질문 세트를 TypeDB, Neo4j, Context에 동일하게 실행하고 PASS/FAIL을 한 표로 보여줍니다.

## 현재 상태

- TypeDB와 Neo4j 적재 데이터는 같은 규정 원문을 기준으로 유지합니다.
- 구조화 경로는 retrieval-guided planner, live catalog, key binding을 사용해 paraphrase 실패를 줄였습니다.
- Context 경로는 `regulation_context.md`를 기반으로 관련 섹션만 선택해 답변합니다.
- query trace와 failure artifact를 JSON으로 저장할 수 있습니다.
- 최근 기준 검증 결과:
  - `tests/validate_data.py all` → TypeDB 101/101, Neo4j 101/101
  - `tests/test_nl_pipeline.py langgraph typedb` → 2/2
  - `tests/test_nl_pipeline.py langgraph neo4j` → 2/2
  - `tests/test_nl_pipeline.py langgraph context` → 2/2
  - `tests/test_nl_pipeline.py compare` → 복합질문 4건, 세 경로 모두 PASS
  - `pytest tests/test_query_rules.py tests/test_nl_regressions.py -q` → 22 passed

## 프로젝트 구조

```text
bok-compensation-regulations/
├── src/
│   ├── bok_compensation/             # TypeDB 구현
│   ├── bok_compensation_neo4j/       # Neo4j 구현
│   └── bok_compensation_context/     # Context 비교 구현
├── schema/
│   └── compensation_regulation.tql   # TypeDB 스키마
├── docs/
│   ├── schema_diagram.md
│   ├── neo4j_schema_diagram.md
│   ├── neo4j_browser_queries.md
│   └── project_bootstrap_prompt.md
├── tests/
│   ├── validate_data.py
│   ├── test_nl_pipeline.py
│   ├── test_nl_regressions.py
│   ├── test_query_rules.py
│   ├── test_nl_router.py
│   └── test_typedb_router.py
├── pyproject.toml
└── README.md
```

## 비교 경로별 역할

### 1. TypeDB

- 구현 위치: `src/bok_compensation/`
- 목적: 엄격한 스키마와 relation 기반 모델로 규정 데이터를 구조화
- 기본 실행 경로: `python -m bok_compensation.langgraph_query`
- 보조 파일:
  - `query_retrieval.py`: 질문에서 intent와 슬롯 추출
  - `live_catalog.py`: 실제 DB에서 직급, 직위, 평가등급, 규칙 행 추출
  - `query_rules.py`: TypeQL 템플릿 우선 선택

### 2. Neo4j

- 구현 위치: `src/bok_compensation_neo4j/`
- 목적: Cypher 기반 구조화 질의 경로 제공
- 기본 실행 경로: `python -m bok_compensation_neo4j.langgraph_query`
- 특징: TypeDB와 같은 질문군을 좀 더 LLM 친화적인 쿼리 언어로 실행

### 3. Context

- 구현 위치: `src/bok_compensation_context/`
- 목적: DB 없이 전처리 문서만으로 답하는 비교 기준선 제공
- 기본 실행 경로: `python -m bok_compensation_context.langgraph_query`
- 핵심 파일:
  - `regulation_context.md`: 조문 요약 + 마크다운 표
  - `context_query.py`: 관련 섹션 선택 후 직접 추론

## 언제 어떤 경로를 봐야 하는가

| 질문 유형 | TypeDB | Neo4j | Context |
|-----------|--------|-------|---------|
| 구조적 조회 | 강함 | 강함 | 약함 |
| 수치/조합 계산 | 보통 | 강함 | 약함 |
| 규정 해석형 질문 | 보통 | 보통 | 강함 |
| 모델 정합성 검증 | 강함 | 보통 | 불가 |
| LLM 쿼리 생성 안정성 | 보통 | 강함 | 높음 |

운영 관점에서의 역할 분리는 아래처럼 보는 것이 맞습니다.

- TypeDB: 정합성 중심의 기준 모델
- Neo4j: 실용적인 구조화 질의 엔진
- Context: DB 없는 비교 기준선

## 설치

### 사전 요구사항

| 구성 요소 | 버전 | 용도 |
|-----------|------|------|
| Python | 3.9+ | 런타임 |
| TypeDB Server | 3.x | 구조화 그래프 DB |
| Neo4j | 5.x Community | 구조화 그래프 DB |
| Docker | 최신 | 컨테이너 실행 |
| LLM endpoint | OpenAI-compatible 또는 Ollama | 자연어 질의 |

### 컨테이너 실행

```bash
# TypeDB
docker run -d --name typedb \
  -p 1729:1729 -p 8000:8000 \
  typedb/typedb:latest

# Neo4j
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:5-community
```

### Python 환경

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev,neo4j,llm]
```

### 데이터 적재

```bash
# TypeDB
PYTHONPATH=src python -m bok_compensation.create_db
PYTHONPATH=src python -m bok_compensation.insert_data
PYTHONPATH=src python -m bok_compensation.check_db

# Neo4j
PYTHONPATH=src python -m bok_compensation_neo4j.create_schema
PYTHONPATH=src python -m bok_compensation_neo4j.insert_data
PYTHONPATH=src python -m bok_compensation_neo4j.check_db
```

## LLM 설정

기본값은 OpenAI 호환 엔드포인트입니다.

```bash
export LLM_PROVIDER=openai-compatible
export OPENAI_BASE_URL=http://211.188.81.250:30402/v1
export OPENAI_MODEL=HCX-GOV-THINK-V1-32B
```

Ollama를 쓸 경우:

```bash
export LLM_PROVIDER=ollama
export OLLAMA_URL=http://localhost:11434
export OLLAMA_MODEL=qwen2.5-coder:14b-instruct
```

## 검증 명령

비교 결과를 확인할 때는 아래 순서만 보면 충분합니다.

```bash
# 데이터 정합성
PYTHONPATH=src python tests/validate_data.py all

# retrieval / regression
PYTHONPATH=src python -m pytest tests/test_query_rules.py tests/test_nl_regressions.py -q

# 세 경로 LangGraph 스모크
PYTHONPATH=src python tests/test_nl_pipeline.py langgraph typedb
PYTHONPATH=src python tests/test_nl_pipeline.py langgraph neo4j
PYTHONPATH=src python tests/test_nl_pipeline.py langgraph context

# 세 경로 비교표
PYTHONPATH=src python tests/test_nl_pipeline.py compare
```

추가로 필요한 경우:

```bash
# 직접 쿼리 스모크
PYTHONPATH=src python tests/test_nl_pipeline.py direct all

# E2E 경로
PYTHONPATH=src python tests/test_nl_pipeline.py e2e typedb
PYTHONPATH=src python tests/test_nl_pipeline.py e2e neo4j
```

## 테스트가 보는 질문 범주

- 초임호봉: `G5 직원의 초봉은?`
- 규정 해석: `기한부 고용계약자는 상여금을 받을 수 있어?`
- 국외본봉: `미국 주재 2급 직원의 국외본봉은?`
- 임금피크제: `임금피크제 2년차 지급률은?`
- 개정이력: `보수규정 개정이력은 몇 번 있었어?`
- 복합질문: 초봉 + 국외본봉, 규정 해석 + 수치 조회 조합

## 자연어 질의 구조

TypeDB와 Neo4j 경로는 공통적으로 아래 흐름을 따릅니다.

```text
질문 → Planner → Semantic/Data 실행 → Summary
```

안정화 장치:

- `query_retrieval.py`: 질문에서 intent와 핵심 슬롯 추출
- `live_catalog.py`: 실제 DB에서 바인딩 가능한 값 추출
- `query_rules.py`: 자유 생성 전에 규칙 기반 템플릿 적용
- `BOK_QUERY_TRACE_DIR`: query trace JSON 저장
- `BOK_FAILURE_TRACE_DIR`: 실패 artifact JSON 저장

Context 경로는 DB 조회 대신 `regulation_context.md`에서 관련 섹션을 골라 LLM에 직접 전달합니다.

## 데이터 범주

비교용으로 유지하는 핵심 데이터 범주는 아래와 같습니다.

| 범주 | 예시 |
|------|------|
| 조문/규정 해석 | 기한부 고용계약자 상여금 가능 여부 |
| 호봉/본봉 | 3급 50호봉, G5 초봉 |
| 직책급 | 팀장, 부서장가/나 |
| 상여금 | 직책구분 × 평가등급 |
| 연봉차등액/상한액 | 1~3급 평가 차등, 상한액 |
| 임금피크제 | 적용연차별 지급률 |
| 국외본봉 | 국가 × 직급 |
| 개정이력 | 부칙 개정 내역 |

## 참고 문서

- TypeDB 다이어그램: [docs/schema_diagram.md](docs/schema_diagram.md)
- Neo4j 다이어그램: [docs/neo4j_schema_diagram.md](docs/neo4j_schema_diagram.md)
- Neo4j 브라우저용 질의: [docs/neo4j_browser_queries.md](docs/neo4j_browser_queries.md)
- 프로젝트 부트스트랩 메모: [docs/project_bootstrap_prompt.md](docs/project_bootstrap_prompt.md)

## 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `TYPEDB_ADDRESS` | `localhost:1729` | TypeDB 서버 주소 |
| `TYPEDB_DATABASE` | `bok-compensation-regulations` | TypeDB 데이터베이스명 |
| `TYPEDB_USERNAME` | `admin` | TypeDB 사용자명 |
| `TYPEDB_PASSWORD` | `password` | TypeDB 비밀번호 |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j Bolt 주소 |
| `NEO4J_USERNAME` | `neo4j` | Neo4j 사용자명 |
| `NEO4J_PASSWORD` | `password` | Neo4j 비밀번호 |
| `NEO4J_DATABASE` | `neo4j` | Neo4j 데이터베이스명 |
| `LLM_PROVIDER` | `openai-compatible` | `openai-compatible` 또는 `ollama` |
| `OPENAI_BASE_URL` | `http://211.188.81.250:30402/v1` | OpenAI 호환 API 주소 |
| `OPENAI_MODEL` | `HCX-GOV-THINK-V1-32B` | 기본 모델 |
| `OPENAI_API_KEY` | `unused` | 필요 시 API 키 |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama 서버 주소 |
| `OLLAMA_MODEL` | `qwen2.5-coder:14b-instruct` | Ollama 모델 |
| `BOK_USE_LIVE_CATALOG` | `1` | live catalog 사용 여부 |
| `BOK_USE_KEY_BINDING` | `1` | 규칙 행 key binding 사용 여부 |
| `BOK_QUERY_TRACE_DIR` | unset | query trace 저장 경로 |
| `BOK_FAILURE_TRACE_DIR` | unset | 실패 artifact 저장 경로 |

## 한계

- TypeDB와 Neo4j의 복합질문 안정성은 retrieval-guided planner와 규칙 템플릿에 일부 의존합니다.
- Context 경로는 비교용 기준선이므로 복잡한 계산형 질문에서는 문서 전처리 품질과 프롬프트 제약에 크게 좌우됩니다.
- 일부 고난도 산술 질의는 아직 별도 템플릿 확장이 필요합니다.
