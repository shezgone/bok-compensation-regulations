# 한국은행 보수규정 지식 그래프 (Neo4j LPG 대응도)

이 문서는 TypeDB 스키마가 Neo4j에서는 어떻게 펼쳐지는지 보여주는 대응 다이어그램입니다.

- TypeDB의 엔티티는 Neo4j 노드 레이블로 매핑됩니다.
- TypeDB의 N-ary relation은 Neo4j에서 중심 기준 노드와 여러 관계선으로 분해됩니다.
- 따라서 질의 흐름은 더 직선적으로 보이지만, 관계 의미는 애플리케이션 쿼리에서 보존해야 합니다.

```mermaid
flowchart TD
    classDef node fill:#1e3a8a,stroke:#93c5fd,stroke-width:2px,color:#ffffff;
    classDef hub fill:#9a3412,stroke:#fdba74,stroke-width:2px,color:#ffffff;
    classDef note fill:#f8fafc,stroke:#94a3b8,stroke-width:1.5px,color:#0f172a;

    subgraph 규정_영역["규정 노드"]
        direction LR
        Regulation["(:규정)\n규정번호, 규정명"]:::node
        Article["(:조문)\n조번호, 조문내용"]:::node
        History["(:개정이력)\n개정일"]:::node

        Regulation -->|규정구성| Article
        Regulation -->|규정개정| History
    end

    subgraph 인사_영역["인사 축 노드"]
        direction LR
        JobGroup["(:직렬)\n직렬코드, 직렬명"]:::node
        Rank["(:직급)\n직급코드, 직급서열"]:::node
        Position["(:직위)\n직위코드, 직위서열"]:::node
        Eval["(:평가결과)\n평가등급"]:::node

        JobGroup -->|직렬분류| Rank
    end

    subgraph 기준_노드["기준표 노드"]
        direction TB
        PayStep["(:호봉)\n호봉번호, 호봉금액"]:::hub
        InitStd["(:초임호봉기준)\n초임호봉번호"]:::hub
        PosPay["(:직책급기준)\n직책급액"]:::hub
        Bonus["(:상여금기준)\n상여금지급률"]:::hub
        Diff["(:연봉차등액기준)\n차등액"]:::hub
        Cap["(:연봉상한액기준)\n연봉상한액"]:::hub
        Overseas["(:국외본봉기준)\n국가명, 국외기본급액"]:::hub
        BasePay["(:보수기준)\n보수기본급액"]:::hub
        Allowance["(:수당)\n수당액, 수당지급률"]:::hub
        WagePeak["(:임금피크제기준)\n적용연차, 임금피크지급률"]:::hub
    end

    Rank -->|호봉체계구성| PayStep
    InitStd -->|대상직렬| JobGroup
    PosPay -->|해당직급| Rank
    PosPay -->|해당직위| Position
    Bonus -->|해당직책구분| Position
    Bonus -->|해당등급| Eval
    Diff -->|해당직급| Rank
    Diff -->|해당등급| Eval
    Cap -->|해당직급| Rank
    Overseas -->|해당직급| Rank

    Note["TypeDB에서는 relation 자체가 1급 요소이지만\nNeo4j에서는 기준 노드에서 각 축으로 관계가 퍼지는 형태로 구현됩니다."]:::note
    기준_노드 --- Note
```

## 읽는 방법

1. 파란 노드는 축 노드 또는 문서 노드입니다. `직급`, `직위`, `평가결과`, `직렬`이 여기에 해당합니다.
2. 주황 노드는 실제 금액/지급률/기준값을 가진 중심 노드입니다.
3. TypeDB의 `직책급결정(적용기준, 해당직급, 해당직위)`은 Neo4j에서 `(:직책급기준)-[:해당직급]->(:직급)` 과 `(:직책급기준)-[:해당직위]->(:직위)` 두 관계로 분해됩니다.
4. 그래서 Neo4j는 탐색은 단순하지만, 관계 의미를 쿼리에서 정확히 묶어야 합니다.

## TypeDB와 읽는 차이

| 관점 | TypeDB | Neo4j |
|------|--------|-------|
| 관계 표현 | relation 자체가 중심 | 기준 노드가 중심 |
| 질문 읽는 방식 | relation 역할을 찾는다 | 기준 노드에서 연결된 축을 찾는다 |
| 강점 | 의미 보존이 엄격함 | 시각화와 탐색이 직관적임 |

## 예시 질의 해석

`3급 팀장 EX 평가 상여금`을 읽을 때는 아래처럼 봅니다.

1. 기준 노드는 `(:상여금기준)` 입니다.
2. 여기에 `[:해당직책구분] -> (:직위 {직위명: '팀장'})` 이 연결됩니다.
3. 동시에 `[:해당등급] -> (:평가결과 {평가등급: 'EX'})` 이 연결됩니다.
4. 그 노드의 `상여금지급률` 속성을 읽으면 됩니다.