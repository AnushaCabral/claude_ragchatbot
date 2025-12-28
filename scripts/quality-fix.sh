#!/usr/bin/env bash
# Fix code quality issues automatically where possible

set -e

echo "🔧 Fixing code quality issues..."
echo ""

# Format code
echo "📦 Running isort..."
uv run isort backend/
echo "✅ Imports sorted"
echo ""

echo "🎨 Running black..."
uv run black backend/
echo "✅ Code formatted"
echo ""

# Run checks to see what's left
echo "🔍 Running remaining checks..."
echo ""

echo "📝 Running flake8..."
if uv run flake8 backend/; then
    echo "✅ Flake8 checks passed"
else
    echo "⚠️  Flake8 found issues that need manual fixing"
fi
echo ""

echo "🔬 Running mypy..."
if uv run mypy backend/; then
    echo "✅ Type checking passed"
else
    echo "⚠️  Mypy found issues that need manual fixing"
fi
echo ""

echo "✨ Auto-fixes complete! Check above for any remaining issues."
