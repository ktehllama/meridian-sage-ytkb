#!/bin/bash
# PostToolUse hook: syntax-check any .py file after Edit or Write
# Receives JSON on stdin with tool_name and tool_input

INPUT=$(cat)
FILE=$(echo "$INPUT" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))" 2>/dev/null)

# Only check Python files that exist
if [[ "$FILE" == *.py ]] && [[ -f "$FILE" ]]; then
    if python -m py_compile "$FILE" 2>&1; then
        echo "✓ Syntax OK: $FILE"
    else
        echo "✗ Syntax error in: $FILE"
        exit 2  # non-zero exit surfaces the error to Claude
    fi
fi
