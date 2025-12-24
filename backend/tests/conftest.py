# backend/tests/conftest.py
# Pytest fixtures and shared test utilities

import pytest
from unittest.mock import Mock, MagicMock
from typing import List, Dict, Any
import tempfile
import shutil
import os
import sys

# Add parent directory to path to import backend modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Course, Lesson, CourseChunk, Source
from vector_store import VectorStore, SearchResults
from config import Config


@pytest.fixture
def mock_config():
    """Mock configuration for testing"""
    config = Mock(spec=Config)
    config.DEBUG = False
    config.LLM_PROVIDER = "groq"
    config.GROQ_API_KEY = "test_groq_key_1234567890"
    config.GROQ_MODEL = "llama-3.3-70b-versatile"
    config.ANTHROPIC_API_KEY = "test_anthropic_key_1234567890"
    config.ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
    config.EMBEDDING_MODEL = "all-MiniLM-L6-v2"
    config.CHUNK_SIZE = 800
    config.CHUNK_OVERLAP = 100
    config.MAX_RESULTS = 5
    config.MAX_HISTORY = 2
    config.CHROMA_PATH = "./test_chroma_db"
    return config


@pytest.fixture
def sample_courses():
    """Sample course data for testing"""
    return [
        Course(
            title="MCP: Build Rich-Context AI Apps with Anthropic",
            course_link="https://example.com/mcp-course",
            instructor="Test Instructor",
            lessons=[
                Lesson(lesson_number=0, title="Introduction to MCP", lesson_link="https://example.com/mcp-lesson-0"),
                Lesson(lesson_number=1, title="Building MCP Servers", lesson_link="https://example.com/mcp-lesson-1"),
                Lesson(lesson_number=2, title="MCP Clients", lesson_link="https://example.com/mcp-lesson-2"),
            ]
        ),
        Course(
            title="Introduction to Prompt Engineering",
            course_link="https://example.com/prompt-eng",
            instructor="Another Instructor",
            lessons=[
                Lesson(lesson_number=0, title="What is Prompt Engineering", lesson_link="https://example.com/pe-lesson-0"),
                Lesson(lesson_number=1, title="Advanced Techniques", lesson_link="https://example.com/pe-lesson-1"),
            ]
        )
    ]


@pytest.fixture
def sample_chunks():
    """Sample course chunks for testing"""
    return [
        CourseChunk(
            content="Course MCP: Build Rich-Context AI Apps with Anthropic Lesson 0 content: MCP stands for Model Context Protocol. It enables rich context sharing between AI applications and external data sources.",
            course_title="MCP: Build Rich-Context AI Apps with Anthropic",
            lesson_number=0,
            chunk_index=0
        ),
        CourseChunk(
            content="Course MCP: Build Rich-Context AI Apps with Anthropic Lesson 1 content: Building an MCP server requires implementing the protocol handlers and defining your tools. The server acts as a bridge between the AI and your data.",
            course_title="MCP: Build Rich-Context AI Apps with Anthropic",
            lesson_number=1,
            chunk_index=1
        ),
        CourseChunk(
            content="Course Introduction to Prompt Engineering Lesson 0 content: Prompt engineering is the art of crafting effective prompts to guide AI models toward desired outputs. Key techniques include few-shot learning and chain-of-thought prompting.",
            course_title="Introduction to Prompt Engineering",
            lesson_number=0,
            chunk_index=2
        )
    ]


@pytest.fixture
def temp_chroma_db(mock_config, sample_courses, sample_chunks):
    """Create a temporary ChromaDB with test data"""
    temp_dir = tempfile.mkdtemp()
    mock_config.CHROMA_PATH = temp_dir

    # Create vector store and populate with test data
    vector_store = VectorStore(
        chroma_path=temp_dir,
        embedding_model=mock_config.EMBEDDING_MODEL,
        max_results=mock_config.MAX_RESULTS
    )

    # Add sample courses and chunks
    for course in sample_courses:
        vector_store.add_course_metadata(course)

    vector_store.add_course_content(sample_chunks)

    yield vector_store

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_groq_response():
    """Mock Groq API response without tool calls"""
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message = Mock()
    mock_response.choices[0].message.content = "This is a test response from Groq."
    mock_response.choices[0].message.tool_calls = None
    mock_response.choices[0].finish_reason = "stop"
    return mock_response


@pytest.fixture
def mock_groq_tool_call_response():
    """Mock Groq API response with tool call"""
    import json

    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message = Mock()
    mock_response.choices[0].message.content = ""

    # Mock tool call
    mock_tool_call = Mock()
    mock_tool_call.id = "call_123"
    mock_tool_call.function = Mock()
    mock_tool_call.function.name = "search_course_content"
    mock_tool_call.function.arguments = json.dumps({
        "query": "MCP",
        "course_name": None,
        "lesson_number": None
    })

    mock_response.choices[0].message.tool_calls = [mock_tool_call]
    mock_response.choices[0].finish_reason = "tool_calls"
    return mock_response


@pytest.fixture
def mock_anthropic_response():
    """Mock Anthropic API response without tool calls"""
    mock_response = Mock()

    # Mock text block
    mock_text_block = Mock()
    mock_text_block.type = "text"
    mock_text_block.text = "This is a test response from Claude."

    mock_response.content = [mock_text_block]
    mock_response.stop_reason = "end_turn"
    return mock_response


@pytest.fixture
def mock_anthropic_tool_call_response():
    """Mock Anthropic API response with tool call"""
    mock_response = Mock()

    # Mock tool use block
    mock_tool_block = Mock()
    mock_tool_block.type = "tool_use"
    mock_tool_block.id = "toolu_123"
    mock_tool_block.name = "search_course_content"
    mock_tool_block.input = {
        "query": "MCP",
        "course_name": None,
        "lesson_number": None
    }

    mock_response.content = [mock_tool_block]
    mock_response.stop_reason = "tool_use"
    return mock_response
