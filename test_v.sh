python run_typedb_q4_verbose.py > output_verbose.txt 2>&1
cat output_verbose.txt | grep -E "(Tool |Result:|Final:)" -A 1
