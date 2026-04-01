"""
Zone Analytics Engine for traffic monitoring.

Manages custom zones defined by users on the video feed and provides per-zone
analytics including vehicle counting, speed analysis, occupancy, and threshold
alerts. Uses point-in-polygon ray casting for accurate spatial analysis.

Features:
    - Create/manage custom zones (counting, speed traps, restricted areas, parking)
    - Directional counting (north, south, east, west)
    - Entry/exit tracking with persistent state
    - Real-time occupancy and vehicle type distribution
    - Speed analysis per zone
    - Threshold-based alerting
    - Temporal statistics (peak times, trends)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
import json

logger = logging.getLogger(__name__)


class ZoneType(str, Enum):
    """Types of zones for traffic analysis."""
    COUNTING = "counting"
    SPEED_TRAP = "speed_trap"
    RESTRICTED = "restricted"
    PARKING = "parking"


@dataclass
class Zone:
    """
    Represents a custom zone on the video feed.

    Zones are defined by polygonal boundaries and can track various
    metrics like vehicle counts, speeds, and occupancy.
    """
    id: str
    name: str
    polygon: List[Tuple[int, int]]  # List of (x, y) vertices defining the zone boundary
    zone_type: ZoneType
    direction: Optional[str] = None  # "north", "south", "east", "west" for directional counting
    threshold_vehicles: Optional[int] = None  # Alert if count exceeds this
    threshold_speed: Optional[float] = None  # Alert if speed exceeds this (km/h)
    threshold_occupancy: Optional[float] = None  # Alert if occupancy % exceeds this
    created_at: datetime = field(default_factory=datetime.now)
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert zone to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "polygon": self.polygon,
            "zone_type": self.zone_type.value,
            "direction": self.direction,
            "threshold_vehicles": self.threshold_vehicles,
            "threshold_speed": self.threshold_speed,
            "threshold_occupancy": self.threshold_occupancy,
            "created_at": self.created_at.isoformat(),
            "enabled": self.enabled,
        }


@dataclass
class ZoneStatistics:
    """Statistics for a specific zone."""
    zone_id: str
    vehicle_count: int = 0
    vehicles_by_type: Dict[str, int] = field(default_factory=dict)
    entry_count: int = 0
    exit_count: int = 0
    average_speed: float = 0.0
    occupancy_percentage: float = 0.0
    peak_time: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


class ZoneAnalytics:
    """
    Manages zones and provides per-zone traffic analytics.

    Uses point-in-polygon ray casting to determine zone membership and
    tracks entry/exit events for accurate vehicle counting.
    """

    def __init__(self, frame_width: int = 1920, frame_height: int = 1080):
        """
        Initialize zone analytics engine.

        Args:
            frame_width: Width of video frame
            frame_height: Height of video frame
        """
        self.zones: Dict[str, Zone] = {}
        self.frame_width = frame_width
        self.frame_height = frame_height

        # Track vehicle presence in zones (track_id -> {zone_id -> was_in_zone})
        self.vehicle_zone_state: Dict[int, Dict[str, bool]] = {}

        # Statistics accumulation
        self.zone_stats: Dict[str, Dict[str, Any]] = {}

        logger.info(f"ZoneAnalytics initialized for {frame_width}x{frame_height} frames")

    def add_zone(self, zone: Zone) -> None:
        """
        Add a new zone.

        Args:
            zone: Zone object to add
        """
        if zone.id in self.zones:
            logger.warning(f"Zone {zone.id} already exists, replacing")

        self.zones[zone.id] = zone
        self.zone_stats[zone.id] = {
            "vehicle_count": 0,
            "vehicles_by_type": {},
            "entries": 0,
            "exits": 0,
            "speeds": [],
            "first_detection_time": datetime.now(),
        }
        logger.info(f"Zone added: {zone.name} ({zone.id})")

    def remove_zone(self, zone_id: str) -> None:
        """
        Remove a zone.

        Args:
            zone_id: ID of zone to remove
        """
        if zone_id in self.zones:
            del self.zones[zone_id]
            if zone_id in self.zone_stats:
                del self.zone_stats[zone_id]
            logger.info(f"Zone removed: {zone_id}")
        else:
            logger.warning(f"Zone {zone_id} not found")

    def point_in_zone(self, x: float, y: float, zone_id: str) -> bool:
        """
        Check if a point is inside a zone using ray casting algorithm.

        Implements the ray casting (crossing number) algorithm for
        point-in-polygon detection. Efficient and handles concave polygons.

        Args:
            x: X coordinate of point
            y: Y coordinate of point
            zone_id: ID of zone to check against

        Returns:
            True if point is inside zone, False otherwise
        """
        if zone_id not in self.zones:
            return False

        zone = self.zones[zone_id]
        polygon = zone.polygon

        if len(polygon) < 3:
            return False

        # Ray casting algorithm
        crossing_count = 0
        n = len(polygon)

        for i in range(n):
            x1, y1 = polygon[i]
            x2, y2 = polygon[(i + 1) % n]

            # Check if horizontal ray from (x, y) crosses this edge
            if ((y1 <= y < y2) or (y2 <= y < y1)):
                # Calculate x-coordinate of intersection
                x_intersect = x1 + (y - y1) * (x2 - x1) / (y2 - y1)

                if x < x_intersect:
                    crossing_count += 1

        return crossing_count % 2 == 1

    def process_detections(self, detections: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Process detections and update zone statistics.

        Determines which detections are in which zones, tracks entries/exits,
        and updates all zone metrics.

        Args:
            detections: List of detection dictionaries with centroid data

        Returns:
            Dictionary mapping zone_id to zone data with updated metrics
        """
        # Initialize zone data for this batch
        zone_data = {
            zone_id: {
                "vehicles": [],
                "entries": 0,
                "exits": 0,
                "vehicle_types": {},
            }
            for zone_id in self.zones.keys()
        }

        # Process each detection
        for detection in detections:
            track_id = detection.get("track_id", detection.get("id"))
            centroid = detection.get("centroid", [0, 0])
            x, y = centroid[0], centroid[1]
            vehicle_type = detection.get("vehicle_type", "unknown")

            # Check which zones this vehicle is in
            for zone_id in self.zones.keys():
                if not self.zones[zone_id].enabled:
                    continue

                in_zone = self.point_in_zone(x, y, zone_id)

                # Initialize state tracking for this vehicle if needed
                if track_id not in self.vehicle_zone_state:
                    self.vehicle_zone_state[track_id] = {}

                was_in_zone = self.vehicle_zone_state[track_id].get(zone_id, False)

                # Detect entry
                if in_zone and not was_in_zone:
                    zone_data[zone_id]["entries"] += 1
                    self.zone_stats[zone_id]["entries"] += 1
                    logger.debug(f"Vehicle {track_id} entered zone {zone_id}")

                # Detect exit
                if not in_zone and was_in_zone:
                    zone_data[zone_id]["exits"] += 1
                    self.zone_stats[zone_id]["exits"] += 1
                    logger.debug(f"Vehicle {track_id} exited zone {zone_id}")

                # Update state
                self.vehicle_zone_state[track_id][zone_id] = in_zone

                # If in zone, collect data
                if in_zone:
                    zone_data[zone_id]["vehicles"].append(detection)
                    if vehicle_type not in zone_data[zone_id]["vehicle_types"]:
                        zone_data[zone_id]["vehicle_types"][vehicle_type] = 0
                    zone_data[zone_id]["vehicle_types"][vehicle_type] += 1

                    # Update stats
                    if vehicle_type not in self.zone_stats[zone_id]["vehicles_by_type"]:
                        self.zone_stats[zone_id]["vehicles_by_type"][vehicle_type] = 0
                    self.zone_stats[zone_id]["vehicles_by_type"][vehicle_type] += 1

        # Update current vehicle counts
        for zone_id, data in zone_data.items():
            self.zone_stats[zone_id]["vehicle_count"] = len(data["vehicles"])

        return zone_data

    def get_zone_stats(
        self,
        zone_id: str,
        time_range_minutes: int = 60
    ) -> Dict[str, Any]:
        """
        Get statistics for a specific zone.

        Provides vehicle count, type distribution, entry/exit counts,
        average speed, and peak activity time.

        Args:
            zone_id: ID of zone to get stats for
            time_range_minutes: Time range for statistics (not yet filtered)

        Returns:
            Dictionary with zone statistics
        """
        if zone_id not in self.zones:
            return {}

        stats = self.zone_stats.get(zone_id, {})
        zone = self.zones[zone_id]

        return {
            "zone_id": zone_id,
            "zone_name": zone.name,
            "zone_type": zone.zone_type.value,
            "vehicle_count": stats.get("vehicle_count", 0),
            "vehicles_by_type": stats.get("vehicles_by_type", {}),
            "total_entries": stats.get("entries", 0),
            "total_exits": stats.get("exits", 0),
            "average_speed_kmh": sum(stats.get("speeds", [0])) / max(len(stats.get("speeds", [1])), 1),
            "occupancy_percentage": 0.0,  # Can be calculated based on frame capacity
            "peak_time": stats.get("peak_time"),
            "time_range_minutes": time_range_minutes,
            "timestamp": datetime.now().isoformat(),
        }

    def get_zone_alerts(self) -> List[Dict[str, Any]]:
        """
        Check if any zone exceeds configured thresholds.

        Returns alerts for zones that violate their configured limits
        (vehicle count, speed, occupancy).

        Returns:
            List of alert dictionaries
        """
        alerts = []

        for zone_id, zone in self.zones.items():
            if not zone.enabled:
                continue

            stats = self.zone_stats.get(zone_id, {})
            current_count = stats.get("vehicle_count", 0)
            avg_speed = sum(stats.get("speeds", [0])) / max(len(stats.get("speeds", [1])), 1)

            # Check vehicle count threshold
            if zone.threshold_vehicles and current_count > zone.threshold_vehicles:
                alerts.append({
                    "zone_id": zone_id,
                    "zone_name": zone.name,
                    "alert_type": "vehicle_count_threshold",
                    "threshold": zone.threshold_vehicles,
                    "current_value": current_count,
                    "severity": "medium",
                    "timestamp": datetime.now().isoformat(),
                })

            # Check speed threshold
            if zone.threshold_speed and avg_speed > zone.threshold_speed:
                alerts.append({
                    "zone_id": zone_id,
                    "zone_name": zone.name,
                    "alert_type": "speed_threshold",
                    "threshold": zone.threshold_speed,
                    "current_value": avg_speed,
                    "severity": "high",
                    "timestamp": datetime.now().isoformat(),
                })

            # Check occupancy threshold
            if zone.threshold_occupancy:
                # Occupancy would need frame-level max capacity calculation
                occupancy = stats.get("occupancy_percentage", 0)
                if occupancy > zone.threshold_occupancy:
                    alerts.append({
                        "zone_id": zone_id,
                        "zone_name": zone.name,
                        "alert_type": "occupancy_threshold",
                        "threshold": zone.threshold_occupancy,
                        "current_value": occupancy,
                        "severity": "medium",
                        "timestamp": datetime.now().isoformat(),
                    })

        return alerts

    def add_speed_to_zone(self, zone_id: str, speed_kmh: float) -> None:
        """
        Add a speed measurement to a zone's speed statistics.

        Args:
            zone_id: ID of zone
            speed_kmh: Speed in km/h
        """
        if zone_id in self.zone_stats:
            self.zone_stats[zone_id]["speeds"].append(speed_kmh)

    def list_zones(self) -> List[Dict[str, Any]]:
        """
        Get list of all zones with their current statistics.

        Returns:
            List of zone dictionaries with current data
        """
        zones_list = []
        for zone_id, zone in self.zones.items():
            zone_dict = zone.to_dict()
            stats = self.zone_stats.get(zone_id, {})
            zone_dict["current_vehicles"] = stats.get("vehicle_count", 0)
            zone_dict["total_entries"] = stats.get("entries", 0)
            zone_dict["total_exits"] = stats.get("exits", 0)
            zones_list.append(zone_dict)
        return zones_list

    def reset_zone_stats(self, zone_id: Optional[str] = None) -> None:
        """
        Reset statistics for one or all zones.

        Args:
            zone_id: ID of zone to reset, or None to reset all
        """
        if zone_id:
            if zone_id in self.zone_stats:
                self.zone_stats[zone_id] = {
                    "vehicle_count": 0,
                    "vehicles_by_type": {},
                    "entries": 0,
                    "exits": 0,
                    "speeds": [],
                    "first_detection_time": datetime.now(),
                }
                logger.info(f"Reset stats for zone {zone_id}")
        else:
            for zone_id in self.zone_stats:
                self.zone_stats[zone_id] = {
                    "vehicle_count": 0,
                    "vehicles_by_type": {},
                    "entries": 0,
                    "exits": 0,
                    "speeds": [],
                    "first_detection_time": datetime.now(),
                }
            logger.info("Reset stats for all zones")
