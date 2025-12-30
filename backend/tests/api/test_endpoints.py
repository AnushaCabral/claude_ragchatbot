# backend/tests/api/test_endpoints.py
# Tests for FastAPI endpoints

import pytest
from unittest.mock import Mock
from fastapi import status
from models import Source


@pytest.mark.api
class TestQueryEndpoint:
    """Tests for /api/query endpoint"""

    def test_query_success_with_sources(self, client, mock_rag_system):
        """Test successful query with sources returned"""
        # Arrange
        request_data = {
            "query": "What is MCP?",
            "session_id": None
        }

        # Act
        response = client.post("/api/query", json=request_data)

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert "answer" in data
        assert "sources" in data
        assert "session_id" in data

        assert data["answer"] == "This is a test answer about MCP."
        assert len(data["sources"]) == 1
        assert data["sources"][0]["course_title"] == "MCP: Build Rich-Context AI Apps with Anthropic"
        assert data["sources"][0]["lesson_number"] == 0
        assert data["session_id"] == "test-session-123"

        # Verify RAG system was called correctly
        mock_rag_system.query.assert_called_once_with("What is MCP?", "test-session-123")

    def test_query_with_existing_session_id(self, client, mock_rag_system):
        """Test query with existing session ID"""
        # Arrange
        existing_session = "existing-session-456"
        request_data = {
            "query": "Tell me about Prompt Engineering",
            "session_id": existing_session
        }

        # Act
        response = client.post("/api/query", json=request_data)

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["session_id"] == existing_session

        # Verify session manager was NOT called to create new session
        mock_rag_system.session_manager.create_session.assert_not_called()
        mock_rag_system.query.assert_called_once_with(
            "Tell me about Prompt Engineering",
            existing_session
        )

    def test_query_creates_session_when_not_provided(self, client, mock_rag_system):
        """Test query creates new session when session_id not provided"""
        # Arrange
        request_data = {
            "query": "What courses are available?"
        }

        # Act
        response = client.post("/api/query", json=request_data)

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["session_id"] == "test-session-123"

        # Verify session was created
        mock_rag_system.session_manager.create_session.assert_called_once()

    def test_query_missing_query_field(self, client):
        """Test query with missing query field returns validation error"""
        # Arrange
        request_data = {
            "session_id": "some-session"
            # Missing "query" field
        }

        # Act
        response = client.post("/api/query", json=request_data)

        # Assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_query_empty_query_string(self, client, mock_rag_system):
        """Test query with empty string"""
        # Arrange
        request_data = {
            "query": ""
        }

        # Act
        response = client.post("/api/query", json=request_data)

        # Assert
        assert response.status_code == status.HTTP_200_OK
        # Empty query should still be processed
        mock_rag_system.query.assert_called_once()

    def test_query_rag_system_error(self, client, mock_rag_system):
        """Test query when RAG system raises exception"""
        # Arrange
        mock_rag_system.query.side_effect = Exception("Database connection failed")
        request_data = {
            "query": "Test query"
        }

        # Act
        response = client.post("/api/query", json=request_data)

        # Assert
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Database connection failed" in response.json()["detail"]

    def test_query_response_structure(self, client, mock_rag_system):
        """Test that response matches QueryResponse model"""
        # Arrange
        mock_rag_system.query.return_value = (
            "Multiple sources answer",
            [
                Source(
                    display_text="Course A - Lesson 1",
                    course_title="Course A",
                    lesson_number=1,
                    url="https://example.com/a-1"
                ),
                Source(
                    display_text="Course B - Lesson 2",
                    course_title="Course B",
                    lesson_number=2,
                    url="https://example.com/b-2"
                )
            ]
        )

        request_data = {"query": "Compare courses"}

        # Act
        response = client.post("/api/query", json=request_data)

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Validate structure
        assert isinstance(data["answer"], str)
        assert isinstance(data["sources"], list)
        assert isinstance(data["session_id"], str)

        # Validate sources structure
        assert len(data["sources"]) == 2
        for source in data["sources"]:
            assert "display_text" in source
            assert "course_title" in source
            assert "lesson_number" in source
            assert "url" in source


@pytest.mark.api
class TestCoursesEndpoint:
    """Tests for /api/courses endpoint"""

    def test_get_courses_success(self, client, mock_rag_system, sample_courses):
        """Test successful retrieval of course statistics"""
        # Act
        response = client.get("/api/courses")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert "total_courses" in data
        assert "course_titles" in data

        assert data["total_courses"] == 2
        assert len(data["course_titles"]) == 2
        assert "MCP: Build Rich-Context AI Apps with Anthropic" in data["course_titles"]
        assert "Introduction to Prompt Engineering" in data["course_titles"]

        # Verify RAG system method was called
        mock_rag_system.get_course_analytics.assert_called_once()

    def test_get_courses_empty_database(self, client, mock_rag_system):
        """Test course endpoint when no courses are loaded"""
        # Arrange
        mock_rag_system.get_course_analytics.return_value = {
            "total_courses": 0,
            "course_titles": []
        }

        # Act
        response = client.get("/api/courses")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["total_courses"] == 0
        assert data["course_titles"] == []

    def test_get_courses_rag_system_error(self, client, mock_rag_system):
        """Test courses endpoint when RAG system raises exception"""
        # Arrange
        mock_rag_system.get_course_analytics.side_effect = Exception("Vector store unavailable")

        # Act
        response = client.get("/api/courses")

        # Assert
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Vector store unavailable" in response.json()["detail"]

    def test_get_courses_response_structure(self, client, mock_rag_system):
        """Test that response matches CourseStats model"""
        # Arrange
        mock_rag_system.get_course_analytics.return_value = {
            "total_courses": 3,
            "course_titles": ["Course 1", "Course 2", "Course 3"]
        }

        # Act
        response = client.get("/api/courses")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Validate structure
        assert isinstance(data["total_courses"], int)
        assert isinstance(data["course_titles"], list)
        assert all(isinstance(title, str) for title in data["course_titles"])


@pytest.mark.api
class TestRootEndpoint:
    """Tests for / root endpoint"""

    def test_root_returns_message(self, client):
        """Test root endpoint returns welcome message"""
        # Act
        response = client.get("/")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert "message" in data
        assert data["message"] == "Course Materials RAG System API"

    def test_root_endpoint_accessible(self, client):
        """Test root endpoint is accessible without authentication"""
        # Act
        response = client.get("/")

        # Assert
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.api
class TestCORSMiddleware:
    """Tests for CORS middleware configuration"""

    def test_cors_middleware_allows_requests(self, client):
        """Test that requests work (CORS middleware doesn't block)"""
        # The TestClient doesn't expose CORS headers, but we can verify
        # that the middleware is configured by ensuring requests succeed
        # In a real browser, CORS headers would be present

        # Act - Make a request that would be subject to CORS
        response = client.get("/")

        # Assert - Request succeeds without CORS blocking
        assert response.status_code == status.HTTP_200_OK

    def test_cors_preflight_request(self, client):
        """Test CORS preflight OPTIONS request"""
        # Act
        response = client.options(
            "/api/query",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type"
            }
        )

        # Assert - OPTIONS request should succeed
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT]


@pytest.mark.api
class TestErrorHandling:
    """Tests for error handling across API endpoints"""

    def test_invalid_json_payload(self, client):
        """Test API response to malformed JSON"""
        # Act
        response = client.post(
            "/api/query",
            data="invalid-json-data",
            headers={"Content-Type": "application/json"}
        )

        # Assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_invalid_endpoint(self, client):
        """Test 404 response for non-existent endpoint"""
        # Act
        response = client.get("/api/nonexistent")

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_wrong_http_method(self, client):
        """Test error when using wrong HTTP method"""
        # Act - GET instead of POST for /api/query
        response = client.get("/api/query")

        # Assert
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.api
class TestSessionManagement:
    """Tests for session ID handling"""

    def test_session_id_persistence(self, client, mock_rag_system):
        """Test that session_id is returned and can be reused"""
        # First request
        response1 = client.post("/api/query", json={"query": "First query"})
        session_id = response1.json()["session_id"]

        # Second request with same session
        response2 = client.post("/api/query", json={
            "query": "Follow-up query",
            "session_id": session_id
        })

        # Assert
        assert response1.status_code == status.HTTP_200_OK
        assert response2.status_code == status.HTTP_200_OK
        assert response2.json()["session_id"] == session_id

    def test_multiple_sessions_independent(self, client, mock_rag_system):
        """Test that multiple sessions are handled independently"""
        # Arrange - Configure mock to return different session IDs
        session_ids = ["session-1", "session-2"]
        mock_rag_system.session_manager.create_session.side_effect = session_ids

        # Act - Create two separate sessions
        response1 = client.post("/api/query", json={"query": "Query 1"})
        response2 = client.post("/api/query", json={"query": "Query 2"})

        # Assert
        assert response1.json()["session_id"] == "session-1"
        assert response2.json()["session_id"] == "session-2"
        assert mock_rag_system.session_manager.create_session.call_count == 2
