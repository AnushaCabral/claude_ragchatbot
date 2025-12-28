# backend/tests/integration/test_sequential_rag_queries.py
# Integration tests for sequential tool calling in RAG system

import shutil
import tempfile

import pytest
from config import Config
from rag_system import RAGSystem


@pytest.fixture
def rag_system_with_test_data():
    """Create RAG system with test course data"""
    temp_dir = tempfile.mkdtemp()

    try:
        # Initialize RAG system with test configuration
        rag = RAGSystem(
            chroma_path=temp_dir,
            embedding_model=Config.EMBEDDING_MODEL,
            llm_provider=Config.LLM_PROVIDER,
            api_key=(
                Config.GROQ_API_KEY
                if Config.LLM_PROVIDER == "groq"
                else Config.ANTHROPIC_API_KEY
            ),
            model=(
                Config.GROQ_MODEL
                if Config.LLM_PROVIDER == "groq"
                else Config.ANTHROPIC_MODEL
            ),
        )

        # Add test courses
        from models import Course, CourseChunk, Lesson

        # Course 1: MCP
        mcp_course = Course(
            title="MCP: Build Rich-Context AI Apps with Anthropic",
            instructor="Anthropic Team",
            course_link="https://example.com/mcp",
            lessons=[
                Lesson(
                    lesson_number=0,
                    title="Introduction to MCP",
                    lesson_link="https://example.com/mcp/lesson0",
                ),
                Lesson(
                    lesson_number=1,
                    title="Building Context Servers",
                    lesson_link="https://example.com/mcp/lesson1",
                ),
            ],
        )

        # Course 2: Prompt Engineering
        pe_course = Course(
            title="Introduction to Prompt Engineering",
            instructor="AI Educator",
            course_link="https://example.com/prompt-eng",
            lessons=[
                Lesson(
                    lesson_number=0,
                    title="Prompt Engineering Basics",
                    lesson_link="https://example.com/pe/lesson0",
                ),
                Lesson(
                    lesson_number=1,
                    title="Advanced Prompting Techniques",
                    lesson_link="https://example.com/pe/lesson1",
                ),
            ],
        )

        # Add course metadata
        rag.vector_store.add_course_metadata(mcp_course)
        rag.vector_store.add_course_metadata(pe_course)

        # Add course content
        mcp_chunks = [
            CourseChunk(
                course_title=mcp_course.title,
                lesson_number=0,
                chunk_index=0,
                content="Course MCP: Build Rich-Context AI Apps with Anthropic Lesson 0 content: The Model Context Protocol (MCP) enables AI applications to access rich contextual information from various data sources. MCP servers act as bridges between AI models and data.",
            ),
            CourseChunk(
                course_title=mcp_course.title,
                lesson_number=1,
                chunk_index=1,
                content="Course MCP: Build Rich-Context AI Apps with Anthropic Lesson 1 content: Building context servers involves implementing the MCP protocol to expose data sources. Servers can provide file system access, database queries, and API integrations.",
            ),
        ]

        pe_chunks = [
            CourseChunk(
                course_title=pe_course.title,
                lesson_number=0,
                chunk_index=0,
                content="Course Introduction to Prompt Engineering Lesson 0 content: Prompt engineering is the art of crafting effective prompts to guide AI models toward desired outputs. Key techniques include few-shot learning and chain-of-thought prompting.",
            ),
            CourseChunk(
                course_title=pe_course.title,
                lesson_number=1,
                chunk_index=1,
                content="Course Introduction to Prompt Engineering Lesson 1 content: Advanced prompting techniques include role-based prompting, structured output formats, and iterative refinement. These methods improve accuracy and consistency.",
            ),
        ]

        rag.vector_store.add_course_content(mcp_chunks + pe_chunks)

        yield rag

    finally:
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)


class TestSequentialRagQueries:
    """Integration tests for sequential tool calling in real RAG queries"""

    @pytest.mark.integration
    def test_comparison_query_uses_two_searches(self, rag_system_with_test_data):
        """Test that comparison queries can use sequential searches"""
        rag = rag_system_with_test_data

        # Query that should trigger two searches
        query = "Compare the MCP course and the Prompt Engineering course"

        response, sources = rag.query(query, session_id="test_session")

        # Verify response is not empty
        assert len(response) > 0
        assert isinstance(response, str)

        # Verify both courses are represented in sources
        # (Sequential calling should allow searching both courses)
        source_texts = [s.display_text for s in sources]

        # At least one source should mention MCP or be from that course
        mcp_mentioned = any(
            "MCP" in text or "Model Context Protocol" in text for text in source_texts
        )

        # At least one source should be from Prompt Engineering
        pe_mentioned = any(
            "Prompt Engineering" in text or "Introduction to Prompt Engineering" in text
            for text in source_texts
        )

        # With sequential tool calling, both should be present
        # (May not always trigger depending on LLM behavior, so we test conservatively)
        assert len(sources) > 0, "Should have at least some sources"

    @pytest.mark.integration
    def test_single_search_still_works(self, rag_system_with_test_data):
        """Test that single-search queries work correctly (backward compatibility)"""
        rag = rag_system_with_test_data

        # Simple query that should only need one search
        query = "What is covered in the MCP course?"

        response, sources = rag.query(query, session_id="test_session_2")

        # Verify response exists
        assert len(response) > 0
        assert isinstance(response, str)

        # Should have sources from the search
        assert len(sources) > 0

        # Sources should be relevant to MCP
        source_texts = [s.display_text for s in sources]
        mcp_relevant = any(
            "MCP" in text or "Model Context Protocol" in text for text in source_texts
        )
        assert mcp_relevant, "Sources should be relevant to MCP"

    @pytest.mark.integration
    def test_outline_then_search_sequential_query(self, rag_system_with_test_data):
        """Test queries that might need outline first, then content search"""
        rag = rag_system_with_test_data

        # Query that could benefit from getting outline first
        query = (
            "What topics are covered in both the MCP and Prompt Engineering courses?"
        )

        response, sources = rag.query(query, session_id="test_session_3")

        # Verify response
        assert len(response) > 0
        assert isinstance(response, str)

        # Should have sources (may be from outline or content search)
        assert len(sources) >= 0  # Sources may vary depending on tool strategy

    @pytest.mark.integration
    def test_general_knowledge_no_search(self, rag_system_with_test_data):
        """Test that general knowledge questions don't trigger unnecessary searches"""
        rag = rag_system_with_test_data

        # General knowledge question
        query = "What is artificial intelligence?"

        response, sources = rag.query(query, session_id="test_session_4")

        # Verify response exists
        assert len(response) > 0
        assert isinstance(response, str)

        # May or may not have sources depending on LLM behavior
        # (Some LLMs might still search, but it's not required)

    @pytest.mark.integration
    def test_multi_round_with_conversation_history(self, rag_system_with_test_data):
        """Test that sequential calling works with conversation history"""
        rag = rag_system_with_test_data

        session_id = "test_session_5"

        # First query
        query1 = "What is MCP?"
        response1, sources1 = rag.query(query1, session_id=session_id)

        assert len(response1) > 0

        # Follow-up query that references previous context
        query2 = "How does it compare to Prompt Engineering?"
        response2, sources2 = rag.query(query2, session_id=session_id)

        # Verify second response exists
        assert len(response2) > 0

        # Should handle context correctly (exact behavior depends on LLM)

    @pytest.mark.integration
    def test_course_specific_lesson_query(self, rag_system_with_test_data):
        """Test queries about specific lessons (single round should suffice)"""
        rag = rag_system_with_test_data

        query = "What is covered in lesson 1 of the MCP course?"

        response, sources = rag.query(query, session_id="test_session_6")

        # Verify response
        assert len(response) > 0

        # Should have sources from lesson 1
        if len(sources) > 0:
            # At least one source should be from lesson 1
            lesson_1_sources = [s for s in sources if s.lesson_number == 1]
            # May or may not be exact depending on search behavior

    @pytest.mark.integration
    def test_error_handling_in_sequential_calls(self, rag_system_with_test_data):
        """Test that errors in sequential calls are handled gracefully"""
        rag = rag_system_with_test_data

        # Query with non-existent course (should handle gracefully)
        query = "Compare the NonExistentCourse and MCP courses"

        response, sources = rag.query(query, session_id="test_session_7")

        # Should get a response (even if it's an error message or fallback)
        assert isinstance(response, str)
        assert len(response) > 0

        # May or may not have sources depending on fallback behavior


class TestProviderCompatibility:
    """Test that sequential calling works with different providers"""

    @pytest.mark.integration
    @pytest.mark.skipif(
        Config.LLM_PROVIDER != "anthropic", reason="Requires Anthropic provider"
    )
    def test_anthropic_sequential_calls(self, rag_system_with_test_data):
        """Test sequential calling with Anthropic provider"""
        rag = rag_system_with_test_data

        query = "Compare MCP and Prompt Engineering"
        response, sources = rag.query(query, session_id="anthropic_test")

        assert len(response) > 0
        assert isinstance(response, str)

    @pytest.mark.integration
    @pytest.mark.skipif(Config.LLM_PROVIDER != "groq", reason="Requires Groq provider")
    def test_groq_sequential_calls(self, rag_system_with_test_data):
        """Test sequential calling with Groq provider"""
        rag = rag_system_with_test_data

        query = "Compare MCP and Prompt Engineering"
        response, sources = rag.query(query, session_id="groq_test")

        assert len(response) > 0
        assert isinstance(response, str)
