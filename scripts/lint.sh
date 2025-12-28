#!/usr/bin/env bash
# Run linting checks (flake8 and mypy)

set -e

echo "🔍 Running linting checks..."
echo ""

echo "📝 Running flake8..."
uv run flake8 backend/
echo "✅ Flake8 checks passed"
echo ""

echo "🔬 Running mypy..."
uv run mypy backend/
echo "✅ Type checking complete"
echo ""

echo "✨ All linting checks passed!"
