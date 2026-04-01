"""
Rule-based and ML-based incident detection module.

Detects traffic incidents including stopped vehicles, wrong-way driving,
congestion, crowds, and accidents using track history and heuristics.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Set, Tuple
from datetime import datetime, timedelta
import numpy as np

logger = logging.getLogger(__name__)


class IncidentType(str, Enum):
    """Types of traffic incidents."""
    STOPPED_VEHICLE = "stopped_vehicle"
    WRONG_WAY_DRIVING = "wrong_way"
    CONGESTION = "congestion"
    CROWD = "crowd"
    ACCIDENT = "accident"
    COLLISION = "collision"
    ILLEGAL_PARKING = "illegal_parking"
    DEBRIS = "debris"
    PEDESTRIAN_VIOLATION = "pedestrian_violation"


class IncidentSeverity(str, Enum):
    """Incident severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Incident:
    """
    Represents a detected traffic incident.

    Attributes:
        incident_id: Unique incident identifier
        incident_type: Type of incident
        severity: Severity level
        location: Geographic location (x, y) or name
        involved_tracks: List of track IDs involved in this incident
        timestamp: When incident was first detected
        duration: How long the incident has existed
        confidence: Detection confidence (0-1)
        description: Human-readable description
        metadata: Additional incident-specific metadata
        is_active: Whether incident is still ongoing
    """
    incident_id: str
    incident_type: IncidentType
    severity: IncidentSeverity
    location: Tuple[float, float]
    involved_tracks: List[int] = field(default_factory=list)
    timestamp: Optional[datetime] = None
    duration: float = 0.0
    confidence: float = 0.5
    description: str = ""
    metadata: Dict = field(default_factory=dict)
    is_active: bool = True

    def __post_init__(self):
        """Initialize timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now()

    def update_duration(self) -> None:
        """Update incident duration."""
        if self.timestamp:
            elapsed = datetime.now() - self.timestamp
            self.duration = elapsed.total_seconds()

    def deactivate(self) -> None:
        """Mark incident as inactive (resolved)."""
        self.is_active = False
        self.update_duration()


class IncidentDetector:
    """
    Detects traffic incidents using rule-based and heuristic methods.

    Analyzes track history, velocities, and spatial relationships to identify
    various types of traffic incidents.
    """

    def __init__(
        self,
        stopped_vehicle_threshold: float = 1.0,  # pixels/frame
        stopped_duration_frames: int = 30,
        congestion_vehicle_count: int = 5,
        congestion_distance: float = 100.0,  # pixels
        crowd_person_count: int = 5,
        crowd_distance: float = 50.0,  # pixels
        collision_distance: float = 30.0,  # pixels
        collision_frames: int = 5,
        wrong_way_angle_threshold: float = 120.0,  # degrees
        incident_cooldown_frames: int = 60,
    ):
        """
        Initialize incident detector.

        Args:
            stopped_vehicle_threshold: Max velocity (pixels/frame) to be "stopped"
            stopped_duration_frames: Frames before vehicle is considered stopped
            congestion_vehicle_count: Min vehicles to constitute congestion
            congestion_distance: Max distance between vehicles for congestion
            crowd_person_count: Min persons to constitute a crowd
            crowd_distance: Max distance between persons for crowd
            collision_distance: Distance threshold for collision detection
            collision_frames: Frames to assess for collision
            wrong_way_angle_threshold: Angle threshold for wrong-way detection
            incident_cooldown_frames: Frames to wait before new incident of same type
        """
        self.stopped_vehicle_threshold = stopped_vehicle_threshold
        self.stopped_duration_frames = stopped_duration_frames
        self.congestion_vehicle_count = congestion_vehicle_count
        self.congestion_distance = congestion_distance
        self.crowd_person_count = crowd_person_count
        self.crowd_distance = crowd_distance
        self.collision_distance = collision_distance
        self.collision_frames = collision_frames
        self.wrong_way_angle_threshold = wrong_way_angle_threshold
        self.incident_cooldown_frames = incident_cooldown_frames

        self.incidents: Dict[str, Incident] = {}
        self.next_incident_id = 1
        self.incident_cooldown: Dict[Tuple[int, IncidentType], int] = {}

        logger.info("IncidentDetector initialized")

    def detect(self, tracks: List) -> List[Incident]:
        """
        Detect incidents from tracked objects.

        Args:
            tracks: List of Track objects from tracker

        Returns:
            List of detected Incident objects
        """
        detected_incidents = []

        # Detect stopped vehicles
        detected_incidents.extend(self._detect_stopped_vehicles(tracks))

        # Detect congestion
        detected_incidents.extend(self._detect_congestion(tracks))

        # Detect crowds
        detected_incidents.extend(self._detect_crowds(tracks))

        # Detect collisions
        detected_incidents.extend(self._detect_collisions(tracks))

        # Detect wrong-way driving
        detected_incidents.extend(self._detect_wrong_way_driving(tracks))

        # Register new incidents
        for incident in detected_incidents:
            self._register_incident(incident)

        # Update and remove expired incidents
        self._update_incident_status(tracks)

        logger.debug(f"Detected {len(detected_incidents)} incidents this frame")

        # Update cooldowns
        self._update_cooldowns()

        return detected_incidents

    def _detect_stopped_vehicles(self, tracks: List) -> List[Incident]:
        """
        Detect vehicles that have stopped or are moving very slowly.

        Args:
            tracks: List of Track objects

        Returns:
            List of Incident objects
        """
        incidents = []

        for track in tracks:
            if track.class_name not in ("car", "truck", "bus", "van"):
                continue

            # Calculate average velocity
            velocity_magnitude = np.linalg.norm(track.velocity)

            if velocity_magnitude < self.stopped_vehicle_threshold:
                # Check if stopped for sufficient duration
                if track.frames_since_detection < self.stopped_duration_frames:
                    continue

                # Check cooldown
                cooldown_key = (track.track_id, IncidentType.STOPPED_VEHICLE)
                if cooldown_key in self.incident_cooldown:
                    continue

                # Determine severity based on location and traffic context
                severity = self._assess_stopped_vehicle_severity(track, tracks)

                incident = Incident(
                    incident_id=f"stopped_{track.track_id}_{self.next_incident_id}",
                    incident_type=IncidentType.STOPPED_VEHICLE,
                    severity=severity,
                    location=track.centroid,
                    involved_tracks=[track.track_id],
                    confidence=0.8,
                    description=f"Vehicle {track.track_id} ({track.class_name}) stopped at {track.centroid}",
                    metadata={
                        "track_id": track.track_id,
                        "velocity": float(velocity_magnitude),
                        "class_name": track.class_name,
                    }
                )
                incidents.append(incident)
                self.incident_cooldown[cooldown_key] = self.incident_cooldown_frames

        return incidents

    def _detect_congestion(self, tracks: List) -> List[Incident]:
        """
        Detect traffic congestion (multiple vehicles in close proximity).

        Args:
            tracks: List of Track objects

        Returns:
            List of Incident objects
        """
        incidents = []

        # Get all vehicle tracks
        vehicle_tracks = [t for t in tracks if t.class_name in ("car", "truck", "bus", "van")]

        if len(vehicle_tracks) < self.congestion_vehicle_count:
            return incidents

        # Find clusters of vehicles
        clustered = self._cluster_tracks(
            vehicle_tracks,
            max_distance=self.congestion_distance,
        )

        for cluster_id, cluster_tracks in clustered.items():
            if len(cluster_tracks) >= self.congestion_vehicle_count:
                # Check if this is a new congestion
                cooldown_key = (cluster_id, IncidentType.CONGESTION)
                if cooldown_key in self.incident_cooldown:
                    continue

                # Calculate cluster centroid
                cluster_centroid = np.mean(
                    [np.array(t.centroid) for t in cluster_tracks],
                    axis=0,
                )

                # Assess average velocity
                avg_velocity = np.mean(
                    [np.linalg.norm(t.velocity) for t in cluster_tracks]
                )

                severity = self._assess_congestion_severity(
                    len(cluster_tracks),
                    avg_velocity,
                )

                incident = Incident(
                    incident_id=f"congestion_{self.next_incident_id}",
                    incident_type=IncidentType.CONGESTION,
                    severity=severity,
                    location=tuple(cluster_centroid),
                    involved_tracks=[t.track_id for t in cluster_tracks],
                    confidence=0.75,
                    description=f"Traffic congestion: {len(cluster_tracks)} vehicles",
                    metadata={
                        "vehicle_count": len(cluster_tracks),
                        "average_velocity": float(avg_velocity),
                    }
                )
                incidents.append(incident)
                self.incident_cooldown[cooldown_key] = self.incident_cooldown_frames

        return incidents

    def _detect_crowds(self, tracks: List) -> List[Incident]:
        """
        Detect crowds (multiple persons in close proximity).

        Args:
            tracks: List of Track objects

        Returns:
            List of Incident objects
        """
        incidents = []

        # Get all person tracks
        person_tracks = [t for t in tracks if t.class_name == "person"]

        if len(person_tracks) < self.crowd_person_count:
            return incidents

        # Find clusters of people
        clustered = self._cluster_tracks(
            person_tracks,
            max_distance=self.crowd_distance,
        )

        for cluster_id, cluster_tracks in clustered.items():
            if len(cluster_tracks) >= self.crowd_person_count:
                cooldown_key = (cluster_id, IncidentType.CROWD)
                if cooldown_key in self.incident_cooldown:
                    continue

                cluster_centroid = np.mean(
                    [np.array(t.centroid) for t in cluster_tracks],
                    axis=0,
                )

                severity = IncidentSeverity.MEDIUM if len(cluster_tracks) < 10 else IncidentSeverity.HIGH

                incident = Incident(
                    incident_id=f"crowd_{self.next_incident_id}",
                    incident_type=IncidentType.CROWD,
                    severity=severity,
                    location=tuple(cluster_centroid),
                    involved_tracks=[t.track_id for t in cluster_tracks],
                    confidence=0.7,
                    description=f"Crowd detected: {len(cluster_tracks)} persons",
                    metadata={
                        "person_count": len(cluster_tracks),
                    }
                )
                incidents.append(incident)
                self.incident_cooldown[cooldown_key] = self.incident_cooldown_frames

        return incidents

    def _detect_collisions(self, tracks: List) -> List[Incident]:
        """
        Detect potential collisions (vehicles in very close proximity with converging paths).

        Args:
            tracks: List of Track objects

        Returns:
            List of Incident objects
        """
        incidents = []

        vehicle_tracks = [t for t in tracks if t.class_name in ("car", "truck", "bus", "van")]

        for i, track1 in enumerate(vehicle_tracks):
            for track2 in vehicle_tracks[i+1:]:
                distance = np.linalg.norm(
                    np.array(track1.centroid) - np.array(track2.centroid)
                )

                if distance < self.collision_distance:
                    # Check if trajectories are converging
                    if self._trajectories_converging(track1, track2):
                        cooldown_key = (track1.track_id, IncidentType.COLLISION)
                        if cooldown_key in self.incident_cooldown:
                            continue

                        # Calculate midpoint
                        midpoint = (
                            (track1.centroid[0] + track2.centroid[0]) / 2,
                            (track1.centroid[1] + track2.centroid[1]) / 2,
                        )

                        incident = Incident(
                            incident_id=f"collision_{self.next_incident_id}",
                            incident_type=IncidentType.COLLISION,
                            severity=IncidentSeverity.CRITICAL,
                            location=midpoint,
                            involved_tracks=[track1.track_id, track2.track_id],
                            confidence=0.9,
                            description=f"Potential collision: vehicles {track1.track_id} and {track2.track_id}",
                            metadata={
                                "distance": float(distance),
                                "track_ids": [track1.track_id, track2.track_id],
                            }
                        )
                        incidents.append(incident)
                        self.incident_cooldown[cooldown_key] = self.incident_cooldown_frames

        return incidents

    def _detect_wrong_way_driving(self, tracks: List) -> List[Incident]:
        """
        Detect vehicles traveling in wrong direction.

        Args:
            tracks: List of Track objects

        Returns:
            List of Incident objects
        """
        incidents = []

        # Expected traffic direction (would come from road geometry in real system)
        # For now, use a simple heuristic based on majority of traffic
        expected_direction = self._estimate_traffic_direction(tracks)

        if expected_direction is None:
            return incidents

        for track in tracks:
            if track.class_name not in ("car", "truck", "bus", "motorcycle", "van"):
                continue

            # Skip if velocity is too low
            velocity_magnitude = np.linalg.norm(track.velocity)
            if velocity_magnitude < self.stopped_vehicle_threshold:
                continue

            # Get movement direction
            movement_direction = np.arctan2(track.velocity[1], track.velocity[0])
            expected_angle = expected_direction

            # Calculate angle difference
            angle_diff = np.degrees(abs(movement_direction - expected_angle))

            # Normalize to 0-180
            if angle_diff > 180:
                angle_diff = 360 - angle_diff

            if angle_diff > self.wrong_way_angle_threshold:
                cooldown_key = (track.track_id, IncidentType.WRONG_WAY_DRIVING)
                if cooldown_key in self.incident_cooldown:
                    continue

                incident = Incident(
                    incident_id=f"wrongway_{track.track_id}_{self.next_incident_id}",
                    incident_type=IncidentType.WRONG_WAY_DRIVING,
                    severity=IncidentSeverity.CRITICAL,
                    location=track.centroid,
                    involved_tracks=[track.track_id],
                    confidence=0.85,
                    description=f"Wrong-way vehicle {track.track_id} detected",
                    metadata={
                        "track_id": track.track_id,
                        "angle_diff": float(angle_diff),
                        "expected_angle": float(np.degrees(expected_angle)),
                    }
                )
                incidents.append(incident)
                self.incident_cooldown[cooldown_key] = self.incident_cooldown_frames

        return incidents

    @staticmethod
    def _cluster_tracks(
        tracks: List,
        max_distance: float,
    ) -> Dict[int, List]:
        """
        Cluster tracks by spatial proximity.

        Args:
            tracks: List of Track objects
            max_distance: Maximum distance for same cluster

        Returns:
            Dictionary mapping cluster IDs to lists of tracks
        """
        clusters: Dict[int, List] = {}
        track_to_cluster: Dict[int, int] = {}
        next_cluster_id = 0

        for track in tracks:
            assigned = False

            for other_track, cluster_id in track_to_cluster.items():
                distance = np.linalg.norm(
                    np.array(track.centroid) - np.array(other_track.centroid)
                )

                if distance < max_distance:
                    clusters[cluster_id].append(track)
                    track_to_cluster[track.track_id] = cluster_id
                    assigned = True
                    break

            if not assigned:
                clusters[next_cluster_id] = [track]
                track_to_cluster[track.track_id] = next_cluster_id
                next_cluster_id += 1

        return clusters

    @staticmethod
    def _trajectories_converging(track1, track2) -> bool:
        """
        Check if two tracks are on converging trajectories.

        Args:
            track1: First Track object
            track2: Second Track object

        Returns:
            True if trajectories are converging
        """
        v1 = track1.velocity
        v2 = track2.velocity

        # Vector from track1 to track2
        displacement = np.array(track2.centroid) - np.array(track1.centroid)

        if np.linalg.norm(displacement) < 1e-6:
            return True

        # Normalize
        displacement = displacement / np.linalg.norm(displacement)

        # Check if both are moving toward each other
        dot1 = np.dot(v1, displacement)
        dot2 = np.dot(v2, -displacement)

        return dot1 > 0 and dot2 > 0

    @staticmethod
    def _estimate_traffic_direction(tracks: List) -> Optional[float]:
        """
        Estimate the expected traffic direction from majority of tracks.

        Args:
            tracks: List of Track objects

        Returns:
            Expected direction in radians or None
        """
        vehicle_tracks = [t for t in tracks if t.class_name in ("car", "truck", "bus", "van")]

        if not vehicle_tracks:
            return None

        directions = []
        for track in vehicle_tracks:
            velocity_magnitude = np.linalg.norm(track.velocity)
            if velocity_magnitude > 1.0:  # Only moving vehicles
                direction = np.arctan2(track.velocity[1], track.velocity[0])
                directions.append(direction)

        if not directions:
            return None

        # Return median direction
        return np.median(directions)

    @staticmethod
    def _assess_stopped_vehicle_severity(track, all_tracks: List) -> IncidentSeverity:
        """
        Assess severity of stopped vehicle based on context.

        Args:
            track: Stopped Track object
            all_tracks: All Track objects for context

        Returns:
            IncidentSeverity level
        """
        # Check if in congested area
        nearby_vehicles = sum(
            1 for t in all_tracks
            if t.class_name in ("car", "truck", "bus", "van") and
            np.linalg.norm(np.array(t.centroid) - np.array(track.centroid)) < 200
        )

        if nearby_vehicles > 5:
            return IncidentSeverity.HIGH

        return IncidentSeverity.MEDIUM

    @staticmethod
    def _assess_congestion_severity(vehicle_count: int, avg_velocity: float) -> IncidentSeverity:
        """
        Assess severity of congestion.

        Args:
            vehicle_count: Number of vehicles in congestion
            avg_velocity: Average velocity of vehicles

        Returns:
            IncidentSeverity level
        """
        if vehicle_count > 15 and avg_velocity < 2.0:
            return IncidentSeverity.CRITICAL
        elif vehicle_count > 10 and avg_velocity < 3.0:
            return IncidentSeverity.HIGH
        else:
            return IncidentSeverity.MEDIUM

    def _register_incident(self, incident: Incident) -> None:
        """
        Register a new incident in the system.

        Args:
            incident: Incident to register
        """
        self.incidents[incident.incident_id] = incident
        self.next_incident_id += 1
        logger.info(
            f"Registered incident {incident.incident_id}: "
            f"{incident.incident_type.value} ({incident.severity.value})"
        )

    def _update_incident_status(self, tracks: List) -> None:
        """
        Update status of ongoing incidents.

        Args:
            tracks: List of Track objects
        """
        active_track_ids = {t.track_id for t in tracks}

        for incident_id, incident in list(self.incidents.items()):
            incident.update_duration()

            # Deactivate incident if involved tracks are gone
            if not any(tid in active_track_ids for tid in incident.involved_tracks):
                if incident.is_active:
                    incident.deactivate()
                    logger.info(f"Deactivated incident {incident_id}")

    def _update_cooldowns(self) -> None:
        """Decrement cooldown timers."""
        expired_cooldowns = []

        for key, remaining in self.incident_cooldown.items():
            remaining -= 1
            if remaining <= 0:
                expired_cooldowns.append(key)
            else:
                self.incident_cooldown[key] = remaining

        for key in expired_cooldowns:
            del self.incident_cooldown[key]

    def get_active_incidents(self) -> List[Incident]:
        """
        Get all active incidents.

        Returns:
            List of active Incident objects
        """
        return [
            incident for incident in self.incidents.values()
            if incident.is_active
        ]

    def get_incidents_by_type(self, incident_type: IncidentType) -> List[Incident]:
        """
        Get incidents of a specific type.

        Args:
            incident_type: IncidentType to filter by

        Returns:
            List of matching Incident objects
        """
        return [
            incident for incident in self.incidents.values()
            if incident.incident_type == incident_type
        ]

    def get_statistics(self) -> dict:
        """
        Get incident detection statistics.

        Returns:
            Dictionary with statistics
        """
        active = self.get_active_incidents()

        return {
            "total_incidents": len(self.incidents),
            "active_incidents": len(active),
            "by_type": {
                incident_type.value: len(self.get_incidents_by_type(incident_type))
                for incident_type in IncidentType
            },
            "by_severity": {
                severity.value: sum(1 for i in active if i.severity == severity)
                for severity in IncidentSeverity
            },
        }
