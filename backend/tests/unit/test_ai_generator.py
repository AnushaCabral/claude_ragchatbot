# backend/tests/unit/test_ai_generator.py
# Unit tests for sequential tool calling in AIGenerator

import pytest
from unittest.mock import Mock, patch, call
from ai_generator import AIGenerator
from llm_providers import LLMResponse


class TestSequentialToolCalling:
    """Tests for sequential tool calling (up to 2 rounds)"""

    @pytest.fixture
    def mock_provider(self):
        """Create mock LLM provider"""
        provider = Mock()
        return provider

    @pytest.fixture
    def ai_generator(self, mock_provider):
        """Create AIGenerator with mock provider"""
        return AIGenerator(provider=mock_provider)

    @pytest.fixture
    def mock_tool_manager(self):
        """Create mock tool manager"""
        manager = Mock()
        manager.execute_tool = Mock(return_value="Tool result content")
        return manager

    def test_single_round_tool_execution_backward_compatibility(self, ai_generator, mock_provider, mock_tool_manager):
        """Test that single-round queries still work (backward compatibility)"""
        # Setup: Query needs one tool, Claude answers after seeing result

        # Round 1: Claude wants to use a tool
        initial_response = LLMResponse(
            content="",
            requires_tool_execution=True,
            tool_calls=[{
                "id": "call_1",
                "name": "search_course_content",
                "input": {"query": "What is MCP?"}
            }],
            raw_response=Mock(content=[{"type": "tool_use", "id": "call_1"}])
        )

        # Round 1 follow-up: Claude answers directly (no more tools)
        final_response = LLMResponse(
            content="MCP stands for Model Context Protocol...",
            requires_tool_execution=False,
            tool_calls=[],
            raw_response=Mock()
        )

        # Mock provider to return responses in sequence
        mock_provider.generate_response = Mock(side_effect=[initial_response, final_response])
        mock_provider.build_tool_result_messages = Mock(return_value=[
            {"role": "user", "content": [{"type": "tool_result", "content": "Tool result content"}]}
        ])

        # Execute
        result = ai_generator.generate_response(
            query="What is MCP?",
            tools=[{"name": "search_course_content"}],
            tool_manager=mock_tool_manager
        )

        # Verify: Should execute 1 tool call and 1 follow-up API call (2 total)
        assert mock_provider.generate_response.call_count == 2
        assert mock_tool_manager.execute_tool.call_count == 1
        assert result == "MCP stands for Model Context Protocol..."

        # Verify tools were available in both calls (round 1 is not final round)
        # Tools remain enabled until max rounds reached, allowing Claude to decide
        first_call_tools = mock_provider.generate_response.call_args_list[0][1]['tools']
        second_call_tools = mock_provider.generate_response.call_args_list[1][1]['tools']
        assert first_call_tools is not None
        assert second_call_tools is not None  # Tools still enabled (round 1 of 2)

    def test_two_round_tool_execution(self, ai_generator, mock_provider, mock_tool_manager):
        """Test that two-round queries work correctly"""
        # Setup: Comparison query requiring two searches

        # Round 1: Claude wants to search first course
        initial_response = LLMResponse(
            content="",
            requires_tool_execution=True,
            tool_calls=[{
                "id": "call_1",
                "name": "get_course_outline",
                "input": {"course_title": "MCP"}
            }],
            raw_response=Mock(content=[{"type": "tool_use", "id": "call_1"}])
        )

        # After round 1: Claude wants to search second course
        round_2_response = LLMResponse(
            content="",
            requires_tool_execution=True,
            tool_calls=[{
                "id": "call_2",
                "name": "get_course_outline",
                "input": {"course_title": "Prompt Engineering"}
            }],
            raw_response=Mock(content=[{"type": "tool_use", "id": "call_2"}])
        )

        # After round 2: Claude provides final answer
        final_response = LLMResponse(
            content="Comparison: MCP focuses on... while Prompt Engineering covers...",
            requires_tool_execution=False,
            tool_calls=[],
            raw_response=Mock()
        )

        # Mock provider to return responses in sequence
        mock_provider.generate_response = Mock(side_effect=[
            initial_response,  # Initial call
            round_2_response,  # After round 1 tools
            final_response     # After round 2 tools
        ])
        mock_provider.build_tool_result_messages = Mock(return_value=[
            {"role": "user", "content": [{"type": "tool_result", "content": "Tool result"}]}
        ])

        # Execute
        result = ai_generator.generate_response(
            query="Compare MCP and Prompt Engineering courses",
            tools=[{"name": "get_course_outline"}],
            tool_manager=mock_tool_manager
        )

        # Verify: 3 API calls (initial + 2 follow-ups), 2 tool executions
        assert mock_provider.generate_response.call_count == 3
        assert mock_tool_manager.execute_tool.call_count == 2
        assert result == "Comparison: MCP focuses on... while Prompt Engineering covers..."

        # Verify tools were enabled in rounds 1 and 2, disabled in final call
        call_args = mock_provider.generate_response.call_args_list
        assert call_args[0][1]['tools'] is not None  # Initial call
        assert call_args[1][1]['tools'] is not None  # After round 1 (tools still enabled)
        assert call_args[2][1]['tools'] is None      # After round 2 (tools disabled)

    def test_max_rounds_enforced(self, ai_generator, mock_provider, mock_tool_manager):
        """Test that execution stops after 2 rounds even if Claude wants more tools"""
        # Setup: Claude keeps requesting tools indefinitely

        # All responses request tools (simulating Claude never satisfied)
        tool_response = LLMResponse(
            content="",
            requires_tool_execution=True,
            tool_calls=[{
                "id": "call_x",
                "name": "search_course_content",
                "input": {"query": "test"}
            }],
            raw_response=Mock(content=[{"type": "tool_use", "id": "call_x"}])
        )

        # Mock provider to always want more tools
        mock_provider.generate_response = Mock(return_value=tool_response)
        mock_provider.build_tool_result_messages = Mock(return_value=[
            {"role": "user", "content": [{"type": "tool_result", "content": "Result"}]}
        ])

        # Execute
        result = ai_generator.generate_response(
            query="Complex question",
            tools=[{"name": "search_course_content"}],
            tool_manager=mock_tool_manager
        )

        # Verify: Stops after 2 rounds (3 API calls: initial + 2 follow-ups)
        assert mock_provider.generate_response.call_count == 3
        assert mock_tool_manager.execute_tool.call_count == 2

        # Should return response even if Claude wants more tools
        assert result is not None

        # Verify tools were disabled on final call (round 2)
        final_call_tools = mock_provider.generate_response.call_args_list[2][1]['tools']
        assert final_call_tools is None

    def test_early_termination_no_tools(self, ai_generator, mock_provider, mock_tool_manager):
        """Test early termination when Claude answers directly after round 1"""
        # Setup: Claude makes one tool call, then answers

        # Round 1: Claude wants to search
        initial_response = LLMResponse(
            content="",
            requires_tool_execution=True,
            tool_calls=[{
                "id": "call_1",
                "name": "get_course_outline",
                "input": {"course_title": "MCP"}
            }],
            raw_response=Mock(content=[{"type": "tool_use", "id": "call_1"}])
        )

        # After round 1: Claude has enough info, answers directly
        final_response = LLMResponse(
            content="The MCP course covers...",
            requires_tool_execution=False,
            tool_calls=[],
            raw_response=Mock()
        )

        mock_provider.generate_response = Mock(side_effect=[initial_response, final_response])
        mock_provider.build_tool_result_messages = Mock(return_value=[
            {"role": "user", "content": [{"type": "tool_result", "content": "Outline data"}]}
        ])

        # Execute
        result = ai_generator.generate_response(
            query="What does MCP course cover?",
            tools=[{"name": "get_course_outline"}],
            tool_manager=mock_tool_manager
        )

        # Verify: Only 2 API calls (terminates early)
        assert mock_provider.generate_response.call_count == 2
        assert mock_tool_manager.execute_tool.call_count == 1
        assert result == "The MCP course covers..."

    def test_tool_execution_error_terminates_gracefully(self, ai_generator, mock_provider, mock_tool_manager):
        """Test that tool execution errors are handled gracefully"""
        # Setup: Tool execution raises exception

        initial_response = LLMResponse(
            content="",
            requires_tool_execution=True,
            tool_calls=[{
                "id": "call_1",
                "name": "search_course_content",
                "input": {"query": "test"}
            }],
            raw_response=Mock(content=[{"type": "tool_use", "id": "call_1"}])
        )

        mock_provider.generate_response = Mock(return_value=initial_response)
        mock_provider.build_tool_result_messages = Mock(return_value=[])

        # Tool execution fails
        mock_tool_manager.execute_tool = Mock(side_effect=Exception("Database connection error"))

        # Execute
        result = ai_generator.generate_response(
            query="Test query",
            tools=[{"name": "search_course_content"}],
            tool_manager=mock_tool_manager
        )

        # Verify: Returns error message, doesn't crash
        assert isinstance(result, str)
        assert "Error executing tool" in result
        assert "Database connection error" in result

        # Should not make follow-up API call after error
        assert mock_provider.generate_response.call_count == 1

    def test_message_accumulation_across_rounds(self, ai_generator, mock_provider, mock_tool_manager):
        """Test that messages accumulate correctly across rounds"""
        # Setup: Two-round execution

        initial_response = LLMResponse(
            content="",
            requires_tool_execution=True,
            tool_calls=[{"id": "call_1", "name": "tool1", "input": {}}],
            raw_response=Mock(content=[{"type": "tool_use", "id": "call_1"}])
        )

        round_2_response = LLMResponse(
            content="",
            requires_tool_execution=True,
            tool_calls=[{"id": "call_2", "name": "tool2", "input": {}}],
            raw_response=Mock(content=[{"type": "tool_use", "id": "call_2"}])
        )

        final_response = LLMResponse(
            content="Final answer",
            requires_tool_execution=False,
            tool_calls=[],
            raw_response=Mock()
        )

        mock_provider.generate_response = Mock(side_effect=[
            initial_response,
            round_2_response,
            final_response
        ])
        mock_provider.build_tool_result_messages = Mock(return_value=[
            {"role": "user", "content": [{"type": "tool_result", "content": "Result"}]}
        ])

        # Execute
        ai_generator.generate_response(
            query="Test",
            tools=[{"name": "tool1"}, {"name": "tool2"}],
            tool_manager=mock_tool_manager
        )

        # Verify message accumulation
        call_args = mock_provider.generate_response.call_args_list

        # Initial call: 1 message (user query)
        assert len(call_args[0][1]['messages']) == 1

        # After round 1: 1 (user) + 1 (assistant tool call) + 1 (tool result) = 3
        round_2_messages = call_args[1][1]['messages']
        assert len(round_2_messages) >= 3

        # After round 2: Previous 3 + 1 (assistant tool call) + 1 (tool result) = 5
        final_messages = call_args[2][1]['messages']
        assert len(final_messages) >= 5

    def test_no_tools_no_tool_execution(self, ai_generator, mock_provider):
        """Test that queries without tools work normally"""
        # Setup: Direct answer, no tools

        direct_response = LLMResponse(
            content="This is general knowledge...",
            requires_tool_execution=False,
            tool_calls=[],
            raw_response=Mock()
        )

        mock_provider.generate_response = Mock(return_value=direct_response)

        # Execute
        result = ai_generator.generate_response(
            query="What is 2+2?",
            tools=None,
            tool_manager=None
        )

        # Verify: Single API call, no tool execution
        assert mock_provider.generate_response.call_count == 1
        assert result == "This is general knowledge..."

    def test_groq_provider_format_handling(self, ai_generator, mock_provider, mock_tool_manager):
        """Test that Groq provider message format is handled correctly"""
        # Setup: Groq-style response with choices

        mock_message = Mock()
        mock_message.content = ""
        mock_message.tool_calls = [Mock(
            id="call_1",
            function=Mock(name="search", arguments='{"query": "test"}')
        )]

        mock_choice = Mock()
        mock_choice.message = mock_message

        mock_raw_response = Mock()
        mock_raw_response.choices = [mock_choice]
        # Groq format doesn't have .content attribute at top level

        initial_response = LLMResponse(
            content="",
            requires_tool_execution=True,
            tool_calls=[{"id": "call_1", "name": "search", "input": {"query": "test"}}],
            raw_response=mock_raw_response
        )

        final_response = LLMResponse(
            content="Answer",
            requires_tool_execution=False,
            tool_calls=[],
            raw_response=Mock()
        )

        mock_provider.generate_response = Mock(side_effect=[initial_response, final_response])
        mock_provider.build_tool_result_messages = Mock(return_value=[
            {"role": "user", "content": "Result"}
        ])

        # Execute
        result = ai_generator.generate_response(
            query="Test",
            tools=[{"name": "search"}],
            tool_manager=mock_tool_manager
        )

        # Verify: Handles Groq format without errors
        assert result == "Answer"
        assert mock_tool_manager.execute_tool.call_count == 1

    @patch('config.Config.DEBUG', True)
    def test_debug_logging_enabled(self, ai_generator, mock_provider, mock_tool_manager, capsys):
        """Test that debug logging works when DEBUG=True"""
        # Setup
        initial_response = LLMResponse(
            content="",
            requires_tool_execution=True,
            tool_calls=[{"id": "call_1", "name": "tool", "input": {}}],
            raw_response=Mock(content=[{"type": "tool_use"}])
        )

        final_response = LLMResponse(
            content="Answer",
            requires_tool_execution=False,
            tool_calls=[],
            raw_response=Mock()
        )

        mock_provider.generate_response = Mock(side_effect=[initial_response, final_response])
        mock_provider.build_tool_result_messages = Mock(return_value=[
            {"role": "user", "content": "Result"}
        ])

        # Execute
        ai_generator.generate_response(
            query="Test",
            tools=[{"name": "tool"}],
            tool_manager=mock_tool_manager
        )

        # Verify debug output
        captured = capsys.readouterr()
        assert "[DEBUG]" in captured.out
        assert "Tool calling round" in captured.out
