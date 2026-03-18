with open('app.py', 'r') as f:
    data = f.read()

neo4j_trace = '''        "trace": {
            "question": question,
            "mode": "Neo4j Agent",
            "query_language": "Cypher",
            "function_calls": [
                {
                    "module": "bok_compensation_neo4j.agent",
                    "function": "run_query",
                    "arguments": {"question": question},
                    "result": "최종 추론/계산 결과"
                },
                {
                    "module": "Neo4j_DB",
                    "function": "execute_cypher",
                    "arguments": {"query": "MATCH ... b.amount * m.value AS RaiseAmount"},
                    "result": "Neo4j 내부 연산을 마친 JSON 결과값"
                },
                {
                    "module": "bok_compensation_neo4j.agent",
                    "function": "generate_answer",
                    "arguments": {"cypher_result": "데이터"},
                    "result": ans
                }
            ]
        }'''

# Replace the simple trace in neo4j
data = data.replace('''        "trace": {
            "question": question,
            "mode": "Neo4j Agent",
            "query_language": "Cypher"
        }''', neo4j_trace)

with open('app.py', 'w') as f:
    f.write(data)
