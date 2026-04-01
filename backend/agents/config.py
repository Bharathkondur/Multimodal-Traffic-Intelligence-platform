"""
Configuration management for Traffic Intelligence Agent.

Provides environment-based configuration with sensible defaults
and type-safe configuration objects.
"""

import os
from enum import Enum
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class LLMBackend(str, Enum):
    """Available LLM backends."""
    OPENAI = "openai"
    OLLAMA = "ollama"
    GEMINI = "gemini"


class LogLevel(str, Enum):
    """Logging levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class OpenAIConfig:
    """OpenAI configuration."""
    api_key: str = os.getenv("OPENAI_API_KEY", "")
    model: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    temperature: float = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))
    max_tokens: Optional[int] = None
    request_timeout: int = 60

    def validate(self) -> bool:
        """Validate OpenAI configuration."""
        return bool(self.api_key)


@dataclass
class OllamaConfig:
    """Ollama configuration."""
    base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model: str = os.getenv("OLLAMA_MODEL", "llama3")
    temperature: float = float(os.getenv("OLLAMA_TEMPERATURE", "0.5"))
    num_predict: Optional[int] = None
    timeout: int = 300

    def validate(self) -> bool:
        """Validate Ollama configuration."""
        return bool(self.base_url)


@dataclass
class GeminiConfig:
    """Google Gemini configuration."""
    api_key: str = os.getenv("GOOGLE_API_KEY", "")
    model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    temperature: float = float(os.getenv("GEMINI_TEMPERATURE", "0.7"))
    max_output_tokens: Optional[int] = None

    def validate(self) -> bool:
        """Validate Gemini configuration."""
        return bool(self.api_key)


@dataclass
class RAGConfig:
    """RAG system configuration."""
    enabled: bool = os.getenv("RAG_ENABLED", "true").lower() == "true"
    embedding_dimension: int = int(os.getenv("RAG_EMBEDDING_DIM", "384"))
    use_faiss: bool = os.getenv("RAG_USE_FAISS", "false").lower() == "true"
    max_context_tokens: int = int(os.getenv("RAG_MAX_TOKENS", "8000"))
    retrieval_k: int = int(os.getenv("RAG_RETRIEVAL_K", "5"))


@dataclass
class AgentConfig:
    """Agent configuration."""
    llm_backend: LLMBackend = LLMBackend(
        os.getenv("LLM_BACKEND", "openai")
    )
    temperature: float = float(os.getenv("AGENT_TEMPERATURE", "0.7"))
    enable_streaming: bool = os.getenv("AGENT_STREAMING", "false").lower() == "true"
    timeout: int = int(os.getenv("AGENT_TIMEOUT", "300"))
    max_retries: int = int(os.getenv("AGENT_MAX_RETRIES", "3"))


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: LogLevel = LogLevel(os.getenv("LOG_LEVEL", "INFO"))
    format_string: str = (
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    log_file: Optional[str] = os.getenv("LOG_FILE", None)
    enable_file_logging: bool = (
        os.getenv("LOG_FILE_ENABLED", "false").lower() == "true"
    )


@dataclass
class TrafficAgentConfig:
    """Complete Traffic Agent configuration."""
    openai: OpenAIConfig = None
    ollama: OllamaConfig = None
    gemini: GeminiConfig = None
    rag: RAGConfig = None
    agent: AgentConfig = None
    logging: LoggingConfig = None

    def __post_init__(self):
        """Initialize nested configs."""
        if self.openai is None:
            self.openai = OpenAIConfig()
        if self.ollama is None:
            self.ollama = OllamaConfig()
        if self.gemini is None:
            self.gemini = GeminiConfig()
        if self.rag is None:
            self.rag = RAGConfig()
        if self.agent is None:
            self.agent = AgentConfig()
        if self.logging is None:
            self.logging = LoggingConfig()

    def validate(self) -> tuple[bool, list[str]]:
        """
        Validate configuration.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Check LLM backend availability
        if self.agent.llm_backend == LLMBackend.OPENAI:
            if not self.openai.validate():
                errors.append(
                    "OpenAI backend selected but OPENAI_API_KEY not set"
                )
        elif self.agent.llm_backend == LLMBackend.OLLAMA:
            if not self.ollama.validate():
                errors.append(
                    "Ollama backend selected but OLLAMA_BASE_URL not configured"
                )
        elif self.agent.llm_backend == LLMBackend.GEMINI:
            if not self.gemini.validate():
                errors.append(
                    "Gemini backend selected but GOOGLE_API_KEY not set. "
                    "Get a free key at https://aistudio.google.com/apikey"
                )

        # Check RAG config
        if self.rag.enabled and self.rag.use_faiss:
            try:
                import faiss  # noqa: F401
            except ImportError:
                errors.append(
                    "FAISS requested but not installed. "
                    "Install with: pip install faiss-cpu"
                )

        return len(errors) == 0, errors

    def to_dict(self) -> dict:
        """Convert configuration to dictionary."""
        return {
            "llm_backend": self.agent.llm_backend.value,
            "llm_model": (
                self.openai.model if self.agent.llm_backend == LLMBackend.OPENAI
                else self.gemini.model if self.agent.llm_backend == LLMBackend.GEMINI
                else self.ollama.model
            ),
            "temperature": self.agent.temperature,
            "streaming_enabled": self.agent.enable_streaming,
            "rag_enabled": self.rag.enabled,
            "embedding_dimension": self.rag.embedding_dimension,
            "log_level": self.logging.level.value,
        }

    def print_summary(self) -> None:
        """Print configuration summary."""
        print("\n" + "=" * 60)
        print("Traffic Intelligence Agent Configuration Summary")
        print("=" * 60)

        print(f"\nLLM Configuration:")
        print(f"  Backend: {self.agent.llm_backend.value}")

        if self.agent.llm_backend == LLMBackend.OPENAI:
            print(f"  Model: {self.openai.model}")
            print(f"  Temperature: {self.openai.temperature}")
        elif self.agent.llm_backend == LLMBackend.GEMINI:
            print(f"  Model: {self.gemini.model}")
            print(f"  Temperature: {self.gemini.temperature}")
            print(f"  API Key set: {'yes' if self.gemini.api_key else 'NO'}")
        else:
            print(f"  Model: {self.ollama.model}")
            print(f"  Base URL: {self.ollama.base_url}")
            print(f"  Temperature: {self.ollama.temperature}")

        print(f"\nAgent Configuration:")
        print(f"  Streaming: {self.agent.enable_streaming}")
        print(f"  Timeout: {self.agent.timeout}s")
        print(f"  Max Retries: {self.agent.max_retries}")

        print(f"\nRAG Configuration:")
        print(f"  Enabled: {self.rag.enabled}")
        if self.rag.enabled:
            print(f"  Embedding Dimension: {self.rag.embedding_dimension}")
            print(f"  Use FAISS: {self.rag.use_faiss}")
            print(f"  Max Context Tokens: {self.rag.max_context_tokens}")

        print(f"\nLogging Configuration:")
        print(f"  Level: {self.logging.level.value}")
        print(f"  File Logging: {self.logging.enable_file_logging}")
        if self.logging.log_file:
            print(f"  Log File: {self.logging.log_file}")

        print("=" * 60 + "\n")


# Global configuration instance
_config: Optional[TrafficAgentConfig] = None


def get_config() -> TrafficAgentConfig:
    """
    Get global configuration instance (lazy loaded).

    Returns:
        TrafficAgentConfig instance
    """
    global _config
    if _config is None:
        _config = TrafficAgentConfig()
    return _config


def load_config(config_path: Optional[str] = None) -> TrafficAgentConfig:
    """
    Load configuration from file or environment.

    Args:
        config_path: Optional path to .env file

    Returns:
        TrafficAgentConfig instance
    """
    global _config

    if config_path:
        load_dotenv(config_path)

    _config = TrafficAgentConfig()
    is_valid, errors = _config.validate()

    if not is_valid:
        print("Configuration Validation Errors:")
        for error in errors:
            print(f"  - {error}")

    return _config


def reset_config() -> None:
    """Reset global configuration instance."""
    global _config
    _config = None


# Example usage
if __name__ == "__main__":
    config = load_config()
    config.print_summary()

    is_valid, errors = config.validate()
    if not is_valid:
        print("Configuration is invalid:")
        for error in errors:
            print(f"  {error}")
    else:
        print("Configuration is valid!")
