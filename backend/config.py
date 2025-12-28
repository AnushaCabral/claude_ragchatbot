import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file in parent directory
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


@dataclass
class Config:
    """Configuration settings for the RAG system"""

    # Debug settings
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # LLM Provider settings
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "anthropic")

    # Anthropic API settings
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"

    # Groq API settings
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Embedding model settings
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    # Document processing settings
    CHUNK_SIZE: int = 800  # Size of text chunks for vector storage
    CHUNK_OVERLAP: int = 100  # Characters to overlap between chunks
    MAX_RESULTS: int = 5  # Maximum search results to return
    MAX_HISTORY: int = 2  # Number of conversation messages to remember

    # Response Token Budgets (adaptive based on query type)
    TOKEN_BUDGET_OUTLINE: int = 1500  # Course outline/structure queries
    TOKEN_BUDGET_COMPARISON: int = 2500  # Comparison/multi-course queries
    TOKEN_BUDGET_CONTENT: int = 1200  # Standard content search queries
    TOKEN_BUDGET_GENERAL: int = 1000  # General knowledge queries

    # Database paths
    CHROMA_PATH: str = "./chroma_db"  # ChromaDB storage location


config = Config()
