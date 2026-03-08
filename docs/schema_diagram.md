# 한국은행 보수규정 지식 그래프 (TypeDB Schema)

```mermaid
graph TD
    %% 다크 모드/라이트 모드 모두에서 잘 보이도록 고대비 색상 적용
    classDef entity fill:#1a365d,stroke:#63b3ed,stroke-width:2px,color:#ffffff;
    classDef relation fill:#7b341e,stroke:#fbd38d,stroke-width:2px,color:#ffffff;

    %% --------------------------------
    %% 1. 규정 체계 (Regulation System)
    %% --------------------------------
    subgraph 규정_체계["📜 규정 체계"]
        Regulation["규정"]:::entity
        Article["조문"]:::entity
        History["개정이력"]:::entity
        
        Rel_Comp{"규정구성"}:::relation
        Rel_Rev{"규정개정"}:::relation

        Regulation -->|상위규정| Rel_Comp -->|하위조문| Article
        Regulation -->|대상규정| Rel_Rev -->|이력| History
    end

    %% --------------------------------
    %% 2. 인사 체계 (HR System)
    %% --------------------------------
    subgraph 인사_체계["🧑‍💼 인사 체계"]
        JobGroup["직렬"]:::entity
        Rank["직급"]:::entity
        Position["직위"]:::entity
        
        Rel_Class{"직렬분류"}:::relation
        JobGroup -->|분류직렬| Rel_Class -->|분류직급| Rank
    end

    %% --------------------------------
    %% 3. 보수 체계 (Compensation System)
    %% --------------------------------
    subgraph 보수_체계["💰 보수/지급 체계"]
        PayStep["호봉"]:::entity
        Allowance["수당"]:::entity
        BasePay["보수기준"]:::entity
    end

    %% --------------------------------
    %% 4. 교차 및 산정 매핑 (Relations)
    %% --------------------------------
    %% 호봉 관련
    Rel_PayStep{"호봉체계구성"}:::relation
    Rank -->|소속직급| Rel_PayStep -->|구성호봉| PayStep

    Rel_InitStep{"초임호봉결정\n(별표2)"}:::relation
    JobGroup -->|대상직렬| Rel_InitStep -.->|적용| PayStep

    %% 수당/상여금 관련
    Rel_PositionPay{"직책급결정\n(별표1-1)"}:::relation
    Rank -->|해당직급| Rel_PositionPay
    Position -->|해당직위| Rel_PositionPay
    Rel_PositionPay -.->|직책급액| Allowance

    Rel_Bonus{"상여금결정\n(별표1-2)"}:::relation
    Position -->|해당직책구분| Rel_Bonus -.->|상여지급률| Allowance

    %% 기본급/연봉/해외 관련
    Rel_SalaryDiff{"연봉차등\n(별표7)"}:::relation
    Rank -->|해당직급| Rel_SalaryDiff -.-> BasePay

    Rel_SalaryLimit{"연봉상한\n(별표8)"}:::relation
    Rank -->|해당직급| Rel_SalaryLimit -.-> BasePay

    Rel_Overseas{"국외본봉결정\n(별표1-5)"}:::relation
    Rank -->|해당직급| Rel_Overseas -.-> BasePay
```