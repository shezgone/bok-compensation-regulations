# Dual Graph Ontology Project Bootstrap Prompt

아래 프롬프트는 이 저장소와 유사한 구조의 새 프로젝트를 AI에게 처음부터 세팅시키기 위한 초기 지시문 템플릿입니다.

사용 방법:

1. 대괄호 플레이스홀더를 새 프로젝트 내용으로 바꿉니다.
2. AI 코딩 에이전트 또는 Copilot Chat의 첫 프롬프트로 넣습니다.
3. 초기 생성 후, 데이터 소스와 실제 용어에 맞춰 스키마와 적재 코드를 좁혀갑니다.

---

## Prompt Template

```text
Create a new repository for a dual-graph ontology project with the same overall structure and engineering style as a TypeDB + Neo4j knowledge graph system.

Project context:
- Domain: [DOMAIN_NAME]
- Source materials: [PDFS / regulations / manuals / structured tables / CSVs / notes]
- Goal: build a TypeDB ontology, a Neo4j mirror model, validation scripts, sample graph queries, and an optional local-LLM natural language query pipeline.
- Primary language: Python 3.9+
- Databases: TypeDB 3.x and Neo4j 5.x
- Optional NL stack: Ollama + LangGraph

Critical delivery approach:
- Do NOT attempt to model the entire customer problem space or all source documents in one giant first-pass schema.
- Use a divide-and-conquer workflow.
- Start from the smallest coherent business slice that can be validated end-to-end.
- Expand the ontology incrementally only after each slice is validated against real source data.
- Prefer staged design with verification over broad speculative upfront modeling.

Create the repository with this structure:

[PROJECT_SLUG]/
├── README.md
├── pyproject.toml
├── docs/
│   ├── schema_diagram.md
│   ├── neo4j_schema_diagram.md
│   └── [original source documents or notes]
├── schema/
│   └── [domain_schema].tql
├── src/
│   ├── [typedb_package]/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── connection.py
│   │   ├── create_db.py
│   │   ├── load_schema.py
│   │   ├── insert_data.py
│   │   ├── check_db.py
│   │   ├── verify_schema.py
│   │   ├── sample_queries.py
│   │   ├── graph_query_demo.py
│   │   ├── langgraph_query.py
│   │   └── nl_query.py
│   └── [neo4j_package]/
│       ├── __init__.py
│       ├── config.py
│       ├── connection.py
│       ├── create_schema.py
│       ├── insert_data.py
│       ├── check_db.py
│       ├── graph_query_demo.py
│       ├── langgraph_query.py
│       └── nl_query.py
└── tests/
    ├── __init__.py
    ├── validate_data.py
    ├── test_nl_pipeline.py
    ├── test_nl_router.py
    └── test_typedb_router.py

Required design principles:

1. The TypeDB schema must model the domain using explicit entity, relation, and attribute types.
2. Avoid shared primitive attributes that create hub-like anti-patterns across unrelated entities.
3. Prefer owner-scoped attribute names when the same primitive concept appears in multiple contexts.
4. Model true multi-party business rules as TypeDB relations with named roles.
5. Mirror the same business meaning in Neo4j, even if N-ary relations must be decomposed into node + edge patterns.
6. Keep naming consistent between TypeDB and Neo4j as much as possible.
7. Separate “relation-driven lookup tables” from “standalone lookup entities” in both code and docs.
8. Make the codebase easy to validate and inspect without an LLM.
9. Optimize for human maintainability so engineers can understand, review, and customize the AI-designed schema.

Required execution methodology:

1. Do not design the whole ontology in one shot.
- Break the domain into business slices.
- Examples: document structure, classification hierarchy, lookup tables, amount/rate rules, eligibility rules, exception rules, historical revisions.

2. Use divide and conquer.
- Build each slice independently enough that it can be loaded, queried, and validated.
- Merge slices only after names, ownership, and relation semantics are clear.

3. Use a TDD-like modeling workflow.
- Before expanding the schema, define expected facts and representative business questions.
- Add validation checks for each slice.
- Implement schema and insert logic to satisfy those checks.
- Refactor only after tests and validation data pass.

4. Validate against real source data at every step.
- Do not trust an elegant schema that has not been checked against actual examples.
- Prefer a smaller proven model over a larger speculative model.

5. Favor schema evolution over schema big-bang design.
- Initial version should be minimal but correct.
- Add entities, relations, or owner-scoped attributes only when a new business question or source fact requires them.

6. Keep the model reviewable by humans.
- Every major relation should have a plain-language explanation.
- Every important entity should have a short description of what real-world thing or table row it represents.
- The repository should make it easy to see why a modeling choice exists.

Implementation requirements:

1. README.md
- Write a concise project description.
- Explain the dual TypeDB + Neo4j architecture.
- Include setup instructions for Docker, Python environment, and optional Ollama integration.
- Include a project tree.
- Include Mermaid diagrams for TypeDB and links to docs/schema_diagram.md and docs/neo4j_schema_diagram.md.
- Include validation and test commands.

2. pyproject.toml
- Use setuptools with src layout.
- Base dependency: typedb-driver.
- Optional extras:
  - dev: pytest
  - neo4j: neo4j driver
  - llm: langchain-core, langchain-ollama, langgraph
  - full: union of the above

3. TypeDB package
- config.py: dataclass-based environment config
- connection.py: reusable TypeDB driver factory
- create_db.py: create database and load schema
- insert_data.py: insert normalized sample/domain data
- check_db.py: quick counts and sanity checks
- verify_schema.py: smoke checks for schema validity
- sample_queries.py: small manual read examples
- graph_query_demo.py: a representative multi-hop graph query
- langgraph_query.py: LangGraph-based NL workflow
- nl_query.py: thin compatibility wrapper around the NL path or core query helpers

4. Neo4j package
- config.py and connection.py following the same style
- create_schema.py for constraints and indexes
- insert_data.py mirroring the TypeDB dataset semantically
- check_db.py and graph_query_demo.py for inspection and sample traversal
- langgraph_query.py and nl_query.py mirroring the TypeDB query-path architecture

5. Tests
- validate_data.py should compare expected source facts against both DBs.
- test_nl_pipeline.py should include direct-query checks and optional NL/E2E checks.
- Router tests should verify semantic vs data routing behavior without requiring live LLM calls.
- Tests should be organized so each business slice can be validated independently before full-suite execution.
- Add regression tests whenever the schema is normalized, renamed, split, or merged.

6. Documentation diagrams
- docs/schema_diagram.md should show the TypeDB ontology in a readable Mermaid diagram.
- docs/neo4j_schema_diagram.md should show how the same meaning is represented in Neo4j.
- Include short explanations for how to read each diagram.
- Include at least 2-3 example query paths from business question to schema path.

7. Human handoff documentation
- Produce documentation that helps an engineer understand and customize the AI-designed schema.
- Include:
  - a plain-language explanation of each major entity and relation
  - a distinction between core business axes and lookup/standard tables
  - explanation of owner-scoped attribute naming choices
  - example business questions mapped to schema/query paths
  - known modeling tradeoffs and open decisions

Data modeling guidance:

- Identify core document entities, classification axes, rule/decision relations, and lookup tables.
- Distinguish between:
  - document structure entities
  - organizational axes or classification entities
  - decision/standard entities holding amounts, rates, thresholds, dates, or conditions
- If two entities would otherwise share a generic attribute like code, name, rank, amount, rate, start date, end date, or cap, consider whether the attribute should be renamed into an owner-specific form.
- Use clear role names in TypeDB relations so queries read like business logic.
- Avoid creating abstract types that are not justified by actual source material or query needs.
- If a concept appears only as text in a document, do not automatically force it into a top-level entity unless validation and usage justify it.
- Prefer modeling from actual business questions backward, not from an imagined universal taxonomy forward.

Step-by-step modeling workflow:

1. Source decomposition
- Split the customer material into manageable sections.
- Identify which sections define structure, classification, calculations, eligibility, exceptions, or revisions.

2. Slice selection
- Choose the first slice that is both important and easy to validate.
- Example: start with document/article structure and one lookup table rather than all rules at once.

3. Fact extraction
- Write down the concrete facts that must exist in the database for that slice.
- Include example values, edge cases, and expected query outputs.

4. Validation-first design
- Create validation cases before or alongside schema expansion.
- The validation should answer: what must be true if the slice is modeled correctly?

5. Minimal schema implementation
- Add only the entities, relations, attributes, and roles necessary for that slice.
- Avoid premature generalization.

6. Query proof
- Add one or more sample queries that prove the slice is useful.
- Include both direct data lookups and, if relevant, semantic/document queries.

7. Refactor and normalize
- After a slice works, look for shared-attribute anti-patterns, unclear role names, or duplicated meanings.
- Normalize only once you have concrete evidence from data and tests.

8. Repeat for the next slice
- Keep a growing set of validation checks so previously modeled slices do not regress.

NL query pipeline guidance:

- Keep the NL system optional and separate from core validation.
- Support two broad intents:
  - semantic/document interpretation queries
  - data/amount/rate lookup queries
- For semantic queries, retrieve document/article text as context.
- For data queries, generate TypeQL or Cypher using schema-aware prompts.
- Keep the non-LLM direct-query path reliable and testable.

Coding style requirements:

- Use minimal, focused modules.
- Keep environment configuration centralized.
- Avoid stale sample code that diverges from the main schema.
- Prefer explicit names over clever abstractions.
- Add short comments only when needed to explain non-obvious logic.

Required engineer-facing deliverables:

1. A schema reading guide
- Explain how to read the ontology from top-level domain areas down to individual relations.

2. An entity/relation cheat sheet
- Summarize each important entity, relation, key attributes, and why it exists.

3. Query path examples
- Show how representative business questions traverse the schema.

4. Customization notes
- Identify where engineers should extend the schema when new source documents or rule tables are added.

5. Validation methodology notes
- Explain how to add new facts, new test cases, and new slices without breaking existing ones.

Deliverables:

1. Create all files with working starter content.
2. Add a small but coherent sample dataset.
3. Ensure the README matches the actual files.
4. Ensure tests and documentation refer to real entrypoints.
5. Include validation commands for both databases.
6. Make the initial scaffold clean enough that future schema normalization will be straightforward.
7. Include explicit incremental-design guidance in the documentation so future contributors do not revert to one-shot schema expansion.
8. Ensure the produced documentation is sufficient for an engineer to understand, review, and customize the AI-designed schema without reverse-engineering the whole codebase.

If any domain assumptions are missing, choose pragmatic defaults and clearly note them in the README.
```

---

## Recommended Placeholder Values

| Placeholder | Example |
|-------------|---------|
| `[DOMAIN_NAME]` | internal compensation regulations, procurement policy, academic regulations |
| `[PROJECT_SLUG]` | `acme-policy-ontology` |
| `[typedb_package]` | `acme_policy` |
| `[neo4j_package]` | `acme_policy_neo4j` |
| `[domain_schema]` | `policy_schema` |

## When To Use This Prompt

- 새 규정/정책/지침 온톨로지 프로젝트를 처음 세팅할 때
- TypeDB와 Neo4j를 병행 비교하는 지식그래프 저장소를 만들 때
- 문서 구조 + 기준표 + 다중 조건 결정 로직이 함께 있는 도메인을 모델링할 때
- 이후 LLM 질의까지 붙일 가능성이 있지만, 우선 스키마와 검증 체계를 먼저 잡고 싶을 때

## Recommended Working Style For The AI

- Think like a schema engineer, not a slide-maker.
- Do not over-model the customer domain in the first pass.
- Build, validate, inspect, and then expand.
- Treat every new business slice as a small project with its own facts, tests, and query proofs.
- Keep outputs legible enough that a human engineer can confidently review and modify them.

## What To Customize Immediately After Generation

1. 실제 도메인 용어로 스키마 타입 이름 바꾸기
2. 샘플 데이터 대신 실제 기준표/규정 구조 반영하기
3. validate_data.py의 기대값을 실제 문서 기준으로 다시 채우기
4. README 제목과 설명을 실제 프로젝트명에 맞게 교체하기
5. Mermaid 다이어그램을 실제 relation 구조에 맞게 다듬기