# 한국은행 보수규정 지식 그래프 (TypeDB N-ary 하이퍼그래프)

이 문서는 TypeDB 스키마를 사람이 빠르게 읽기 위한 해설용 다이어그램입니다.

- 위쪽 메인 다이어그램: 전체 구조
- 중간 속성 요약: 엔티티별 핵심 속성
- 아래 질의 경로 다이어그램: 실제 질문이 어떤 relation을 타는지 예시

```mermaid
flowchart TD
    %% 🎨 노드 스타일 정의 (Tailwind 기반 모던 컬러)
    classDef doc fill:#F1F5F9,stroke:#475569,stroke-width:2px,color:#0F172A,font-weight:bold,rx:5,ry:5
    classDef entity fill:#EFF6FF,stroke:#2563EB,stroke-width:2px,color:#1E3A8A,font-weight:bold,rx:8,ry:8
    classDef relation fill:#FEF3C7,stroke:#D97706,stroke-width:2px,color:#92400E,font-weight:bold
    classDef note fill:#F8FAFC,stroke:#94A3B8,stroke-width:1.5px,color:#334155,stroke-dasharray: 5 5

    subgraph Legend["💡 범례 (Legend)"]
        direction LR
        L1["엔티티 (실체/기준표)"]:::entity
        L2{"관계 (N-ary relation)"}:::relation
        L3["단독 기준 엔티티"]:::note
    end

    subgraph 규정_체계["🏛️ 1. 규정 체계 (Regulation Structure)"]
        direction LR
        Regulation["📜 규정\nkey: 규정번호\nprops: 규정명, 시행일"]:::doc
        Rel_Comp{"구성\n관계"}:::relation
        Article["📄 조문 (본문)\n조/항/호번호\nprops: 조문내용"]:::doc
        Addendum["📑 부칙 (경과조치)\nprops: 부칙내용"]:::doc
        Rel_Rev{"개정\n관계"}:::relation
        History["⏳ 개정이력\n개정일\nprops: 이력설명"]:::doc
        Rel_Override{"규정_대체\n(Override)"}:::relation

        Regulation ===>|상위규정| Rel_Comp ===>|하위조문| Article
        Regulation --->|대상규정| Rel_Rev --->|이력| History
        Article -. 구 규정 .-x Rel_Override
        Addendum === 신 규정 ===> Rel_Override
    end

    subgraph 인사_체계["👤 2. 인사 체계 (HR Axis)"]
        direction LR
        JobGroup["💼 직렬\nkey: 직렬코드"]:::entity
        Rel_Class{"직렬\n분류"}:::relation
        Rank["🏅 직급\nkey: 직급코드"]:::entity
        Position["🎯 직위\nkey: 직위코드"]:::entity
        Eval["📈 평가결과\nkey: 평가등급"]:::entity

        JobGroup --->|분류직렬| Rel_Class --->|분류직급| Rank
    end

    subgraph 기준_엔티티["💰 3. 보수 기준 엔티티 (Compensation Standards)"]
        direction TB

        subgraph 관계형_기준["🔗 관계형 기준표"]
            direction LR
            PayStep["호봉\nprops: 호봉번호, 금액"]:::entity
            InitStepStd["초임호봉기준"]:::entity
            PosPayStd["직책급기준\nprops: 직책급액"]:::entity
            BonusStd["상여금기준\nprops: 지급률"]:::entity
            SalDiffStd["연봉차등액기준\nprops: 차등액"]:::entity
            SalCapStd["연봉상한액기준\nprops: 상한액"]:::entity
            OverseasStd["국외본봉기준\nprops: 기본급액"]:::entity
        end

        subgraph 단독_기준["📌 단독 조회 기준표"]
            direction LR
            BasePay["보수기준\nprops: 보수기본급액"]:::entity
            Allowance["수당\nprops: 수당액, 지급률"]:::entity
            WagePeakStd["임금피크제기준\nprops: 연차, 지급률"]:::entity
            StandaloneNote["별도 relation 없이\n속성 자체를 직접 조회"]:::note

            BasePay ~~~ StandaloneNote
            Allowance ~~~ StandaloneNote
            WagePeakStd ~~~ StandaloneNote
        end
    end

    %% 그룹 간 흐름 정렬을 위한 안보이는 연결선
    Legend ~~~ 규정_체계
    규정_체계 ~~~ 인사_체계
    인사_체계 ~~~ 기준_엔티티

    subgraph 핵심_결정_관계["⚙️ 4. 핵심 결정 관계 (N-ary Mappings)"]
        direction TB
        Rel_PayStep{"호봉체계\n구성"}:::relation
        Rel_InitStep{"초임호봉\n결정"}:::relation
        Rel_PositionPay{"직책급\n결정"}:::relation
        Rel_Bonus{"상여금\n결정"}:::relation
        Rel_SalDiff{"연봉\n차등"}:::relation
        Rel_SalCap{"연봉\n상한"}:::relation
        Rel_Overseas{"국외본봉\n결정"}:::relation
    end

    %% 관계 매핑 (가독성을 위한 선 최소화)
    Rank ---> Rel_PayStep ---> PayStep
    JobGroup ---> Rel_InitStep ---> InitStepStd
    
    Rank ---> Rel_PositionPay
    Position ---> Rel_PositionPay ---> PosPayStd

    Position ---> Rel_Bonus
    Eval ---> Rel_Bonus ---> BonusStd

    Rank ---> Rel_SalDiff
    Eval ---> Rel_SalDiff ---> SalDiffStd

    Rank ---> Rel_SalCap ---> SalCapStd
    Rank ---> Rel_Overseas ---> OverseasStd

    %% 🎨 서브그래프 스타일 직접 적용
    style Legend fill:#FFFFFF,stroke:#E2E8F0,stroke-width:1px,rx:10,ry:10
    style 규정_체계 fill:#FFFFFF,stroke:#CBD5E1,stroke-width:2px,rx:10,ry:10
    style 인사_체계 fill:#F8FAFC,stroke:#93C5FD,stroke-width:2px,rx:10,ry:10
    style 핵심_결정_관계 fill:#FFFBEB,stroke:#FDE68A,stroke-width:2px,rx:10,ry:10
    style 기준_엔티티 fill:#F0FDF4,stroke:#BBF7D0,stroke-width:2px,rx:10,ry:10
```

## 읽는 방법

1. 위에서 아래로 읽습니다. `규정 체계`는 법문 구조, `인사 체계`는 사람 분류 축, `보수 기준 엔티티`는 금액/지급률 표입니다.
2. 마름모는 계산 또는 매핑 규칙이 들어가는 관계입니다. 예를 들어 `직책급결정`은 `직급 + 직위 + 직책급기준`을 한 번에 묶습니다.
3. `단독 조회 기준표`는 별도 relation 없이 속성만 직접 읽는 lookup 엔티티입니다. `보수기준`, `수당`, `임금피크제기준`이 여기에 해당합니다.
4. 질문을 스키마에 대응시킬 때는 먼저 기준 엔티티를 찾고, 그 다음 관계 마름모를 따라 필요한 축(`직급`, `직위`, `평가결과`, `직렬`)을 붙이면 됩니다.

## 엔티티 빠른 해설

| 구역 | 엔티티 | 핵심 속성 | 읽는 포인트 |
|------|--------|-----------|-------------|
| 규정 체계 | 규정 | `규정번호`, `규정명`, `시행일` | 전체 문서의 루트입니다. |
| 규정 체계 | 조문 | `조번호`, `항번호`, `호번호`, `조문내용` | 규정 해석 질의의 컨텍스트 원문입니다. |
| 규정 체계 | 부칙 | `부칙내용` | 경과조치 등 예외 사항이며 `규정_대체`를 통해 조문을 오버라이드합니다. |
| 인사 체계 | 직렬 | `직렬코드`, `직렬명` | 초임호봉 결정의 출발 축입니다. |
| 인사 체계 | 직급 | `직급코드`, `직급명`, `직급서열` | 본봉, 직책급, 연봉차등, 상한, 국외본봉의 공통 축입니다. |
| 인사 체계 | 직위 | `직위코드`, `직위명`, `직위서열` | 직책급, 상여금의 공통 축입니다. |
| 인사 체계 | 평가결과 | `평가등급`, `승급호봉수`, `배분율` | 상여금과 연봉차등의 공통 축입니다. |
| 기준표 | 호봉 | `호봉번호`, `호봉금액` | 직급별 본봉표의 실제 금액 행입니다. |
| 기준표 | 직책급기준 | `직책급액` | `직급 + 직위` 조합으로 결정됩니다. |
| 기준표 | 상여금기준 | `상여금지급률`, `연간지급률` | `직위 + 평가등급` 조합으로 결정됩니다. |
| 기준표 | 연봉차등액기준 | `차등액` | `직급 + 평가등급` 조합으로 결정됩니다. |
| 기준표 | 연봉상한액기준 | `연봉상한액` | 직급별 상한 lookup 입니다. |
| 기준표 | 국외본봉기준 | `국가명`, `국외기본급액`, `통화단위` | `국가 + 직급` 기준표입니다. |
| 단독 조회 | 보수기준 | `보수기본급액` | 임원급 기본 보수표입니다. |
| 단독 조회 | 수당 | `수당액`, `수당지급률`, `지급조건` | relation 없이 조건/금액을 직접 읽습니다. |
| 단독 조회 | 임금피크제기준 | `적용연차`, `임금피크지급률` | 연차별 지급률 lookup 입니다. |

## 질의 경로 예시

### 1. 3급 팀장 EX 평가 총보수 질의 경로

```mermaid
flowchart LR
    classDef axis fill:#0f766e,stroke:#99f6e4,stroke-width:2px,color:#ffffff;
    classDef rel fill:#b45309,stroke:#fde68a,stroke-width:2px,color:#ffffff,shape:diamond;
    classDef std fill:#1d4ed8,stroke:#93c5fd,stroke-width:2px,color:#ffffff;

    G["직급: 3급"]:::axis
    P["직위: 팀장"]:::axis
    E["평가: EX"]:::axis
    H{"호봉체계구성"}:::rel
    PP{"직책급결정"}:::rel
    B{"상여금결정"}:::rel
    D{"연봉차등"}:::rel
    C{"연봉상한"}:::rel
    Step["호봉"]:::std
    PosStd["직책급기준"]:::std
    Bonus["상여금기준"]:::std
    Diff["연봉차등액기준"]:::std
    Cap["연봉상한액기준"]:::std

    G --> H --> Step
    G --> PP
    P --> PP --> PosStd
    P --> B
    E --> B --> Bonus
    G --> D
    E --> D --> Diff
    G --> C --> Cap
```

### 2. 종합기획직렬 초임호봉 질의 경로

```mermaid
flowchart LR
    classDef axis fill:#0f766e,stroke:#99f6e4,stroke-width:2px,color:#ffffff;
    classDef rel fill:#b45309,stroke:#fde68a,stroke-width:2px,color:#ffffff,shape:diamond;
    classDef std fill:#1d4ed8,stroke:#93c5fd,stroke-width:2px,color:#ffffff;

    J["직렬: 종합기획직원"]:::axis
    Init{"초임호봉결정"}:::rel
    InitStd["초임호봉기준"]:::std
    G["직급"]:::axis
    Pay{"호봉체계구성"}:::rel
    Step["호봉"]:::std

    J --> Init --> InitStd
    G --> Pay --> Step
```

### 3. 미국 1급 국외본봉 질의 경로

```mermaid
flowchart LR
    classDef axis fill:#0f766e,stroke:#99f6e4,stroke-width:2px,color:#ffffff;
    classDef rel fill:#b45309,stroke:#fde68a,stroke-width:2px,color:#ffffff,shape:diamond;
    classDef std fill:#1d4ed8,stroke:#93c5fd,stroke-width:2px,color:#ffffff;

    G["직급: 1급"]:::axis
    O{"국외본봉결정"}:::rel
    Std["국외본봉기준\n국가명=미국"]:::std

    G --> O --> Std
```

## 해석 팁

1. 금액/지급률 질의는 먼저 어떤 기준표를 읽는지 찾고, 그 기준표를 relation이 요구하는 축으로 역추적하면 됩니다.
2. `직급 + 직위`, `직위 + 평가등급`, `직급 + 평가등급`처럼 축이 2개 이상이면 거의 항상 relation 마름모를 거칩니다.
3. 반대로 `보수기준`, `수당`, `임금피크제기준`처럼 엔티티 자체 속성을 직접 읽는 경우는 relation이 필요 없습니다.
4. 조문 해석 질의는 금액 표보다 `규정 -> 조문` 구조가 핵심이며, NL 파이프라인도 이 구조를 컨텍스트로 사용합니다.