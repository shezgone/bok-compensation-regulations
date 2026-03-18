import logging
import os
import sys
import traceback

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from neo4j import GraphDatabase
from src.bok_compensation_neo4j.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
from src.bok_compensation_neo4j.insert_data import (
    SALARY_TABLE, POSITION_PAY_TABLE, BONUS_RATE_TABLE, SALARY_DIFF_TABLE, 
    SALARY_CAP_TABLE, WAGE_PEAK_TABLE
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CAREER_TRACKS = ["종합기획직원", "일반사무직원", "별정직원", "서무직원", "청원경찰"]

GRADES = [
    ("1급", "종합기획직원", 1), ("2급", "종합기획직원", 2), ("3급", "종합기획직원", 3),
    ("4급", "종합기획직원", 4), ("5급", "종합기획직원", 5), ("6급", "종합기획직원", 6),
    ("G1", "종합기획직원", 7), ("G2", "종합기획직원", 8), ("G3", "종합기획직원", 9),
    ("G4", "종합기획직원", 10), ("G5", "종합기획직원", 11),
    ("GA", "일반사무직원", 12), ("CL", "서무직원", 13), ("PO", "청원경찰", 14)
]

EVALUATIONS = [
    ("EX", 0.10, 2), ("EE", 0.25, 1), ("ME", 0.40, 1), 
    ("BE", 0.20, 0), ("NI", 0.05, 0)
]

POS_NAMES = {
    "P01": "부서장(가)", "P02": "부서장(나)", "P03": "국소속실장",
    "P04": "부장", "P05": "팀장", "P06": "반장", "P07": "조사역",
    "P08": "주임조사역(C1)", "P09": "조사역(C2)"
}

class GraphSchemaSeeder:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def wipe_database(self):
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
            logger.info("Wiped existing Neo4j database.")

    def insert_all_data(self):
        with self.driver.session() as session:
            # 1. Career Tracks
            for track in CAREER_TRACKS:
                session.run("MERGE (t:CareerTrack {name: $name})", name=track)

            # 2. Job Grades & relationship to CareerTrack
            for grade, t_name, order in GRADES:
                session.run("""
                MERGE (g:JobGrade {name: $grade}) SET g.order = $order WITH g
                MATCH (t:CareerTrack {name: $track}) MERGE (t)-[:HAS_GRADE]->(g)
                """, grade=grade, order=order, track=t_name)

            # 3. Base Salary Table
            for grade, data in SALARY_TABLE.items():
                start_step = data["start"]
                for i, amt in enumerate(data["amounts"]):
                    step = start_step + i
                    session.run("""
                    MATCH (g:JobGrade {name: $grade})
                    MERGE (b:BaseSalary {step: $step, amount: $amount})
                    MERGE (g)-[:HAS_BASE_SALARY {step: $step}]->(b)
                    """, grade=grade, step=step, amount=amt * 1000)

            # 4. Duty/Position Pay (직책급)
            for pos_code, grade, amt in POSITION_PAY_TABLE:
                duty_name = POS_NAMES.get(pos_code, pos_code)
                session.run("""
                MATCH (g:JobGrade {name: $grade})
                MERGE (p:DutyAllowance {code: $code, amount: $amount, grade: $grade, name: $duty})
                MERGE (g)-[:HAS_DUTY_ALLOWANCE]->(p)
                """, code=pos_code, grade=grade, amount=amt * 1000, duty=duty_name)

            # 5. Salary Caps (연봉상한)
            for grade, limit in SALARY_CAP_TABLE:
                code = f"CAP-{grade}"
                session.run("""
                MATCH (g:JobGrade {name: $grade})
                MERGE (s:SalaryLimit {amount: $limit, code: $code})
                MERGE (g)-[:HAS_SALARY_LIMIT]->(s)
                """, grade=grade, limit=limit * 1000, code=code)

            # 6. Evaluation Grades (평가등급)
            for eval_grade, dist_rate, num_steps in EVALUATIONS:
                session.run("MERGE (e:EvaluationGrade {name: $name, distribution_rate: $rate, steps: $steps})",
                            name=eval_grade, rate=dist_rate, steps=num_steps)

            # 7. Salary Differential (연봉차등)
            for grade, eval_g, amt_k in SALARY_DIFF_TABLE:
                code_val = f"DIFF-{grade}-{eval_g}"
                session.run("""
                MATCH (g:JobGrade {name: $grade})
                MATCH (e:EvaluationGrade {name: $eval_g})
                MERGE (e)-[:APPLIES_TO]->(g)
                MERGE (d:DifferentialAmount {amount: $amount, code: $code, grade: $grade})
                MERGE (e)-[:HAS_DIFFERENTIAL_AMOUNT {for_grade: $grade}]->(d)
                """, grade=grade, eval_g=eval_g, amount=amt_k * 1000, code=code_val)

            # 8. Wage Peak (임금피크제)
            for year, p_rate in WAGE_PEAK_TABLE:
                code = f"WP-{year}"
                session.run("MERGE (w:WagePeak {code: $code, year: $year, payout_rate: $prate})", 
                            code=code, year=year, prate=p_rate)

            # 9. Bonus Rates (상여금지급률)
            for pos_code, eval_g, rate in BONUS_RATE_TABLE:
                code = f"BONUS-EVAL-{pos_code}-{eval_g}"
                session.run("""
                MATCH (e:EvaluationGrade {name: $eval_g})
                MERGE (b:BonusRate {code: $code, rate: $rate})
                MERGE (e)-[:HAS_BONUS_RATE {for_duty: $pos_code}]->(b)
                """, eval_g=eval_g, code=code, rate=rate, pos_code=pos_code)

            logger.info("Loaded complete BOK Compensation rules into Neo4j successfully!")

if __name__ == "__main__":
    seeder = GraphSchemaSeeder(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    try:
        seeder.wipe_database()
        seeder.insert_all_data()
    except Exception as e:
        logger.error(f"Error seeding database: {e}")
        traceback.print_exc()
    finally:
        seeder.close()
