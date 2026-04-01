"""
Analytics package for Multimodal Traffic Intelligence Platform.

Provides traffic analysis tools including zone analytics, heatmap generation,
speed estimation, and related utilities.

Exports:
    - Zone: Zone definition dataclass
    - ZoneAnalytics: Zone-based traffic analysis
    - TrafficHeatmap: Heatmap generator for density visualization
    - SpeedEstimator: Speed estimation from tracking data
"""

from .zones import Zone, ZoneAnalytics, ZoneType
from .heatmap import TrafficHeatmap
from .speed import SpeedEstimator

__all__ = [
    "Zone",
    "ZoneAnalytics",
    "ZoneType",
    "TrafficHeatmap",
    "SpeedEstimator",
]
