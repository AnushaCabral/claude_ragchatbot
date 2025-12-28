#!/usr/bin/env bash
# Format Python code with isort and black

set -e

echo "🔧 Formatting code..."
echo ""

echo "📦 Running isort..."
uv run isort backend/
echo "✅ Import sorting complete"
echo ""

echo "🎨 Running black..."
uv run black backend/
echo "✅ Code formatting complete"
echo ""

echo "✨ All formatting done!"
