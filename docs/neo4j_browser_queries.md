# Neo4j Browser Sample Queries

Neo4j Browser: `http://localhost:7474`

로그인 정보:
- ID: `neo4j`
- PW: `password`

## 1. 스키마 시각화

```cypher
CALL db.schema.visualization()
```

## 2. 전체 노드 수 확인

```cypher
MATCH (n)
RETURN labels(n) AS labels, count(*) AS cnt
ORDER BY cnt DESC
```

## 3. 3급과 연결된 호봉 일부 보기

```cypher
MATCH (g:직급 {직급코드: '3급'})-[r:호봉체계구성]->(h:호봉)
RETURN g, r, h
ORDER BY h.호봉번호 ASC
LIMIT 20
```

## 4. 팀장 3급 직책급 확인

```cypher
MATCH (pp:직책급기준)-[:해당직급]->(g:직급 {직급코드: '3급'})
MATCH (pp)-[:해당직위]->(p:직위 {직위명: '팀장'})
RETURN p.직위명 AS position, g.직급코드 AS grade, pp.직책급액 AS amount
```

## 5. 부서장(가) EX 평가상여금 지급률 확인

```cypher
MATCH (b:상여금기준)-[:해당직책구분]->(p:직위 {직위명: '부서장(가)'})
MATCH (b)-[:해당등급]->(e:평가결과 {평가등급: 'EX'})
RETURN p.직위명 AS position, e.평가등급 AS eval, b.상여금지급률 AS bonus_rate
```

## 6. 1급 연봉상한액 확인

```cypher
MATCH (c:연봉상한액기준)-[:해당직급]->(g:직급 {직급코드: '1급'})
RETURN g.직급코드 AS grade, c.연봉상한액 AS annual_cap
```

## 7. 미국 1급 국외본봉 확인

```cypher
MATCH (o:국외본봉기준 {국가명: '미국'})-[:해당직급]->(g:직급 {직급코드: '1급'})
RETURN o.국가명 AS country, g.직급코드 AS grade, o.국외기본급액 AS amount, o.통화단위 AS currency
```

## 8. 임금피크제 2년차 지급률 확인

```cypher
MATCH (w:임금피크제기준 {적용연차: 2})
RETURN w.적용연차 AS year, w.임금피크지급률 AS rate
```

## 9. 복합 보수 질의 예시

```cypher
MATCH (grade:직급 {직급코드: '3급'})-[:호봉체계구성]->(step:호봉)
MATCH (pos:직위 {직위명: '팀장'})
MATCH (eval:평가결과 {평가등급: 'EX'})
MATCH (pp:직책급기준)-[:해당직급]->(grade), (pp)-[:해당직위]->(pos)
MATCH (b:상여금기준)-[:해당직책구분]->(pos), (b)-[:해당등급]->(eval)
MATCH (d:연봉차등액기준)-[:해당직급]->(grade), (d)-[:해당등급]->(eval)
MATCH (c:연봉상한액기준)-[:해당직급]->(grade)
RETURN step.호봉번호 AS n,
       step.호봉금액 AS salary,
       pp.직책급액 AS ppay,
       b.상여금지급률 AS brate,
       d.차등액 AS diff,
       c.연봉상한액 AS cap
ORDER BY n DESC
LIMIT 1
```

## 10. 조문 검색

```cypher
MATCH (a:조문)
WHERE a.조문내용 CONTAINS '상여금'
RETURN a.조번호 AS article_no, a.항번호 AS paragraph_no, a.조문내용 AS content
ORDER BY article_no ASC, paragraph_no ASC
```