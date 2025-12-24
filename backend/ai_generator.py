from typing import List, Optional, Dict, Any
from llm_providers import BaseLLMProvider

class AIGenerator:
    """Handles interactions with LLM providers for generating responses"""

    # Static system prompt to avoid rebuilding on each call
    SYSTEM_PROMPT = """ You are an AI assistant specialized in course materials and educational content with access to search and outline retrieval tools.

Multi-Round Tool Usage:
- You can make tool calls across **up to 2 sequential rounds** per user query
- Use this capability for queries requiring multiple information sources
- **Decision-making**: After each round, ask yourself: "Do I have enough information to answer?"
  - If YES: Provide final answer without additional tool calls
  - If NO: Make targeted tool call(s) for missing information (if rounds remain)

Search Tool Usage:
- Use search tools when questions require specific course content
- Use get_course_outline for course structure/topic questions
- Synthesize all search results into accurate, fact-based responses
- If search yields no results, state this clearly without offering alternatives

Multi-Step Search Examples:
- **Comparison questions**: Search each course/topic separately, then synthesize
- **Complex questions**: Break into parts, search for each part sequentially
- **Follow-up searches**: If first search insufficient, refine and search again

Response Protocol:
- **General knowledge**: Answer directly without tools
- **Course-specific**: Search first, then answer
- **Multi-course questions**: Use sequential rounds to gather all needed information
- **Course outline/structure queries**: Use the get_course_outline tool when users ask about:
  - What topics are covered in a course
  - Course structure or lesson organization
  - Complete lesson list for a course
  - Always include the course title, course link, and full lesson details in your response
- **No meta-commentary**:
  - Provide direct answers only — no reasoning process, search explanations, or question-type analysis
  - Do not mention "based on the search results"

All responses must be:
1. **Detailed and educational** - Provide thorough explanations with context
2. **Well-structured** - Organize information logically with clear sections
3. **Example-supported** - Include relevant examples to illustrate concepts
4. **Clear and accessible** - Use plain language while maintaining technical accuracy

Response Guidelines:
- For outline queries: List all lessons with brief descriptions
- For comparison queries: Highlight key differences and similarities with examples
- For content queries: Explain concepts thoroughly with context and examples
- For general queries: Provide comprehensive answers without unnecessary verbosity
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

        # Store tools and query for sequential calling in _handle_tool_execution
        self.available_tools = tools
        self.current_query = query  # Store for adaptive token determination

        # Build system content efficiently - avoid string ops when possible
        system_content = (
            f"{self.SYSTEM_PROMPT}\n\nPrevious conversation:\n{conversation_history}"
            if conversation_history
            else self.SYSTEM_PROMPT
        )

        # Build initial messages
        messages = [{"role": "user", "content": query}]

        # Determine appropriate token limit for this query
        adaptive_max_tokens = self._determine_max_tokens(
            query=query,
            used_tools=False,  # Not yet executed
            tool_names=None
        )

        # Get response from provider with adaptive token limit
        response = self.provider.generate_response(
            messages=messages,
            system_prompt=system_content,
            tools=tools,
            temperature=0,
            max_tokens=adaptive_max_tokens
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
        Handle execution of tool calls with support for up to 2 sequential rounds.

        Supports complex queries requiring multiple searches by allowing Claude to:
        1. Execute tools in round 1
        2. See results and decide if more information needed
        3. Make additional tool calls in round 2 (if needed)
        4. Synthesize final answer

        Args:
            initial_response: The LLMResponse containing tool use requests
            base_messages: Base messages list
            system_prompt: System prompt for the conversation
            tool_manager: Manager to execute tools

        Returns:
            Final response text after tool execution
        """
        from config import Config

        MAX_ROUNDS = 2  # Support up to 2 sequential tool calling rounds
        messages = base_messages.copy()
        current_response = initial_response

        # Loop through rounds, executing tools and getting responses
        for round_num in range(1, MAX_ROUNDS + 1):
            if Config.DEBUG:
                print(f"[DEBUG] Tool calling round {round_num}/{MAX_ROUNDS}")

            # STEP 1: Add assistant's response with tool calls to message history
            # Provider-specific format handling
            if hasattr(current_response.raw_response, 'content'):
                # Anthropic format
                messages.append({
                    "role": "assistant",
                    "content": current_response.raw_response.content
                })
            elif hasattr(current_response.raw_response, 'choices'):
                # Groq format
                messages.append({
                    "role": "assistant",
                    "content": current_response.raw_response.choices[0].message.content or "",
                    "tool_calls": current_response.raw_response.choices[0].message.tool_calls
                })

            # STEP 2: Execute all tool calls from current response
            tool_results = []
            for tool_call in current_response.tool_calls:
                try:
                    if Config.DEBUG:
                        print(f"[DEBUG] Executing tool: {tool_call['name']} with params: {tool_call['input']}")

                    tool_result = tool_manager.execute_tool(
                        tool_call["name"],
                        **tool_call["input"]
                    )

                    tool_results.append({
                        "tool_call_id": tool_call["id"],
                        "content": tool_result
                    })

                    if Config.DEBUG:
                        print(f"[DEBUG] Tool result preview: {tool_result[:100]}...")

                except Exception as e:
                    # Terminate on tool execution error
                    error_msg = f"Error executing tool '{tool_call['name']}': {str(e)}"
                    if Config.DEBUG:
                        print(f"[DEBUG] {error_msg}")
                    return error_msg

            # STEP 3: Add tool results to message history
            if tool_results:
                result_messages = self.provider.build_tool_result_messages(tool_results)
                messages.extend(result_messages)

            # STEP 4: Determine if tools should be available for next API call
            is_final_round = (round_num == MAX_ROUNDS)
            tools_for_next_call = None if is_final_round else self.available_tools

            if Config.DEBUG:
                tools_status = "disabled (final round)" if is_final_round else "enabled"
                print(f"[DEBUG] Tools for next call: {tools_status}")

            # STEP 5: Determine adaptive token limit based on tools used
            tool_names = [tc["name"] for tc in current_response.tool_calls]
            adaptive_max_tokens = self._determine_max_tokens(
                query=self.current_query if hasattr(self, 'current_query') else "",
                used_tools=True,
                tool_names=tool_names
            )

            if Config.DEBUG:
                print(f"[DEBUG] Adaptive max_tokens: {adaptive_max_tokens}")

            # STEP 6: Get next response from LLM
            try:
                next_response = self.provider.generate_response(
                    messages=messages,
                    system_prompt=system_prompt,
                    tools=tools_for_next_call,
                    temperature=0,
                    max_tokens=adaptive_max_tokens
                )
            except Exception as e:
                error_msg = f"Error calling LLM: {str(e)}"
                if Config.DEBUG:
                    print(f"[DEBUG] {error_msg}")
                return error_msg

            # STEP 6: Check termination conditions

            # Condition A: Claude provided direct answer (no more tool calls needed)
            if not next_response.requires_tool_execution:
                if Config.DEBUG:
                    print(f"[DEBUG] Claude answered directly, terminating after round {round_num}")
                return next_response.content

            # Condition B: Maximum rounds reached
            if is_final_round:
                if Config.DEBUG:
                    print(f"[DEBUG] Max rounds ({MAX_ROUNDS}) reached, forcing termination")
                # Force return even if Claude wants more tools
                return next_response.content or "Search limit reached."

            # STEP 7: Continue to next round
            if Config.DEBUG:
                print(f"[DEBUG] Claude requested more tools, continuing to round {round_num + 1}")
            current_response = next_response

        # Safety fallback (should never reach here due to loop range)
        return "Unable to complete request."

    def _determine_max_tokens(self, query: str, used_tools: bool = False,
                              tool_names: Optional[List[str]] = None) -> int:
        """
        Determine appropriate token limit based on query characteristics.

        Implements adaptive response length to provide:
        - Detailed responses for outline/comparison queries
        - Moderate detail for content queries
        - Appropriate length for general queries

        Args:
            query: User's query text
            used_tools: Whether tools were/will be used
            tool_names: Names of tools being used (if applicable)

        Returns:
            Appropriate max_tokens value for this query type
        """
        from config import Config

        query_lower = query.lower()

        # Outline queries: Need space for full lesson lists with descriptions
        outline_keywords = ["outline", "structure", "topics covered", "lesson list",
                           "what topics", "course structure", "what is covered"]
        if any(keyword in query_lower for keyword in outline_keywords):
            return Config.TOKEN_BUDGET_OUTLINE

        # Comparison queries: Need space to synthesize multiple sources
        comparison_keywords = ["compare", "comparison", "difference", "versus",
                              "vs", "vs.", "both", "similarities"]
        if any(keyword in query_lower for keyword in comparison_keywords):
            return Config.TOKEN_BUDGET_COMPARISON

        # Tool-based queries: Moderate educational detail
        if used_tools or tool_names:
            if tool_names and "get_course_outline" in tool_names:
                return Config.TOKEN_BUDGET_OUTLINE  # Outline tool needs more space
            return Config.TOKEN_BUDGET_CONTENT  # Standard content search detail

        # General knowledge: Moderate context
        return Config.TOKEN_BUDGET_GENERAL
