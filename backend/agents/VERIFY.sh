#!/bin/bash

# Verification script for Traffic Intelligence Agent System
# Checks that all required files are present and valid

echo "=================================="
echo "Traffic Intelligence Agent System"
echo "Verification Script"
echo "=================================="
echo

AGENTS_DIR=$(pwd)
REQUIRED_FILES=(
    "__init__.py"
    "graph.py"
    "tools.py"
    "rag.py"
    "prompts.py"
    "config.py"
    "test_agent.py"
    "example_usage.py"
    "integration_example.py"
    "requirements.txt"
    "README.md"
    "IMPLEMENTATION_SUMMARY.md"
    "MANIFEST.md"
)

echo "Checking required files..."
echo

MISSING=0
for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        SIZE=$(wc -l < "$file" 2>/dev/null)
        printf "%-30s ✓ (%4d lines)\n" "$file" "$SIZE"
    else
        printf "%-30s ✗ MISSING\n" "$file"
        ((MISSING++))
    fi
done

echo
if [ $MISSING -eq 0 ]; then
    echo "Status: All files present ✓"
else
    echo "Status: $MISSING file(s) missing ✗"
fi

echo
echo "File Statistics:"
echo "================"
TOTAL_LINES=$(wc -l *.py *.md *.txt 2>/dev/null | tail -1 | awk '{print $1}')
echo "Total lines of code/docs: $TOTAL_LINES"

PY_FILES=$(find . -name "*.py" -type f | wc -l)
echo "Python files: $PY_FILES"

DOC_FILES=$(find . -name "*.md" -type f | wc -l)
echo "Documentation files: $DOC_FILES"

echo
echo "Python Syntax Check:"
echo "==================="
for file in *.py; do
    if python3 -m py_compile "$file" 2>/dev/null; then
        echo "✓ $file"
    else
        echo "✗ $file (syntax error)"
    fi
done

echo
echo "Dependencies:"
echo "============="
echo "Core Requirements:"
grep -E "^[a-z]" requirements.txt | head -6

echo
echo "Optional LLM Backends:"
grep -E "langchain-(openai|ollama)" requirements.txt

echo
echo "Installation Instructions:"
echo "=========================="
echo "1. Install dependencies:"
echo "   pip install -r requirements.txt"
echo
echo "2. Install optional LLM support:"
echo "   pip install langchain-openai     # For OpenAI"
echo "   pip install langchain-ollama     # For Ollama"
echo
echo "3. Set up configuration:"
echo "   cp .env.example .env"
echo "   export OPENAI_API_KEY=sk-..."
echo
echo "4. Run tests:"
echo "   pytest test_agent.py -v"
echo
echo "5. Run examples:"
echo "   python example_usage.py"
echo "   python integration_example.py"

echo
echo "=================================="
echo "Verification Complete"
echo "=================================="
