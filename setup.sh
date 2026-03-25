#!/bin/bash

# 에러 발생 시 즉시 중단
set -e

echo "🚀 [1/4] 데이터베이스(TypeDB, Neo4j) 컨테이너를 시작합니다..."
# Docker 데몬이 켜져있어야 합니다 (Docker Desktop 실행 필수)
docker compose up -d

echo "⏳ [2/4] 데이터베이스가 완전히 초기화될 때까지 15초간 대기합니다..."
sleep 15

echo "🐍 [3/4] 파이썬 환경 및 가상환경(.venv) 설정 중..."

# 파이썬 설치 여부 확인 및 자동 설치 시도 (Homebrew 활용)
if ! command -v python3 >/dev/null 2>&1; then
    echo "⚠️  시스템에 python3가 설치되어 있지 않습니다."
    
    if command -v brew >/dev/null 2>&1; then
        echo "🔄 Homebrew를 사용하여 python을 자동으로 설치합니다..."
        brew install python
    else
        echo "❌ Homebrew가 설치되어 있지 않아 파이썬을 자동으로 설치할 수 없습니다."
        echo "👉 Mac에 python3를 먼저 설치해 주세요! (https://www.python.org/downloads/mac-os/)"
        echo "👉 또는 Homebrew 설치: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        exit 1
    fi
fi

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[full]"

echo "🧠 [4/4] 지식 그래프 스키마 생성 및 기초 데이터를 주입합니다..."

# TypeDB 데이터 입력 및 초기화
echo "▶ (1/2) TypeDB 온톨로지 세팅 진행 중..."
python src/bok_compensation/create_db.py
python src/bok_compensation/insert_data.py

# Neo4j 데이터 입력 및 초기화
echo "▶ (2/2) Neo4j 지식 그래프 세팅 진행 중..."
python src/bok_compensation_neo4j/create_schema.py
python src/bok_compensation_neo4j/insert_data.py

echo ""
echo "================================================================="
echo "✅ 완벽하게 고객 테스트 환경 세팅이 완료되었습니다!"
echo "================================================================="
echo "웹 브라우저에서 챗봇 화면을 테스트하시려면 다음 명령어를 입력하세요:"
echo ""
echo "    source .venv/bin/activate"
echo "    streamlit run app.py"
echo ""
echo "웹 브라우저가 자동으로 열리며, 로컬 테스트 환경을 체험하실 수 있습니다."
echo "================================================================="
