#!/bin/bash
# Pre-commit linting and formatting checks

set -e

echo "Running code quality checks..."
echo ""

# Black - code formatting
echo "→ Running black (code formatter)..."
black --check claude_usage/ || {
    echo "❌ Black formatting failed. Run: black claude_usage/"
    exit 1
}
echo "✓ Black passed"
echo ""

# Ruff - fast Python linter
echo "→ Running ruff (linter)..."
ruff check claude_usage/ || {
    echo "❌ Ruff linting failed. Run: ruff check --fix claude_usage/"
    exit 1
}
echo "✓ Ruff passed"
echo ""

# MyPy - type checking
echo "→ Running mypy (type checker)..."
mypy claude_usage/ --ignore-missing-imports || {
    echo "❌ MyPy type checking failed. Fix type errors."
    exit 1
}
echo "✓ MyPy passed"
echo ""

echo "✅ All checks passed!"
