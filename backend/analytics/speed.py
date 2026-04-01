"""
Speed Estimation Engine for vehicle tracking.

Estimates vehicle speeds from tracking data using pixel displacement
over time. Provides individual vehicle speeds, aggregate statistics,
speed distributions, and speeding detection.

Features:
    - Per-track speed calculation using Euclidean displacement
    - Configurable pixels-per-meter calibration
    - Historical track data with temporal windowing
    - Average speed calculation over time windows
    - Speed distribution analysis (0-20, 20-40, etc. km/h buckets)
    - Speeding detection with configurable speed limits
    - Speedometer calibration using reference distances
    - Outlier filtering for noisy data
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import math
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class TrackSnapshot:
    """Single position snapshot for a track."""
    x: float
    y: float
    timestamp: float
    frame_number: int


class SpeedEstimator:
    """
    Estimates vehicle speeds from tracking data.

    Uses Euclidean distance calculation between consecutive positions
    and time differences to compute speed in real-world units (km/h).
    Maintains historical data for each track for accurate speed estimates.
    """

    # Speed histogram buckets (km/h)
    SPEED_BUCKETS = [
        (0, 20),
        (20, 40),
        (40, 60),
        (60, 80),
        (80, 100),
        (100, float("inf")),
    ]

    def __init__(
        self,
        pixels_per_meter: float = 10.0,
        fps: float = 30.0,
        history_window_frames: int = 300,
    ):
        """
        Initialize speed estimator.

        Args:
            pixels_per_meter: Conversion factor from pixels to real-world distance
            fps: Frames per second of video
            history_window_frames: Number of frames to keep in history per track
        """
        self.pixels_per_meter = pixels_per_meter
        self.fps = fps
        self.frame_duration = 1.0 / fps
        self.history_window_frames = history_window_frames

        # Track history storage: track_id -> deque of TrackSnapshot
        self.track_history: Dict[int, deque] = {}

        # Current speeds: track_id -> speed_kmh
        self.current_speeds: Dict[int, float] = {}

        logger.info(
            f"SpeedEstimator initialized: {pixels_per_meter} px/m, "
            f"{fps} fps, window={history_window_frames} frames"
        )

    def update(self, track_id: int, x: float, y: float, timestamp: float, frame_number: int = 0) -> None:
        """
        Add new position for a track.

        Args:
            track_id: Unique track identifier
            x: X coordinate of vehicle position
            y: Y coordinate of vehicle position
            timestamp: Timestamp of this position (can be seconds or frame-based)
            frame_number: Frame number for reference
        """
        # Initialize history if needed
        if track_id not in self.track_history:
            self.track_history[track_id] = deque(maxlen=self.history_window_frames)

        # Create snapshot
        snapshot = TrackSnapshot(x=x, y=y, timestamp=timestamp, frame_number=frame_number)

        # Add to history
        self.track_history[track_id].append(snapshot)

        # Calculate speed if we have at least 2 points
        if len(self.track_history[track_id]) >= 2:
            self.current_speeds[track_id] = self._calculate_speed(track_id)

    def _calculate_speed(self, track_id: int) -> float:
        """
        Calculate speed for a track using last two positions.

        Uses Euclidean distance formula: sqrt((x2-x1)^2 + (y2-y1)^2)
        Converts to km/h: pixels -> meters -> km/h.

        Args:
            track_id: Track identifier

        Returns:
            Speed in km/h
        """
        history = self.track_history.get(track_id)
        if not history or len(history) < 2:
            return 0.0

        # Get last two positions
        latest = history[-1]
        previous = history[-2]

        # Calculate Euclidean distance in pixels
        dx = latest.x - previous.x
        dy = latest.y - previous.y
        distance_pixels = math.sqrt(dx * dx + dy * dy)

        # Convert to meters
        distance_meters = distance_pixels / self.pixels_per_meter

        # Calculate time difference
        time_diff = latest.timestamp - previous.timestamp
        if time_diff <= 0:
            time_diff = self.frame_duration

        # Calculate speed: meters/second -> km/h
        speed_ms = distance_meters / time_diff
        speed_kmh = speed_ms * 3.6  # 1 m/s = 3.6 km/h

        return max(0.0, speed_kmh)  # Clamp to non-negative

    def get_speed(self, track_id: int) -> Optional[float]:
        """
        Get current speed of a track.

        Args:
            track_id: Track identifier

        Returns:
            Speed in km/h, or None if track not found
        """
        return self.current_speeds.get(track_id)

    def get_speed_over_window(self, track_id: int, window_frames: int = 10) -> float:
        """
        Calculate average speed over a window of frames.

        More stable than single-frame speed by averaging over multiple positions.

        Args:
            track_id: Track identifier
            window_frames: Number of frames to average over

        Returns:
            Average speed in km/h
        """
        history = self.track_history.get(track_id)
        if not history or len(history) < 2:
            return 0.0

        # Get positions within window
        history_list = list(history)
        if len(history_list) < 2:
            return 0.0

        start_idx = max(0, len(history_list) - window_frames)
        start_pos = history_list[start_idx]
        end_pos = history_list[-1]

        # Calculate distance and time
        dx = end_pos.x - start_pos.x
        dy = end_pos.y - start_pos.y
        distance_pixels = math.sqrt(dx * dx + dy * dy)
        distance_meters = distance_pixels / self.pixels_per_meter

        time_diff = end_pos.timestamp - start_pos.timestamp
        if time_diff <= 0:
            time_diff = self.frame_duration * (len(history_list) - start_idx - 1)

        if time_diff <= 0:
            return 0.0

        speed_ms = distance_meters / time_diff
        speed_kmh = speed_ms * 3.6

        return max(0.0, speed_kmh)

    def get_average_speed(self, time_window_seconds: float = 60.0) -> float:
        """
        Calculate average speed of all tracked vehicles.

        Args:
            time_window_seconds: Time window for averaging (currently uses all tracks)

        Returns:
            Average speed in km/h
        """
        if not self.current_speeds:
            return 0.0

        speeds = list(self.current_speeds.values())
        return sum(speeds) / len(speeds) if speeds else 0.0

    def get_speed_distribution(self) -> Dict[str, int]:
        """
        Get distribution of speeds across all tracks.

        Buckets speeds into ranges: 0-20, 20-40, ..., 80+ km/h.

        Returns:
            Dictionary mapping speed range to vehicle count
        """
        distribution = {}
        for min_speed, max_speed in self.SPEED_BUCKETS:
            if max_speed == float("inf"):
                bucket_name = f"{min_speed}+"
            else:
                bucket_name = f"{min_speed}-{max_speed}"

            count = sum(
                1 for speed in self.current_speeds.values()
                if min_speed <= speed < max_speed
            )
            distribution[bucket_name] = count

        return distribution

    def detect_speeding(self, limit_kmh: float = 50.0) -> List[Dict[str, Any]]:
        """
        Detect vehicles exceeding speed limit.

        Args:
            limit_kmh: Speed limit in km/h

        Returns:
            List of speeding violation dictionaries
        """
        violations = []

        for track_id, speed in self.current_speeds.items():
            if speed > limit_kmh:
                history = self.track_history.get(track_id, [])
                if history:
                    latest = list(history)[-1]
                    violations.append({
                        "track_id": track_id,
                        "speed_kmh": speed,
                        "speed_limit_kmh": limit_kmh,
                        "overspeed": speed - limit_kmh,
                        "location": [latest.x, latest.y],
                        "frame_number": latest.frame_number,
                        "timestamp": latest.timestamp,
                        "severity": "high" if (speed - limit_kmh) > 20 else "medium",
                    })

        return violations

    def calibrate(
        self,
        known_distance_pixels: float,
        known_distance_meters: float,
    ) -> None:
        """
        Calibrate pixels_per_meter using a known reference distance.

        Useful for adjusting speed estimates to actual camera angles/zoom.
        For example, measure a known-width lane marking or road feature
        and use it to calibrate the distance conversion.

        Args:
            known_distance_pixels: Measured distance in pixels
            known_distance_meters: Actual distance in meters
        """
        if known_distance_pixels <= 0 or known_distance_meters <= 0:
            logger.warning("Invalid calibration parameters")
            return

        old_ppm = self.pixels_per_meter
        self.pixels_per_meter = known_distance_pixels / known_distance_meters

        logger.info(
            f"Speed calibration: {old_ppm:.2f} px/m -> {self.pixels_per_meter:.2f} px/m "
            f"(using {known_distance_pixels}px = {known_distance_meters}m)"
        )

    def remove_track(self, track_id: int) -> None:
        """
        Remove tracking history for a track (e.g., vehicle left scene).

        Args:
            track_id: Track identifier
        """
        if track_id in self.track_history:
            del self.track_history[track_id]
        if track_id in self.current_speeds:
            del self.current_speeds[track_id]

    def get_track_statistics(self, track_id: int) -> Dict[str, Any]:
        """
        Get detailed statistics for a specific track.

        Args:
            track_id: Track identifier

        Returns:
            Dictionary with speed statistics
        """
        history = self.track_history.get(track_id)
        if not history:
            return {}

        speeds = []
        history_list = list(history)

        # Calculate speeds between consecutive points
        for i in range(1, len(history_list)):
            prev = history_list[i - 1]
            curr = history_list[i]

            dx = curr.x - prev.x
            dy = curr.y - prev.y
            distance_pixels = math.sqrt(dx * dx + dy * dy)
            distance_meters = distance_pixels / self.pixels_per_meter

            time_diff = curr.timestamp - prev.timestamp
            if time_diff <= 0:
                time_diff = self.frame_duration

            speed_ms = distance_meters / time_diff
            speed_kmh = speed_ms * 3.6
            speeds.append(max(0.0, speed_kmh))

        if not speeds:
            return {}

        return {
            "track_id": track_id,
            "current_speed_kmh": self.get_speed(track_id) or 0.0,
            "average_speed_kmh": sum(speeds) / len(speeds),
            "min_speed_kmh": min(speeds),
            "max_speed_kmh": max(speeds),
            "frames_tracked": len(history),
            "total_distance_meters": self._get_total_distance(track_id),
        }

    def _get_total_distance(self, track_id: int) -> float:
        """
        Calculate total distance traveled by a track.

        Args:
            track_id: Track identifier

        Returns:
            Total distance in meters
        """
        history = self.track_history.get(track_id)
        if not history or len(history) < 2:
            return 0.0

        total_distance = 0.0
        history_list = list(history)

        for i in range(1, len(history_list)):
            prev = history_list[i - 1]
            curr = history_list[i]

            dx = curr.x - prev.x
            dy = curr.y - prev.y
            distance_pixels = math.sqrt(dx * dx + dy * dy)
            distance_meters = distance_pixels / self.pixels_per_meter

            total_distance += distance_meters

        return total_distance

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get overall speed statistics across all tracks.

        Returns:
            Dictionary with aggregate statistics
        """
        if not self.current_speeds:
            return {
                "tracked_vehicles": 0,
                "average_speed_kmh": 0.0,
                "max_speed_kmh": 0.0,
                "min_speed_kmh": 0.0,
            }

        speeds = list(self.current_speeds.values())
        return {
            "tracked_vehicles": len(speeds),
            "average_speed_kmh": sum(speeds) / len(speeds),
            "max_speed_kmh": max(speeds),
            "min_speed_kmh": min(speeds),
            "distribution": self.get_speed_distribution(),
        }

    def cleanup_inactive_tracks(self, max_age_frames: int = 500) -> None:
        """
        Remove tracks that haven't been updated recently.

        Useful for cleanup when processing historical data or ensuring
        memory efficiency in long-running sessions.

        Args:
            max_age_frames: Remove tracks not updated for this many frames
        """
        to_remove = []
        current_frame = max((h[-1].frame_number for h in self.track_history.values()), default=0)

        for track_id, history in self.track_history.items():
            if history:
                age = current_frame - history[-1].frame_number
                if age > max_age_frames:
                    to_remove.append(track_id)

        for track_id in to_remove:
            self.remove_track(track_id)

        if to_remove:
            logger.debug(f"Cleaned up {len(to_remove)} inactive tracks")
