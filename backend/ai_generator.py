from typing import List, Optional, Dict, Any
from llm_providers import BaseLLMProvider

class AIGenerator:
    """Handles interactions with LLM providers for generating responses"""

    # Static system prompt to avoid rebuilding on each call
    SYSTEM_PROMPT = """ You are an AI assistant specialized in course materials and educational content with access to a comprehensive search tool for course information.

Search Tool Usage:
- Use the search tool **only** for questions about specific course content or detailed educational materials
- **One search per query maximum**
- Synthesize search results into accurate, fact-based responses
- If search yields no results, state this clearly without offering alternatives

Response Protocol:
- **General knowledge questions**: Answer using existing knowledge without searching
- **Course-specific questions**: Search first, then answer
- **No meta-commentary**:
 - Provide direct answers only — no reasoning process, search explanations, or question-type analysis
 - Do not mention "based on the search results"


All responses must be:
1. **Brief, Concise and focused** - Get to the point quickly
2. **Educational** - Maintain instructional value
3. **Clear** - Use accessible language
4. **Example-supported** - Include relevant examples when they aid understanding
Provide only the direct answer to what was asked.
"""

    def __init__(self, provider: BaseLLMProvider):
        """
        Initialize AIGenerator with a provider.

        Args:
            provider: Implementation of BaseLLMProvider (AnthropicProvider or GroqProvider)
        """
        self.provider = provider

    def generate_response(self, query: str,
                         conversation_history: Optional[str] = None,
                         tools: Optional[List] = None,
                         tool_manager=None) -> str:
        """
        Generate AI response with optional tool usage and conversation context.

        Args:
            query: The user's question or request
            conversation_history: Previous messages for context
            tools: Available tools the AI can use
            tool_manager: Manager to execute tools

        Returns:
            Generated response as string
        """

        # Build system content efficiently - avoid string ops when possible
        system_content = (
            f"{self.SYSTEM_PROMPT}\n\nPrevious conversation:\n{conversation_history}"
            if conversation_history
            else self.SYSTEM_PROMPT
        )

        # Build initial messages
        messages = [{"role": "user", "content": query}]

        # Get response from provider
        response = self.provider.generate_response(
            messages=messages,
            system_prompt=system_content,
            tools=tools,
            temperature=0,
            max_tokens=800
        )

        # Handle tool execution if needed
        if response.requires_tool_execution and tool_manager:
            return self._handle_tool_execution(
                response, messages, system_content, tool_manager
            )

        # Return direct response
        return response.content

    def _handle_tool_execution(self, initial_response, base_messages: List[Dict[str, Any]],
                                system_prompt: str, tool_manager):
        """
        Handle execution of tool calls and get follow-up response.

        Args:
            initial_response: The LLMResponse containing tool use requests
            base_messages: Base messages list
            system_prompt: System prompt for the conversation
            tool_manager: Manager to execute tools

        Returns:
            Final response text after tool execution
        """
        # Start with existing messages
        messages = base_messages.copy()

        # Add assistant's response with tool calls to message history
        # For Anthropic: need to add the full content with tool_use blocks
        # For Groq: need to add assistant message with tool_calls
        if hasattr(initial_response.raw_response, 'content'):
            # Anthropic format
            messages.append({
                "role": "assistant",
                "content": initial_response.raw_response.content
            })
        elif hasattr(initial_response.raw_response, 'choices'):
            # Groq format
            messages.append({
                "role": "assistant",
                "content": initial_response.raw_response.choices[0].message.content or "",
                "tool_calls": initial_response.raw_response.choices[0].message.tool_calls
            })

        # Execute all tool calls and collect results
        tool_results = []
        for tool_call in initial_response.tool_calls:
            tool_result = tool_manager.execute_tool(
                tool_call["name"],
                **tool_call["input"]
            )

            tool_results.append({
                "tool_call_id": tool_call["id"],
                "content": tool_result
            })

        # Add tool results using provider-specific format
        if tool_results:
            result_messages = self.provider.build_tool_result_messages(tool_results)
            messages.extend(result_messages)

        # Get final response without tools
        final_response = self.provider.generate_response(
            messages=messages,
            system_prompt=system_prompt,
            tools=None,  # Don't allow tools in follow-up
            temperature=0,
            max_tokens=800
        )

        return final_response.content
