"""
Traffic Simulator for demo/testing purposes.

Generates realistic simulated traffic detection data with natural movement patterns,
vehicle spawning, lane-based traffic, and periodic incidents. Useful for portfolio
demonstrations and testing the platform without a real video source.

Features:
    - Realistic vehicle spawning with Poisson distribution
    - Lane-based traffic with configurable directions
    - Natural vehicle movement with speed variation
    - Incident generation (stalled vehicles, congestion)
    - WebSocket broadcasting compatible with real pipeline
    - Database-compatible output format
"""

import asyncio
import logging
import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, List, Dict, Any
import math

import numpy as np

logger = logging.getLogger(__name__)


class VehicleType(str, Enum):
    """Vehicle types in simulation."""
    CAR = "car"
    TRUCK = "truck"
    BUS = "bus"
    MOTORCYCLE = "motorcycle"
    BICYCLE = "bicycle"


class VehicleState(str, Enum):
    """Vehicle movement state."""
    NORMAL = "normal"
    STOPPED = "stopped"
    ACCELERATING = "accelerating"
    DECELERATING = "decelerating"


@dataclass
class SimulatedVehicle:
    """Represents a simulated vehicle in the traffic scene."""
    track_id: int
    vehicle_type: VehicleType
    x: float
    y: float
    vx: float  # velocity x
    vy: float  # velocity y
    width: float
    height: float
    confidence: float
    state: VehicleState = VehicleState.NORMAL
    frames_in_scene: int = 0
    stopped_frames: int = 0


class TrafficSimulator:
    """
    Generates realistic simulated traffic detection data for demo purposes.

    A recruiter watching the dashboard should see natural-looking traffic with
    vehicles moving in lanes, realistic speed variations, periodic incidents,
    and statistics matching real traffic patterns.
    """

    # Video frame dimensions
    FRAME_WIDTH = 1920
    FRAME_HEIGHT = 1080

    # Lane configuration: 4 lanes (2 each direction)
    # Lanes 0-1: left-to-right (west-to-east)
    # Lanes 2-3: right-to-left (east-to-west)
    LANES = [
        {"y": 200, "direction": (1, 0), "name": "SB Lane 1"},
        {"y": 400, "direction": (1, 0), "name": "SB Lane 2"},
        {"y": 600, "direction": (-1, 0), "name": "NB Lane 1"},
        {"y": 800, "direction": (-1, 0), "name": "NB Lane 2"},
    ]

    # Vehicle type probabilities
    VEHICLE_TYPE_DIST = {
        VehicleType.CAR: 0.60,
        VehicleType.TRUCK: 0.15,
        VehicleType.BUS: 0.10,
        VehicleType.MOTORCYCLE: 0.10,
        VehicleType.BICYCLE: 0.05,
    }

    # Vehicle dimensions (width, height in pixels)
    VEHICLE_DIMS = {
        VehicleType.CAR: (80, 50),
        VehicleType.TRUCK: (120, 60),
        VehicleType.BUS: (100, 80),
        VehicleType.MOTORCYCLE: (40, 30),
        VehicleType.BICYCLE: (30, 40),
    }

    # Base speeds (pixels per frame at 30 FPS)
    BASE_SPEEDS = {
        VehicleType.CAR: 5.0,
        VehicleType.TRUCK: 3.5,
        VehicleType.BUS: 3.0,
        VehicleType.MOTORCYCLE: 6.0,
        VehicleType.BICYCLE: 1.5,
    }

    def __init__(self, session_id: str, frame_width: int = 1920, frame_height: int = 1080):
        """
        Initialize the simulator.

        Args:
            session_id: Unique identifier for this simulation session
            frame_width: Width of simulated video frames
            frame_height: Height of simulated video frames
        """
        self.session_id = session_id
        self.frame_width = frame_width
        self.frame_height = frame_height

        self.frame_count = 0
        self.tracks: Dict[int, SimulatedVehicle] = {}
        self.next_track_id = 1000
        self.running = False

        # Statistics tracking
        self.total_vehicles = 0
        self.current_vehicles = 0
        self.incident_count = 0

        # Timing
        self.last_incident_time = datetime.now()

        logger.info(
            f"TrafficSimulator initialized for session {session_id} "
            f"({frame_width}x{frame_height})"
        )

    async def start(
        self,
        fps: float = 10.0,
        duration_seconds: float = 300.0,
        broadcast_callback=None,
        db_callback=None,
    ) -> None:
        """
        Run simulation for specified duration.

        Generates realistic detection events and broadcasts via callbacks
        (WebSocket and database), matching the real pipeline interface.

        Args:
            fps: Frames per second for simulation
            duration_seconds: Duration to run simulation
            broadcast_callback: Async callback for WebSocket broadcast
            db_callback: Async callback for database storage
        """
        self.running = True
        frame_interval = 1.0 / fps
        start_time = datetime.now()
        frames_processed = 0

        logger.info(
            f"Starting simulation: {duration_seconds}s at {fps} FPS "
            f"({int(duration_seconds * fps)} frames)"
        )

        try:
            while self.running and (datetime.now() - start_time).total_seconds() < duration_seconds:
                self.frame_count += 1
                elapsed_time = (datetime.now() - start_time).total_seconds()

                # Generate detections for this frame
                detections = await self.generate_frame_detections()

                # Check for incidents
                incidents = await self.check_incidents()

                # Create frame data packet
                frame_data = {
                    "session_id": self.session_id,
                    "frame_count": self.frame_count,
                    "timestamp": datetime.now().isoformat(),
                    "detections": detections,
                    "incidents": incidents,
                    "statistics": {
                        "vehicles_in_scene": len(self.tracks),
                        "total_vehicles_processed": self.total_vehicles,
                        "incident_count": self.incident_count,
                    },
                }

                # Broadcast if callback provided
                if broadcast_callback:
                    try:
                        await broadcast_callback(frame_data)
                    except Exception as e:
                        logger.error(f"Broadcast callback error: {e}")

                # Store in database if callback provided
                if db_callback:
                    try:
                        await db_callback(frame_data)
                    except Exception as e:
                        logger.error(f"Database callback error: {e}")

                frames_processed += 1

                # Frame rate control
                await asyncio.sleep(frame_interval)

        except Exception as e:
            logger.error(f"Simulation error: {e}")
            self.running = False
        finally:
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"Simulation complete: processed {frames_processed} frames "
                f"in {elapsed:.1f}s ({self.total_vehicles} total vehicles detected)"
            )

    async def generate_frame_detections(self) -> List[Dict[str, Any]]:
        """
        Generate detections for one frame with realistic movement patterns.

        Returns:
            List of detection dictionaries compatible with the detection pipeline
        """
        # Spawn new vehicles (Poisson distribution)
        if random.random() < 0.3:  # ~30% chance per frame
            self._spawn_vehicles()

        # Update existing vehicle positions
        self._update_vehicle_positions()

        # Remove vehicles that left the scene
        self._prune_vehicles()

        # Convert to detection format
        detections = []
        for track_id, vehicle in self.tracks.items():
            x1 = vehicle.x - vehicle.width / 2
            y1 = vehicle.y - vehicle.height / 2
            x2 = x1 + vehicle.width
            y2 = y1 + vehicle.height

            # Clamp to frame bounds
            x1 = max(0, min(x1, self.frame_width))
            y1 = max(0, min(y1, self.frame_height))
            x2 = max(0, min(x2, self.frame_width))
            y2 = max(0, min(y2, self.frame_height))

            detection = {
                "track_id": track_id,
                "class_id": self._vehicle_type_to_class_id(vehicle.vehicle_type),
                "class_name": vehicle.vehicle_type.value,
                "confidence": vehicle.confidence,
                "bbox": [x1, y1, x2, y2],
                "centroid": [vehicle.x, vehicle.y],
                "area": vehicle.width * vehicle.height,
                "vehicle_type": vehicle.vehicle_type.value,
                "frame_index": self.frame_count,
            }
            detections.append(detection)

        self.current_vehicles = len(detections)
        return detections

    async def check_incidents(self) -> List[Dict[str, Any]]:
        """
        Check simulated tracks for incident conditions.

        Detects: stalled vehicles, congestion, unusual activity.

        Returns:
            List of incident dictionaries
        """
        incidents = []

        # Check for stopped vehicles (stalled incidents)
        for track_id, vehicle in self.tracks.items():
            if vehicle.state == VehicleState.STOPPED and vehicle.stopped_frames > 30:
                incidents.append({
                    "incident_type": "stalled_vehicle",
                    "severity": "high",
                    "track_id": track_id,
                    "location": [vehicle.x, vehicle.y],
                    "confidence": 0.95,
                    "timestamp": datetime.now().isoformat(),
                })

        # Check for congestion (high vehicle density)
        if len(self.tracks) > 15:
            incidents.append({
                "incident_type": "congestion",
                "severity": "medium",
                "vehicle_count": len(self.tracks),
                "location": [self.frame_width / 2, self.frame_height / 2],
                "confidence": 0.85,
                "timestamp": datetime.now().isoformat(),
            })

        # Periodically generate random incidents (every ~60 seconds)
        time_since_incident = (datetime.now() - self.last_incident_time).total_seconds()
        if time_since_incident > 60 and random.random() < 0.1:
            if self.tracks:
                random_vehicle = random.choice(list(self.tracks.values()))
                incidents.append({
                    "incident_type": "unusual_activity",
                    "severity": "low",
                    "location": [random_vehicle.x, random_vehicle.y],
                    "confidence": 0.7,
                    "timestamp": datetime.now().isoformat(),
                })
                self.last_incident_time = datetime.now()
                self.incident_count += 1

        return incidents

    def _spawn_vehicles(self) -> None:
        """Spawn new vehicles at random entry points."""
        num_to_spawn = random.randint(1, 3)

        for _ in range(num_to_spawn):
            lane = random.choice(self.LANES)
            vehicle_type = random.choices(
                list(self.VEHICLE_TYPE_DIST.keys()),
                weights=list(self.VEHICLE_TYPE_DIST.values()),
            )[0]

            width, height = self.VEHICLE_DIMS[vehicle_type]
            base_speed = self.BASE_SPEEDS[vehicle_type]

            # Spawn at edge based on lane direction
            if lane["direction"][0] > 0:  # Left to right
                x = -width
            else:  # Right to left
                x = self.frame_width + width

            y = lane["y"] + random.uniform(-10, 10)  # Add slight variance
            vx = lane["direction"][0] * base_speed * random.uniform(0.8, 1.2)
            vy = random.uniform(-0.1, 0.1)  # Slight vertical wandering

            vehicle = SimulatedVehicle(
                track_id=self.next_track_id,
                vehicle_type=vehicle_type,
                x=x,
                y=y,
                vx=vx,
                vy=vy,
                width=width,
                height=height,
                confidence=0.9 + random.uniform(-0.05, 0.05),
            )

            self.tracks[self.next_track_id] = vehicle
            self.next_track_id += 1
            self.total_vehicles += 1

    def _update_vehicle_positions(self) -> None:
        """Update vehicle positions with realistic physics."""
        for vehicle in self.tracks.values():
            # Apply state-based physics
            if vehicle.state == VehicleState.STOPPED:
                vehicle.stopped_frames += 1
                # Randomly recover from stopped state
                if vehicle.stopped_frames > 60 and random.random() < 0.05:
                    vehicle.state = VehicleState.NORMAL
                    vehicle.stopped_frames = 0
                    vehicle.vx *= 0.5
                    vehicle.vy *= 0.5
            else:
                # Normal movement with random perturbation
                if random.random() < 0.02:
                    # Randomly change state
                    vehicle.state = random.choice([
                        VehicleState.NORMAL,
                        VehicleState.ACCELERATING,
                        VehicleState.DECELERATING,
                        VehicleState.STOPPED,
                    ])

                if vehicle.state == VehicleState.ACCELERATING:
                    vehicle.vx *= 1.05
                elif vehicle.state == VehicleState.DECELERATING:
                    vehicle.vx *= 0.95
                elif vehicle.state == VehicleState.STOPPED:
                    vehicle.vx = 0
                    vehicle.vy = 0

            # Apply position update
            vehicle.x += vehicle.vx
            vehicle.y += vehicle.vy

            # Add lane-keeping behavior (return to lane center)
            for lane in self.LANES:
                if abs(vehicle.y - lane["y"]) < 100:
                    vehicle.y += (lane["y"] - vehicle.y) * 0.02
                    break

            vehicle.frames_in_scene += 1

    def _prune_vehicles(self) -> None:
        """Remove vehicles that have left the scene."""
        to_remove = []
        for track_id, vehicle in self.tracks.items():
            # Remove if completely off-screen with buffer
            buffer = 200
            if (vehicle.x < -buffer or vehicle.x > self.frame_width + buffer or
                vehicle.y < -buffer or vehicle.y > self.frame_height + buffer):
                to_remove.append(track_id)

        for track_id in to_remove:
            del self.tracks[track_id]

    @staticmethod
    def _vehicle_type_to_class_id(vehicle_type: VehicleType) -> int:
        """Map vehicle type to YOLO class ID."""
        mapping = {
            VehicleType.CAR: 2,
            VehicleType.TRUCK: 7,
            VehicleType.BUS: 5,
            VehicleType.MOTORCYCLE: 3,
            VehicleType.BICYCLE: 1,
        }
        return mapping.get(vehicle_type, 0)

    async def stop(self) -> None:
        """Stop the simulation."""
        self.running = False
        logger.info(f"Simulation stopped. Summary: {self.frame_count} frames, "
                   f"{self.total_vehicles} vehicles, {self.incident_count} incidents")

    def reset(self) -> None:
        """Reset simulator state for new simulation."""
        self.frame_count = 0
        self.tracks.clear()
        self.next_track_id = 1000
        self.total_vehicles = 0
        self.current_vehicles = 0
        self.incident_count = 0
        self.last_incident_time = datetime.now()
        logger.info(f"Simulator reset for session {self.session_id}")

    def get_statistics(self) -> Dict[str, Any]:
        """Get current simulation statistics."""
        return {
            "session_id": self.session_id,
            "frame_count": self.frame_count,
            "current_vehicles": self.current_vehicles,
            "total_vehicles_processed": self.total_vehicles,
            "incident_count": self.incident_count,
            "running": self.running,
            "timestamp": datetime.now().isoformat(),
        }
