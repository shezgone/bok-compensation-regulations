# 한국은행 보수규정 지식 그래프 (TypeDB N-ary 하이퍼그래프)

```mermaid
graph TD
    %% 다크 모드/라이트 모드 모두에서 잘 보이도록 고대비 색상 적용
    classDef entity fill:#1a365d,stroke:#63b3ed,stroke-width:2px,color:#ffffff;
    classDef relation fill:#7b341e,stroke:#fbd38d,stroke-width:2px,color:#ffffff,shape:diamond;

    %% --------------------------------
    %% 1. 규정 체계 (Regulation System)
    %% --------------------------------
    subgraph 규정_체계["📜 규정 체계"]
        Regulation["규정"]:::entity
        Article["조문"]:::entity
        History["개정이력"]:::entity
        
        Rel_Comp{"규정구성<br/>(Relation)"}:::relation
        Rel_Rev{"규정개정<br/>(Relation)"}:::relation

        Regulation -->|상위규정| Rel_Comp
        Article -->|하위조문| Rel_Comp
        
        Regulation -->|대상규정| Rel_Rev
        History -->|이력| Rel_Rev
    end

    %% --------------------------------
    %% 2. 인사 체계 (HR System)
    %% --------------------------------
    subgraph 인사_체계["🧑‍💼 인사 체계"]
        JobGroup["직렬"]:::entity
        Rank["직급"]:::entity
        Position["직위"]:::entity
        
        Rel_Class{"직렬분류<br/>(Relation)"}:::relation
        JobGroup -->|분류직렬| Rel_Class
        Rank -->|분류직급| Rel_Class
    end

    %% --------------------------------
    %% 3. 보수 산정 기준 체계 (Compensation Standards)
    %% --------------------------------
    subgraph 보수_체계["💰 기준/지급액 체계"]
        PayStep["호봉"]:::entity
        PosPayStd["직책급기준\n(별표 1-1)"]:::entity
        InitStepStd["초임호봉기준\n(별표 2)"]:::entity
    end

    %% --------------------------------
    %% 4. N-ary(다항) 하이퍼그래프 릴레이션
    %% --------------------------------
    %% 호봉 체계 (2항)
    Rel_PayStep{"호봉체계구성<br/>(Relation)"}:::relation
    Rank -->|소속직급| Rel_PayStep
    PayStep -->|구성호봉| Rel_PayStep

    %% 초임호봉 결정 (2항 구조)
    Rel_InitStep{"초임호봉결정<br/>(Relation)"}:::relation
    JobGroup -->|대상직렬| Rel_InitStep
    InitStepStd -->|적용기준| Rel_InitStep

    %% [핵심] 직책급 결정 (3항 하이퍼그래프: 직급 + 직위 + 직책급기준 연결)
    Rel_PositionPay{"직책급결정<br/>(Hyper-Relation)"}:::relation
    Rank -->|해당직급| Rel_PositionPay
    Position -->|해당직위| Rel_PositionPay
    PosPayStd -->|적용기준| Rel_PositionPay
```