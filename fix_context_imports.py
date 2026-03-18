import os
import glob

def find_and_replace_in_files(directory, old_str, new_str):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                with open(filepath, 'r') as f:
                    content = f.read()
                if old_str in content:
                    print(f"Updating {filepath}")
                    content = content.replace(old_str, new_str)
                    with open(filepath, 'w') as f:
                        f.write(content)

find_and_replace_in_files('src/bok_compensation_context', 'from bok_compensation.', 'from bok_compensation_typedb.')
find_and_replace_in_files('src/bok_compensation_context', 'import bok_compensation.', 'import bok_compensation_typedb.')

