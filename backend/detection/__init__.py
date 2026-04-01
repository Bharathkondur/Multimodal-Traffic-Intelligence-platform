"""
Computer Vision Detection Engine for Multimodal Traffic Intelligence Platform.

This module provides comprehensive detection, tracking, and analysis capabilities
for traffic monitoring systems including vehicle detection, license plate reading,
object tracking, and incident detection.
"""

from .detector import (
    VehicleDetector,
    Detection,
    VehicleType,
)
from .tracker import (
    ObjectTracker,
    Track,
    TrackState,
)
from .plate_reader import (
    PlateReader,
    PlateDetection,
)
from .incident_detector import (
    IncidentDetector,
    Incident,
    IncidentType,
    IncidentSeverity,
)

__all__ = [
    # Detector
    "VehicleDetector",
    "Detection",
    "VehicleType",
    # Tracker
    "ObjectTracker",
    "Track",
    "TrackState",
    # Plate Reader
    "PlateReader",
    "PlateDetection",
    # Incident Detector
    "IncidentDetector",
    "Incident",
    "IncidentType",
    "IncidentSeverity",
]

__version__ = "1.0.0"
