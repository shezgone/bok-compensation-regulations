#!/bin/bash

# 에러 발생 시 즉시 중단
set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

# ─────────────────────────────────────────────
# [0/5] 사전 점검: Docker / Python
# ─────────────────────────────────────────────
echo "🔎 [0/5] 사전 환경 점검..."

if ! command -v docker >/dev/null 2>&1; then
    echo "❌ Docker가 설치되어 있지 않습니다."
    echo "👉 Docker Desktop을 먼저 설치하세요: https://www.docker.com/products/docker-desktop/"
    echo "   (Graph DB 없이 Context RAG만 테스트하려면 README의 '3-B' 섹션을 참고하세요.)"
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    echo "❌ Docker 데몬이 실행 중이 아닙니다."
    echo "👉 Docker Desktop을 실행한 후 다시 시도하세요."
    exit 1
fi

# Python 설치 확인 및 자동 설치 시도 (Homebrew 활용)
if ! command -v python3 >/dev/null 2>&1; then
    echo "⚠️  시스템에 python3가 설치되어 있지 않습니다."
    if command -v brew >/dev/null 2>&1; then
        echo "🔄 Homebrew를 사용하여 python을 자동으로 설치합니다..."
        brew install python
    else
        echo "❌ Homebrew가 설치되어 있지 않아 파이썬을 자동으로 설치할 수 없습니다."
        echo "👉 https://www.python.org/downloads/ 에서 Python 3.9+를 설치하세요."
        exit 1
    fi
fi

# ─────────────────────────────────────────────
# [1/5] 환경설정 파일 생성 (.env, llm.py)
# ─────────────────────────────────────────────
echo ""
echo "⚙️  [1/5] 환경설정 파일 준비..."

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "  ▸ .env 생성됨 (.env.example 복사). LLM 엔드포인트를 수정하세요."
else
    echo "  ▸ .env 이미 존재 — 건너뜀."
fi

LLM_PY="src/bok_compensation_typedb/llm.py"
if [ ! -f "$LLM_PY" ]; then
    cp src/bok_compensation_typedb/llm_template.py "$LLM_PY"
    echo "  ▸ $LLM_PY 생성됨 (llm_template.py 복사)."
else
    echo "  ▸ $LLM_PY 이미 존재 — 건너뜀."
fi

# ─────────────────────────────────────────────
# [2/5] 데이터베이스 컨테이너 기동
# ─────────────────────────────────────────────
echo ""
echo "🚀 [2/5] TypeDB / Neo4j 컨테이너 기동..."
docker compose up -d

echo "⏳ DB 초기화 대기 (15초)..."
sleep 15

# ─────────────────────────────────────────────
# [3/5] Python 가상환경 + 의존성 설치
# ─────────────────────────────────────────────
echo ""
echo "🐍 [3/5] 가상환경(.venv) 및 의존성 설치..."

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[full]"

# ─────────────────────────────────────────────
# [4/5] TypeDB 스키마 + 데이터 적재
# ─────────────────────────────────────────────
echo ""
echo "🧠 [4/5] TypeDB 온톨로지 세팅..."
# create_db.py / insert_data.py는 상대 import(from .config)를 사용하므로
# 반드시 -m 모듈 형태로 실행해야 한다. PYTHONPATH는 프로젝트 루트.
export PYTHONPATH="$PROJECT_ROOT"
python -m src.bok_compensation_typedb.create_db
python -m src.bok_compensation_typedb.insert_data

# ─────────────────────────────────────────────
# [5/5] Neo4j 스키마 + 데이터 적재
# ─────────────────────────────────────────────
echo ""
echo "🧠 [5/5] Neo4j 지식 그래프 세팅..."
# insert_data.py가 wipe + 전체 시드(Cypher MERGE)를 수행한다.
# 별표 수치 데이터는 data_tables.py에서 import.
python src/bok_compensation_neo4j/insert_data.py

# ─────────────────────────────────────────────
# 완료
# ─────────────────────────────────────────────
echo ""
echo "================================================================="
echo "✅ 설치 완료"
echo "================================================================="
echo ""
echo "1) .env 파일에 LLM 엔드포인트(OPENAI_BASE_URL/MODEL/API_KEY)를 입력하세요."
echo "2) 웹 UI 실행:"
echo ""
echo "    source .venv/bin/activate"
echo "    streamlit run app.py"
echo ""
echo "================================================================="
