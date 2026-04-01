"""
Video Stream Processing and WebSocket Layer for Multimodal Traffic Intelligence Platform.

This module provides real-time video stream processing capabilities and WebSocket
communication for live traffic monitoring, detection broadcasting, incident alerts,
and performance metrics tracking.
"""

from .processor import (
    StreamProcessor,
    StreamSource,
    StreamSourceType,
    ProcessingMetrics,
    ProcessingConfig,
)
from .websocket import (
    ConnectionManager,
    Channel,
    BroadcastMessage,
)

__all__ = [
    # Processor
    "StreamProcessor",
    "StreamSource",
    "StreamSourceType",
    "ProcessingMetrics",
    "ProcessingConfig",
    # WebSocket
    "ConnectionManager",
    "Channel",
    "BroadcastMessage",
]

__version__ = "1.0.0"
