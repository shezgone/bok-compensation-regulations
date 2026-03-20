import os
import re

files_to_patch = [
    "src/bok_compensation_neo4j/insert_data.py",
    "src/bok_compensation_typedb/insert_data.py",
]

for file_path in files_to_patch:
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            content = f.read()

        # We want to change the standard SALARY_DIFF_TABLE, not the ADDENDUM_SALARY_DIFF.
        # Let's find SALARY_DIFF_TABLE explicitly and only replace inside it.
        start_idx = content.find("SALARY_DIFF_TABLE")
        end_idx = content.find("]", start_idx)
        
        target = content[start_idx:end_idx]
        
        # Replace only in target
        target = target.replace('("1급", "EX", 3672)', '("1급", "EX", 3500)')
        target = target.replace('("1급", "EE", 2448)', '("1급", "EE", 2300)')
        target = target.replace('("1급", "ME", 1224)', '("1급", "ME", 1100)')
        
        target = target.replace('("2급", "EX", 3348)', '("2급", "EX", 3200)')
        target = target.replace('("2급", "EE", 2232)', '("2급", "EE", 2100)')
        target = target.replace('("2급", "ME", 1116)', '("2급", "ME", 1000)')
        
        target = target.replace('("3급", "EX", 3024)', '("3급", "EX", 2900)')
        target = target.replace('("3급", "EE", 2016)', '("3급", "EE", 1900)')
        target = target.replace('("3급", "ME", 1008)', '("3급", "ME", 900)')

        content = content[:start_idx] + target + content[end_idx:]

        with open(file_path, "w") as f:
            f.write(content)
        print(f"Patched {file_path}")
