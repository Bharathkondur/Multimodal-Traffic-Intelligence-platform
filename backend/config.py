"""
Application configuration module using Pydantic settings.

Loads configuration from environment variables with sensible defaults.
"""

from pydantic_settings import BaseSettings
from typing import Optional, List
import os


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Attributes:
        app_name: Application name
        debug: Debug mode flag
        database_url: SQLAlchemy database URL
        redis_url: Redis connection URL
        openai_api_key: OpenAI API key
        openai_model: OpenAI model name
        ollama_base_url: Ollama API base URL
        use_ollama: Whether to use Ollama instead of OpenAI
        model_path: Path to YOLOv8 model
        easyocr_model_path: Path to EasyOCR model cache
        upload_dir: Directory for uploaded files
        max_upload_size: Maximum upload file size in bytes
        detection_confidence_threshold: Confidence threshold for detections
        max_detections_per_frame: Maximum detections to keep per frame
        cors_origins: CORS allowed origins
        log_level: Logging level
    """

    # Application
    app_name: str = "Multimodal Scene Intelligence Platform"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://traffic_user:password@localhost/traffic_db"
    redis_url: str = "redis://localhost:6379/0"

    # LLM Configuration
    llm_provider: str = "gemini"          # gemini | openai | ollama
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"
    google_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_vision_model: str = "gemini-2.5-flash"

    # Model paths — YOLO26 by default (Jan 2026, NMS-free, 43% faster CPU).
    model_path: str = "yolo26s.pt"
    yolo_model_path: str = "yolo26s.pt"          # alias for env YOLO_MODEL_PATH
    yolo_pose_model_path: str = "yolo26s-pose.pt"
    easyocr_model_path: str = os.path.expanduser("~/.EasyOCR/model")

    # Upload configuration
    upload_dir: str = "/tmp/traffic_uploads"
    max_upload_size: int = 5 * 1024 * 1024 * 1024  # 5GB

    # Detection configuration
    detection_confidence_threshold: float = 0.45
    detection_iou_threshold: float = 0.45
    max_detections_per_frame: int = 300

    # Pose estimation (body keypoints for action heuristics)
    pose_enabled: bool = True
    pose_frame_interval: int = 3           # run pose every Nth detection frame

    # Live scene captioning (VLM)
    captioning_enabled: bool = True
    caption_interval_s: float = 3.0        # how often to send a frame to the VLM
    caption_max_tokens: int = 160
    caption_include_pose: bool = True

    # Rule engine / watchlist
    rules_enabled: bool = True
    max_rules_per_session: int = 20
    alert_cooldown_s: float = 15.0         # minimum gap between alerts of the same rule
    alert_snapshot_quality: int = 70       # JPEG quality for stored alert snapshots

    # CORS configuration
    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ]

    # Logging
    log_level: str = "INFO"

    # API Configuration
    api_version: str = "1.0.0"
    api_prefix: str = "/api"

    # Session configuration
    session_timeout_minutes: int = 1440  # 24 hours
    max_concurrent_sessions: int = 10

    # Stream configuration
    stream_buffer_size: int = 100
    stream_timeout_seconds: int = 300

    class Config:
        """Pydantic config."""

        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return not self.debug

    @property
    def active_llm_provider(self) -> str:
        """Get the configured LLM provider."""
        return self.llm_provider  # gemini | openai | ollama

    def get_database_url(self) -> str:
        """
        Get the database URL, replacing localhost for Docker if needed.

        Returns:
            Database connection URL
        """
        if os.getenv("DOCKER_ENV") == "true":
            return self.database_url.replace("localhost", "db")
        return self.database_url

    def get_redis_url(self) -> str:
        """
        Get the Redis URL, replacing localhost for Docker if needed.

        Returns:
            Redis connection URL
        """
        if os.getenv("DOCKER_ENV") == "true":
            return self.redis_url.replace("localhost", "redis")
        return self.redis_url


# Global settings instance
settings = Settings()
