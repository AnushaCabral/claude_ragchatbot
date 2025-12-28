import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


def debug_print(*args, **kwargs):
    """Print only if DEBUG mode is enabled"""
    from config import config

    if config.DEBUG:
        print(*args, **kwargs)


@dataclass
class LLMResponse:
    """Normalized response structure across providers"""

    content: str
    requires_tool_execution: bool
    tool_calls: List[Dict[str, Any]]
    raw_response: Any


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers"""

    @abstractmethod
    def generate_response(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0,
        max_tokens: int = 800,
    ) -> LLMResponse:
        """Generate response with normalized output"""
        pass

    @abstractmethod
    def convert_tool_definition(self, tool_def: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Anthropic-style tool definition to provider format"""
        pass

    @abstractmethod
    def build_tool_result_messages(
        self, tool_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Build tool result messages in provider format"""
        pass


class AnthropicProvider(BaseLLMProvider):
    """Provider implementation for Anthropic's Claude API"""

    def __init__(self, api_key: str, model: str):
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def generate_response(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0,
        max_tokens: int = 800,
    ) -> LLMResponse:
        """Generate response using Anthropic API"""
        api_params = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": messages,
            "system": system_prompt,
        }

        # Add tools if available
        if tools:
            api_params["tools"] = tools
            api_params["tool_choice"] = {"type": "auto"}

        # Get response from Claude
        response = self.client.messages.create(**api_params)

        # Check if tool use is required
        requires_tool_execution = response.stop_reason == "tool_use"

        # Extract tool calls if present
        tool_calls = []
        if requires_tool_execution:
            for content_block in response.content:
                if content_block.type == "tool_use":
                    tool_calls.append(
                        {
                            "id": content_block.id,
                            "name": content_block.name,
                            "input": content_block.input,
                        }
                    )

        # Get text content
        content = ""
        if not requires_tool_execution and response.content:
            content = response.content[0].text

        return LLMResponse(
            content=content,
            requires_tool_execution=requires_tool_execution,
            tool_calls=tool_calls,
            raw_response=response,
        )

    def convert_tool_definition(self, tool_def: Dict[str, Any]) -> Dict[str, Any]:
        """Anthropic format is our base format, no conversion needed"""
        return tool_def

    def build_tool_result_messages(
        self, tool_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Build Anthropic-formatted tool result messages"""
        # Anthropic expects tool results as content blocks in a user message
        result_blocks = []
        for result in tool_results:
            result_blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": result["tool_call_id"],
                    "content": result["content"],
                }
            )

        return [{"role": "user", "content": result_blocks}]


class GroqProvider(BaseLLMProvider):
    """Provider implementation for Groq's API (OpenAI-compatible)"""

    def __init__(self, api_key: str, model: str):
        debug_print(
            f"[DEBUG] Initializing GroqProvider with API key: {api_key[:20] if api_key else 'NONE'}..."
        )
        debug_print(f"[DEBUG] Model: {model}")
        # Store API key instead of client for async-safe usage
        self.api_key = api_key
        self.model = model
        debug_print("[DEBUG] GroqProvider initialized")

    def generate_response(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0,
        max_tokens: int = 800,
    ) -> LLMResponse:
        """Generate response using Groq API"""
        debug_print("[DEBUG] GroqProvider.generate_response called")
        debug_print(f"[DEBUG] self.api_key type: {type(self.api_key)}")
        debug_print(
            f"[DEBUG] self.api_key value: {self.api_key[:30] if self.api_key else 'NONE'}..."
        )
        debug_print(
            f"[DEBUG] self.api_key length: {len(self.api_key) if self.api_key else 0}"
        )

        # Create fresh client for each request (async-safe)
        from groq import Groq

        debug_print("[DEBUG] About to create Groq client...")
        client = Groq(api_key=self.api_key)
        debug_print(f"[DEBUG] Created fresh Groq client: {client}")
        debug_print(f"[DEBUG] Model: {self.model}")

        # Build messages with system prompt as first message
        groq_messages = [{"role": "system", "content": system_prompt}] + messages

        # Convert tools to Groq format if provided
        groq_tools = None
        if tools:
            groq_tools = [self.convert_tool_definition(t) for t in tools]
            debug_print(f"[DEBUG] Tools converted: {len(groq_tools)} tools")

        api_params = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": groq_messages,
        }

        # Add tools if available
        if groq_tools:
            api_params["tools"] = groq_tools
            api_params["tool_choice"] = "auto"

        debug_print(
            f"[DEBUG] Making Groq API call with params: {list(api_params.keys())}"
        )

        # Get response from Groq
        try:
            response = client.chat.completions.create(**api_params)
            debug_print("[DEBUG] Groq API call successful")
        except Exception as e:
            debug_print(f"[DEBUG] Groq API call failed: {e}")
            raise

        # Check if tool use is required
        message = response.choices[0].message
        requires_tool_execution = (
            response.choices[0].finish_reason == "tool_calls"
            and hasattr(message, "tool_calls")
            and message.tool_calls is not None
        )

        # Extract tool calls if present
        tool_calls = []
        if requires_tool_execution:
            for tool_call in message.tool_calls:
                # Parse arguments from JSON string
                arguments = json.loads(tool_call.function.arguments)
                tool_calls.append(
                    {
                        "id": tool_call.id,
                        "name": tool_call.function.name,
                        "input": arguments,
                    }
                )

        # Get text content
        content = ""
        if not requires_tool_execution and message.content:
            content = message.content

        return LLMResponse(
            content=content,
            requires_tool_execution=requires_tool_execution,
            tool_calls=tool_calls,
            raw_response=response,
        )

    def convert_tool_definition(self, tool_def: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Anthropic format to OpenAI/Groq format"""
        return {
            "type": "function",
            "function": {
                "name": tool_def["name"],
                "description": tool_def["description"],
                "parameters": tool_def["input_schema"],
            },
        }

    def build_tool_result_messages(
        self, tool_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Build Groq/OpenAI-formatted tool result messages"""
        # Groq expects individual messages with role="tool"
        messages = []
        for result in tool_results:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": result["tool_call_id"],
                    "content": result["content"],
                }
            )
        return messages
