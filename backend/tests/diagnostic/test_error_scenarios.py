# backend/tests/diagnostic/test_error_scenarios.py
# Diagnostic tests for "not found" and "query failed" errors

import shutil
import tempfile
from unittest.mock import Mock, patch

import pytest
from search_tools import CourseSearchTool
from vector_store import VectorStore


class TestNotFoundErrors:
    """Diagnostic tests for 'not found' errors"""

    def test_course_not_found_empty_catalog(self, mock_config):
        """Test course resolution when catalog is empty"""
        temp_dir = tempfile.mkdtemp()
        try:
            empty_store = VectorStore(
                chroma_path=temp_dir,
                embedding_model=mock_config.EMBEDDING_MODEL,
                max_results=5,
            )

            # Try to resolve course in empty catalog
            resolved = empty_store._resolve_course_name("MCP")

            assert resolved is None, "Expected None for empty catalog"

            # Try to search with course filter
            results = empty_store.search(query="anything", course_name="MCP")

            assert results.error is not None, "Expected error for non-existent course"
            assert (
                "No course found" in results.error
            ), f"Expected 'No course found' in error, got: {results.error}"

            print(f"\n✓ Empty catalog error message: {results.error}")

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_course_not_found_via_search_tool(self, temp_chroma_db):
        """CRITICAL: End-to-end 'not found' error via CourseSearchTool"""
        tool = CourseSearchTool(temp_chroma_db)

        result = tool.execute(
            query="test query", course_name="This Course Does Not Exist"
        )

        # Should return error message, not raise exception
        assert isinstance(result, str), f"Expected string result, got {type(result)}"
        assert (
            "not found" in result.lower() or "No course found" in result
        ), f"Expected 'not found' in result, got: {result}"
        assert len(tool.last_sources) == 0, "Expected empty sources list on error"

        print(f"\n✓ CourseSearchTool error message: {result}")

    def test_empty_search_results(self, temp_chroma_db):
        """Test search that returns zero results"""
        tool = CourseSearchTool(temp_chroma_db)

        result = tool.execute(query="xyzabc123nonexistentquery", course_name=None)

        assert isinstance(result, str), f"Expected string result, got {type(result)}"
        assert (
            "No relevant content found" in result
        ), f"Expected 'No relevant content found', got: {result}"
        assert len(tool.last_sources) == 0, "Expected empty sources on no results"

        print(f"\n✓ Empty results message: {result}")


class TestQueryFailedErrors:
    """Diagnostic tests for 'query failed' errors"""

    @patch("vector_store.chromadb.PersistentClient")
    def test_chromadb_exception_handling(self, mock_chroma_client, mock_config):
        """Test how VectorStore handles ChromaDB exceptions"""
        # Mock ChromaDB to raise exception during search
        mock_collection = Mock()
        mock_collection.query.side_effect = Exception("ChromaDB connection error")

        mock_client_instance = Mock()
        mock_client_instance.get_or_create_collection.return_value = mock_collection
        mock_chroma_client.return_value = mock_client_instance

        store = VectorStore(
            chroma_path=mock_config.CHROMA_PATH,
            embedding_model=mock_config.EMBEDDING_MODEL,
            max_results=5,
        )

        results = store.search(query="test")

        # Should return SearchResults with error, not raise exception
        assert results.error is not None, "Expected error in results"
        assert (
            "Search error" in results.error
        ), f"Expected 'Search error', got: {results.error}"
        assert results.is_empty(), "Expected empty results on error"

        print(f"\n✓ ChromaDB exception handled: {results.error}")

    @patch("llm_providers.Groq")
    def test_provider_api_error_propagation(self, mock_groq_class, mock_config):
        """Test how provider errors propagate through system"""
        from llm_providers import GroqProvider

        # Mock Groq client to raise API error
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = Exception(
            "API rate limit exceeded"
        )
        mock_groq_class.return_value = mock_client

        provider = GroqProvider(
            api_key=mock_config.GROQ_API_KEY, model=mock_config.GROQ_MODEL
        )

        # Should raise exception (not caught at provider level)
        with pytest.raises(Exception) as exc_info:
            provider.generate_response(
                messages=[{"role": "user", "content": "test"}],
                system_prompt="test",
                tools=None,
            )

        assert (
            "rate limit" in str(exc_info.value).lower()
        ), f"Expected 'rate limit' in error, got: {exc_info.value}"

        print(f"\n✓ API error propagated: {exc_info.value}")


class TestToolCallParsing:
    """Test tool call format parsing between providers"""

    @patch("llm_providers.Groq")
    def test_groq_tool_call_parsing(self, mock_groq_class, mock_config):
        """Test Groq tool call JSON parsing"""
        import json

        from llm_providers import GroqProvider

        mock_client = Mock()

        # Create mock response with tool call
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].finish_reason = "tool_calls"
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = ""

        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function = Mock()
        mock_tool_call.function.name = "search_course_content"
        mock_tool_call.function.arguments = json.dumps(
            {"query": "MCP", "course_name": None, "lesson_number": None}
        )

        mock_response.choices[0].message.tool_calls = [mock_tool_call]
        mock_client.chat.completions.create.return_value = mock_response
        mock_groq_class.return_value = mock_client

        provider = GroqProvider(
            api_key=mock_config.GROQ_API_KEY, model=mock_config.GROQ_MODEL
        )

        response = provider.generate_response(
            messages=[{"role": "user", "content": "What is MCP?"}],
            system_prompt="test",
            tools=[
                {
                    "name": "search_course_content",
                    "description": "Search",
                    "input_schema": {"type": "object", "properties": {}},
                }
            ],
        )

        assert response.requires_tool_execution, "Expected tool execution required"
        assert (
            len(response.tool_calls) == 1
        ), f"Expected 1 tool call, got {len(response.tool_calls)}"
        assert response.tool_calls[0]["name"] == "search_course_content"
        assert response.tool_calls[0]["input"]["query"] == "MCP"
        assert response.tool_calls[0]["input"]["course_name"] is None

        print(f"\n✓ Groq tool call parsed correctly: {response.tool_calls[0]}")
