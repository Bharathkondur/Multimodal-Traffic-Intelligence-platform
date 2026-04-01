"""
Processing package for Multimodal Traffic Intelligence Platform.

Exports core processing functions for detection, streaming, report generation,
session cleanup tasks, and demo simulation.
"""

from .detection import start_detection_pipeline
from .stream import start_stream_pipeline
from .simulator import TrafficSimulator
from .reports import generate_report_task
from .cleanup import cleanup_session

__all__ = [
    "start_detection_pipeline",
    "start_stream_pipeline",
    "TrafficSimulator",
    "generate_report_task",
    "cleanup_session",
]
