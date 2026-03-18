with open('app.py', 'r') as f:
    data = f.read()

old_block = '''                _render_result_card_summary(result.get("trace") or {})
                with st.expander("Trace"):
                    _render_trace(result.get("trace") or {})'''

new_block = '''                with st.expander("🔗 실행 체인 (Execution Flow)", expanded=True):
                    _render_execution_chain(result.get("trace") or {})'''

data = data.replace(old_block, new_block)

with open('app.py', 'w') as f:
    f.write(data)
