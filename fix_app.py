import re

with open("app.py", "r") as f:
    content = f.read()

# Find _get_role_summary and _render_execution_chain
summary_start = content.find("def _get_role_summary(")
if summary_start != -1:
    funcs_content = content[summary_start:]
    main_content = content[:summary_start]
    
    # We want to insert 'funcs_content' before the main streamlit logic
    # Find a good spot, e.g., after ARCHITECTURES definition or 'def _run_base_llm(...):'
    
    insert_pos = main_content.find("st.set_page_config(")
    if insert_pos == -1:
        insert_pos = 0
        
    new_content = main_content[:insert_pos] + funcs_content + "\n\n" + main_content[insert_pos:]
    
    with open("app.py", "w") as f:
        f.write(new_content)
