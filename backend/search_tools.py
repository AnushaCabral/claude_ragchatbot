from typing import Dict, Any, Optional, Protocol, List
from abc import ABC, abstractmethod
from vector_store import VectorStore, SearchResults
from models import Source


class Tool(ABC):
    """Abstract base class for all tools"""
    
    @abstractmethod
    def get_tool_definition(self) -> Dict[str, Any]:
        """Return Anthropic tool definition for this tool"""
        pass
    
    @abstractmethod
    def execute(self, **kwargs) -> str:
        """Execute the tool with given parameters"""
        pass


class CourseSearchTool(Tool):
    """Tool for searching course content with semantic course name matching"""

    def __init__(self, vector_store: VectorStore):
        self.store = vector_store
        self.last_sources: List[Source] = []  # Track sources from last search
    
    def get_tool_definition(self) -> Dict[str, Any]:
        """Return Anthropic tool definition for this tool"""
        return {
            "name": "search_course_content",
            "description": "Search course materials with smart course name matching and lesson filtering. Only include course_name and lesson_number if specifically mentioned in the query.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search for in the course content"
                    },
                    "course_name": {
                        "type": ["string", "null"],
                        "description": "Course title (partial matches work, e.g. 'MCP', 'Introduction'). Use null or omit if not specified in query."
                    },
                    "lesson_number": {
                        "type": ["integer", "null"],
                        "description": "Specific lesson number to search within (e.g. 1, 2, 3). Use null or omit if not specified."
                    }
                },
                "required": ["query"]
            }
        }
    
    def execute(self, query: str, course_name: Optional[str] = None, lesson_number: Optional[int] = None) -> str:
        """
        Execute the search tool with given parameters.

        Args:
            query: What to search for
            course_name: Optional course filter
            lesson_number: Optional lesson filter

        Returns:
            Formatted search results or error message
        """

        # Normalize empty strings to None (some LLM providers pass "" instead of null)
        if course_name == "":
            course_name = None
        if lesson_number == "":
            lesson_number = None

        # Use the vector store's unified search interface
        results = self.store.search(
            query=query,
            course_name=course_name,
            lesson_number=lesson_number
        )

        # Handle errors with intelligent fallback
        if results.error:
            # If course filter failed but query is good, try without filter as fallback
            if course_name and "No course found" in results.error:
                fallback_results = self.store.search(query=query)
                if not fallback_results.is_empty() and not fallback_results.error:
                    # Add note about fallback
                    return f"[Searched all courses since '{course_name}' wasn't found]\n\n" + self._format_results(fallback_results)
            # Return original error if fallback didn't help
            return results.error
        
        # Handle empty results
        if results.is_empty():
            filter_info = ""
            if course_name:
                filter_info += f" in course '{course_name}'"
            if lesson_number:
                filter_info += f" in lesson {lesson_number}"
            return f"No relevant content found{filter_info}."
        
        # Format and return results
        return self._format_results(results)
    
    def _format_results(self, results: SearchResults) -> str:
        """Format search results with course and lesson context"""
        formatted = []
        seen_sources = {}  # Track unique sources by (course_title, lesson_number)

        for doc, meta in zip(results.documents, results.metadata):
            course_title = meta.get('course_title', 'unknown')
            lesson_num = meta.get('lesson_number')

            # Build context header for LLM (unchanged)
            header = f"[{course_title}"
            if lesson_num is not None:
                header += f" - Lesson {lesson_num}"
            header += "]"

            # Create unique key for deduplication
            source_key = (course_title, lesson_num)

            # Only create Source object if we haven't seen this (course, lesson) combination
            if source_key not in seen_sources:
                # Build display text for UI
                display_text = course_title
                if lesson_num is not None:
                    display_text += f" - Lesson {lesson_num}"

                # Look up best available link
                url = self.store.get_source_link(course_title, lesson_num)

                # Create and store Source object
                source = Source(
                    display_text=display_text,
                    course_title=course_title,
                    lesson_number=lesson_num,
                    url=url
                )
                seen_sources[source_key] = source

            formatted.append(f"{header}\n{doc}")

        # Convert deduplicated sources to list
        self.last_sources = list(seen_sources.values())

        return "\n\n".join(formatted)


class CourseOutlineTool(Tool):
    """Tool for retrieving course outlines with fuzzy course name matching"""

    def __init__(self, vector_store: VectorStore):
        self.store = vector_store
        self.last_sources: List[Source] = []

    def get_tool_definition(self) -> Dict[str, Any]:
        """Return Anthropic tool definition for this tool"""
        return {
            "name": "get_course_outline",
            "description": (
                "Retrieves the complete outline for a specific course, including "
                "the course title, course link, and a structured list of all lessons "
                "with their numbers and titles. Use this when users ask about course "
                "structure, topics covered, lesson organization, or what a course contains. "
                "Supports fuzzy course name matching (e.g., 'MCP' matches "
                "'MCP: Build Rich-Context AI Apps with Anthropic')."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "course_title": {
                        "type": "string",
                        "description": (
                            "The course title or partial course name. "
                            "Can be approximate (e.g., 'prompt engineering' or 'MCP')."
                        )
                    }
                },
                "required": ["course_title"]
            }
        }

    def execute(self, course_title: str) -> str:
        """
        Execute course outline retrieval with fuzzy matching.

        Args:
            course_title: Course name (exact or partial)

        Returns:
            Formatted string with course outline or error message
        """
        # Resolve fuzzy course name
        resolved_title = self.store._resolve_course_name(course_title)

        if not resolved_title:
            self.last_sources = []
            return f"Course not found: '{course_title}'. Please check the course name."

        # Retrieve all course metadata
        all_courses = self.store.get_all_courses_metadata()

        # Find specific course
        course_data = None
        for course in all_courses:
            if course.get('title') == resolved_title:
                course_data = course
                break

        if not course_data:
            self.last_sources = []
            return f"Error: Course metadata not available for '{resolved_title}'."

        # Track source using proper Source model
        source = Source(
            display_text=f"{course_data['title']} - Course Outline",
            course_title=course_data['title'],
            lesson_number=None,
            url=course_data.get('course_link')
        )
        self.last_sources = [source]

        # Format and return outline
        return self._format_outline(course_data)

    def _format_outline(self, course_data: dict) -> str:
        """Format course metadata into readable outline"""
        title = course_data.get('title', 'Unknown')
        link = course_data.get('course_link', 'N/A')
        instructor = course_data.get('instructor', 'N/A')
        lessons = course_data.get('lessons', [])
        lesson_count = course_data.get('lesson_count', len(lessons))

        # Build header
        outline = f"Course: {title}\n"
        outline += f"Course Link: {link}\n"
        outline += f"Instructor: {instructor}\n"
        outline += f"Total Lessons: {lesson_count}\n\n"
        outline += "Lesson Outline:\n"

        if not lessons:
            outline += "  (No lesson details available)\n"
            return outline

        # Format each lesson
        for lesson in lessons:
            lesson_num = lesson.get('lesson_number', '?')
            lesson_title = lesson.get('lesson_title', 'Untitled')
            lesson_link = lesson.get('lesson_link', '')

            outline += f"  Lesson {lesson_num}: {lesson_title}"
            if lesson_link:
                outline += f"\n    Link: {lesson_link}"
            outline += "\n"

        return outline


class ToolManager:
    """Manages available tools for the AI"""
    
    def __init__(self):
        self.tools = {}
    
    def register_tool(self, tool: Tool):
        """Register any tool that implements the Tool interface"""
        tool_def = tool.get_tool_definition()
        tool_name = tool_def.get("name")
        if not tool_name:
            raise ValueError("Tool must have a 'name' in its definition")
        self.tools[tool_name] = tool

    
    def get_tool_definitions(self) -> list:
        """Get all tool definitions for Anthropic tool calling"""
        return [tool.get_tool_definition() for tool in self.tools.values()]
    
    def execute_tool(self, tool_name: str, **kwargs) -> str:
        """Execute a tool by name with given parameters"""
        if tool_name not in self.tools:
            return f"Tool '{tool_name}' not found"
        
        return self.tools[tool_name].execute(**kwargs)
    
    def get_last_sources(self) -> List[Source]:
        """Get sources from the last search operation"""
        # Check all tools for last_sources attribute
        for tool in self.tools.values():
            if hasattr(tool, 'last_sources') and tool.last_sources:
                return tool.last_sources
        return []

    def reset_sources(self):
        """Reset sources from all tools that track sources"""
        for tool in self.tools.values():
            if hasattr(tool, 'last_sources'):
                tool.last_sources = []