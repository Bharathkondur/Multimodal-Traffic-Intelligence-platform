"""
Multi-object tracking module using ByteTrack/SORT approach.

Provides object tracking with Kalman filtering, IoU-based association,
and track lifecycle management for traffic surveillance.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Set, Tuple
from collections import deque
import numpy as np
from scipy import optimize

logger = logging.getLogger(__name__)


class TrackState(str, Enum):
    """State of a tracked object."""
    NEW = "new"
    ACTIVE = "active"
    LOST = "lost"
    REMOVED = "removed"


class KalmanFilter:
    """
    Simple Kalman filter for object trajectory prediction.

    Uses a constant-velocity model with state vector [x, y, vx, vy].
    """

    def __init__(self, dt: float = 1.0):
        """
        Initialize Kalman filter.

        Args:
            dt: Time step for prediction
        """
        self.dt = dt

        # State: [x, y, vx, vy]
        self.x = np.array([0.0, 0.0, 0.0, 0.0])

        # Covariance matrix
        self.P = np.eye(4) * 10.0

        # State transition matrix
        self.F = np.array([
            [1, 0, dt, 0],
            [0, 1, 0, dt],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ])

        # Measurement matrix (we only measure position)
        self.H = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0],
        ])

        # Process noise covariance
        self.Q = np.eye(4) * 0.01

        # Measurement noise covariance
        self.R = np.eye(2) * 10.0

    def predict(self) -> np.ndarray:
        """
        Predict next state.

        Returns:
            Predicted position [x, y]
        """
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        return self.x[:2]

    def update(self, measurement: np.ndarray) -> None:
        """
        Update state with measurement.

        Args:
            measurement: Measured position [x, y]
        """
        z = measurement
        y = z - (self.H @ self.x)

        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)

        self.x = self.x + (K @ y)
        self.P = (np.eye(4) - K @ self.H) @ self.P

    def initialize(self, position: np.ndarray, velocity: Optional[np.ndarray] = None) -> None:
        """
        Initialize filter with position and optional velocity.

        Args:
            position: Initial position [x, y]
            velocity: Initial velocity [vx, vy], defaults to zero
        """
        if velocity is None:
            velocity = np.array([0.0, 0.0])

        self.x = np.array([position[0], position[1], velocity[0], velocity[1]])
        self.P = np.eye(4) * 10.0


@dataclass
class Track:
    """
    Represents a tracked object across multiple frames.

    Attributes:
        track_id: Unique identifier for this track
        centroid: Current center position (x, y)
        bbox: Current bounding box (x1, y1, x2, y2)
        state: Current track state (NEW, ACTIVE, LOST, REMOVED)
        class_name: Detected object class (e.g., 'car', 'person')
        confidence: Latest detection confidence
        frames_since_detection: Frames since last positive detection
        age: Total number of frames this track has existed
        history: Deque of past centroids for trajectory analysis
        velocity: Estimated velocity [vx, vy]
        kalman_filter: Kalman filter for prediction
    """
    track_id: int
    centroid: Tuple[float, float]
    bbox: Tuple[float, float, float, float]
    state: TrackState
    class_name: str
    confidence: float
    frames_since_detection: int = 0
    age: int = 1
    history: deque = field(default_factory=lambda: deque(maxlen=30))
    velocity: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0]))
    kalman_filter: KalmanFilter = field(default_factory=KalmanFilter)

    def __post_init__(self):
        """Initialize history with first centroid."""
        self.history.append(self.centroid)
        self.kalman_filter.initialize(np.array(self.centroid), self.velocity)

    def update(
        self,
        centroid: Tuple[float, float],
        bbox: Tuple[float, float, float, float],
        confidence: float,
    ) -> None:
        """
        Update track with new detection.

        Args:
            centroid: New centroid position
            bbox: New bounding box
            confidence: Detection confidence
        """
        # Calculate velocity
        old_centroid = np.array(self.centroid)
        new_centroid = np.array(centroid)
        self.velocity = new_centroid - old_centroid

        self.centroid = centroid
        self.bbox = bbox
        self.confidence = confidence
        self.frames_since_detection = 0
        self.age += 1
        self.history.append(centroid)

        # Update Kalman filter
        self.kalman_filter.update(new_centroid)

        # Transition to ACTIVE if NEW
        if self.state == TrackState.NEW:
            self.state = TrackState.ACTIVE

    def predict_position(self) -> Tuple[float, float]:
        """
        Predict next position using Kalman filter.

        Returns:
            Predicted centroid position
        """
        predicted = self.kalman_filter.predict()
        return (float(predicted[0]), float(predicted[1]))

    def mark_lost(self) -> None:
        """Mark track as lost (no detection in current frame)."""
        self.frames_since_detection += 1
        if self.state == TrackState.ACTIVE:
            self.state = TrackState.LOST

    def mark_removed(self) -> None:
        """Mark track as removed (permanently lost)."""
        self.state = TrackState.REMOVED

    def get_trajectory(self) -> List[Tuple[float, float]]:
        """
        Get the trajectory history of this track.

        Returns:
            List of (x, y) positions in chronological order
        """
        return list(self.history)

    def is_confirmed(self) -> bool:
        """
        Check if track is confirmed (should be tracked actively).

        Returns:
            True if track is active or recently lost, False otherwise
        """
        return self.state in (TrackState.ACTIVE, TrackState.LOST)


class ObjectTracker:
    """
    Multi-object tracker using IoU-based association and Kalman filtering.

    Implements ByteTrack/SORT-like approach for robust object tracking.
    """

    def __init__(
        self,
        max_lost_frames: int = 30,
        iou_threshold: float = 0.3,
        min_confidence: float = 0.5,
        min_hits: int = 3,
    ):
        """
        Initialize object tracker.

        Args:
            max_lost_frames: Maximum frames to keep a lost track alive
            iou_threshold: Minimum IoU for matching detections to tracks
            min_confidence: Minimum confidence to start new track
            min_hits: Minimum detections to confirm a new track
        """
        self.max_lost_frames = max_lost_frames
        self.iou_threshold = iou_threshold
        self.min_confidence = min_confidence
        self.min_hits = min_hits

        self.tracks: Dict[int, Track] = {}
        self.next_track_id = 1
        self.frame_count = 0

        logger.info(
            f"ObjectTracker initialized: "
            f"max_lost={max_lost_frames}, iou_threshold={iou_threshold}"
        )

    def track(self, detections: List) -> List[Track]:
        """
        Update tracks with new detections.

        Args:
            detections: List of Detection objects from detector

        Returns:
            List of confirmed Track objects
        """
        self.frame_count += 1

        # Predict positions for all active tracks
        for track in self.tracks.values():
            if track.state in (TrackState.ACTIVE, TrackState.LOST):
                track.kalman_filter.predict()

        # Match detections to tracks
        matched, unmatched_dets, unmatched_trks = self._match_detections(detections)

        # Update matched tracks
        for det_idx, trk_idx in matched:
            detection = detections[det_idx]
            track = list(self.tracks.values())[trk_idx]
            track.update(
                centroid=detection.centroid,
                bbox=detection.bbox,
                confidence=detection.confidence,
            )

        # Create new tracks for unmatched detections
        for det_idx in unmatched_dets:
            detection = detections[det_idx]
            if detection.confidence >= self.min_confidence:
                self._create_track(detection)

        # Mark unmatched tracks as lost
        track_list = list(self.tracks.values())
        for trk_idx in unmatched_trks:
            track_list[trk_idx].mark_lost()

        # Remove old lost tracks
        self._cleanup_tracks()

        # Return confirmed tracks
        confirmed_tracks = [
            track for track in self.tracks.values()
            if track.is_confirmed()
        ]

        logger.debug(
            f"Frame {self.frame_count}: {len(confirmed_tracks)} tracked objects"
        )

        return confirmed_tracks

    def _match_detections(
        self,
        detections: List,
    ) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
        """
        Match detections to existing tracks using IoU.

        Args:
            detections: List of Detection objects

        Returns:
            Tuple of (matched_pairs, unmatched_detections, unmatched_tracks)
        """
        if not self.tracks or not detections:
            return [], list(range(len(detections))), list(range(len(self.tracks)))

        # Build IoU cost matrix
        tracks_list = list(self.tracks.values())
        cost_matrix = np.zeros((len(detections), len(tracks_list)))

        for i, detection in enumerate(detections):
            for j, track in enumerate(tracks_list):
                iou = self._compute_iou(detection.bbox, track.bbox)
                # Convert IoU to cost (higher IoU = lower cost)
                cost_matrix[i, j] = 1.0 - iou

        # Hungarian algorithm for optimal matching
        det_indices, trk_indices = optimize.linear_sum_assignment(cost_matrix)

        # Filter matches by IoU threshold
        matched = []
        matched_det_set = set()
        matched_trk_set = set()

        for det_idx, trk_idx in zip(det_indices, trk_indices):
            iou = 1.0 - cost_matrix[det_idx, trk_idx]
            if iou > self.iou_threshold:
                matched.append((det_idx, trk_idx))
                matched_det_set.add(det_idx)
                matched_trk_set.add(trk_idx)

        unmatched_dets = [i for i in range(len(detections)) if i not in matched_det_set]
        unmatched_trks = [i for i in range(len(tracks_list)) if i not in matched_trk_set]

        return matched, unmatched_dets, unmatched_trks

    @staticmethod
    def _compute_iou(bbox1: Tuple[float, float, float, float],
                     bbox2: Tuple[float, float, float, float]) -> float:
        """
        Compute Intersection over Union of two bounding boxes.

        Args:
            bbox1: Bounding box as (x1, y1, x2, y2)
            bbox2: Bounding box as (x1, y1, x2, y2)

        Returns:
            IoU score between 0 and 1
        """
        x1_min, y1_min, x1_max, y1_max = bbox1
        x2_min, y2_min, x2_max, y2_max = bbox2

        inter_xmin = max(x1_min, x2_min)
        inter_ymin = max(y1_min, y2_min)
        inter_xmax = min(x1_max, x2_max)
        inter_ymax = min(y1_max, y2_max)

        if inter_xmax < inter_xmin or inter_ymax < inter_ymin:
            return 0.0

        inter_area = (inter_xmax - inter_xmin) * (inter_ymax - inter_ymin)
        area1 = (x1_max - x1_min) * (y1_max - y1_min)
        area2 = (x2_max - x2_min) * (y2_max - y2_min)
        union_area = area1 + area2 - inter_area

        return inter_area / union_area if union_area > 0 else 0.0

    def _create_track(self, detection) -> None:
        """
        Create a new track from a detection.

        Args:
            detection: Detection object to create track from
        """
        track = Track(
            track_id=self.next_track_id,
            centroid=detection.centroid,
            bbox=detection.bbox,
            state=TrackState.NEW,
            class_name=detection.class_name,
            confidence=detection.confidence,
        )
        self.tracks[self.next_track_id] = track
        self.next_track_id += 1
        logger.debug(f"Created new track {track.track_id}")

    def _cleanup_tracks(self) -> None:
        """Remove old lost tracks that exceed max_lost_frames."""
        to_remove = []

        for track_id, track in self.tracks.items():
            if track.frames_since_detection > self.max_lost_frames:
                track.mark_removed()
                to_remove.append(track_id)

        for track_id in to_remove:
            del self.tracks[track_id]
            logger.debug(f"Removed track {track_id}")

    def get_tracks(self) -> List[Track]:
        """Get all active tracks."""
        return [
            track for track in self.tracks.values()
            if track.is_confirmed()
        ]

    def get_track_by_id(self, track_id: int) -> Optional[Track]:
        """
        Get a specific track by ID.

        Args:
            track_id: Track ID to retrieve

        Returns:
            Track object or None if not found
        """
        return self.tracks.get(track_id)

    def get_statistics(self) -> dict:
        """
        Get tracking statistics.

        Returns:
            Dictionary with tracking metrics
        """
        active = sum(1 for t in self.tracks.values() if t.state == TrackState.ACTIVE)
        lost = sum(1 for t in self.tracks.values() if t.state == TrackState.LOST)
        new = sum(1 for t in self.tracks.values() if t.state == TrackState.NEW)

        return {
            "frame_count": self.frame_count,
            "total_tracks": len(self.tracks),
            "active_tracks": active,
            "lost_tracks": lost,
            "new_tracks": new,
            "next_track_id": self.next_track_id,
        }
