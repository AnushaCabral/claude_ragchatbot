#!/usr/bin/env bash
# Run all code quality checks

set -e

echo "🚀 Running full code quality suite..."
echo ""

# Check if code is formatted
echo "🔍 Checking code formatting..."
if ! uv run black --check backend/; then
    echo "❌ Code is not formatted. Run './scripts/format.sh' to fix."
    exit 1
fi

if ! uv run isort --check-only backend/; then
    echo "❌ Imports are not sorted. Run './scripts/format.sh' to fix."
    exit 1
fi
echo "✅ Code formatting is correct"
echo ""

# Run linting
echo "📝 Running flake8..."
uv run flake8 backend/
echo "✅ Flake8 checks passed"
echo ""

echo "🔬 Running mypy..."
uv run mypy backend/
echo "✅ Type checking complete"
echo ""

# Run tests if available
if [ -d "backend/tests" ] && [ "$(find backend/tests -name 'test_*.py' -type f | wc -l)" -gt 0 ]; then
    echo "🧪 Running tests..."
    uv run pytest backend/tests/ -v
    echo "✅ Tests passed"
    echo ""
fi

echo "✨ All quality checks passed! 🎉"
