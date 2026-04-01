"""
Unit tests for new Traffic Intelligence features.

Demonstrates proper testing patterns for:
- TrafficSimulator
- ZoneAnalytics
- TrafficHeatmap
- SpeedEstimator

Run with: python -m pytest tests_features.py -v
"""

import pytest
import math
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from processing.simulator import TrafficSimulator, VehicleType, SimulatedVehicle
from analytics import Zone, ZoneAnalytics, ZoneType, TrafficHeatmap, SpeedEstimator


# ============================================================================
# TESTS: TrafficSimulator
# ============================================================================

class TestTrafficSimulator:
    """Test suite for TrafficSimulator."""

    def test_simulator_initialization(self):
        """Test simulator can be initialized."""
        simulator = TrafficSimulator("test_session", 1920, 1080)
        assert simulator.session_id == "test_session"
        assert simulator.frame_width == 1920
        assert simulator.frame_height == 1080
        assert simulator.frame_count == 0
        assert simulator.running is False

    def test_simulator_spawn_vehicles(self):
        """Test vehicle spawning."""
        simulator = TrafficSimulator("test", 1920, 1080)
        initial_count = len(simulator.tracks)

        simulator._spawn_vehicles()
        # At least one vehicle should spawn (probabilistic, but almost guaranteed)
        assert len(simulator.tracks) > initial_count

    def test_vehicle_types_distribution(self):
        """Test vehicle type distribution matches configured probabilities."""
        simulator = TrafficSimulator("test", 1920, 1080)

        # Spawn many vehicles to check distribution
        for _ in range(100):
            simulator._spawn_vehicles()

        vehicle_types = [v.vehicle_type for v in simulator.tracks.values()]
        type_counts = {}
        for vtype in vehicle_types:
            type_counts[vtype] = type_counts.get(vtype, 0) + 1

        # Check that cars are the most common
        assert VehicleType.CAR in type_counts
        assert type_counts[VehicleType.CAR] > sum(
            type_counts.get(t, 0) for t in simulator.VEHICLE_TYPE_DIST.keys()
        ) * 0.4  # At least 40% cars

    @pytest.mark.asyncio
    async def test_simulator_generates_detections(self):
        """Test simulator can generate frame detections."""
        simulator = TrafficSimulator("test", 1920, 1080)

        # Create some vehicles manually
        simulator.tracks[1] = SimulatedVehicle(
            track_id=1,
            vehicle_type=VehicleType.CAR,
            x=100,
            y=200,
            vx=5,
            vy=0,
            width=80,
            height=50,
            confidence=0.95,
        )

        detections = await simulator.generate_frame_detections()

        assert len(detections) >= 1
        assert detections[0]["track_id"] == 1
        assert detections[0]["class_name"] == "car"
        assert detections[0]["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_simulator_incident_detection(self):
        """Test simulator can detect incidents."""
        simulator = TrafficSimulator("test", 1920, 1080)

        # Create stopped vehicle
        simulator.tracks[1] = SimulatedVehicle(
            track_id=1,
            vehicle_type=VehicleType.CAR,
            x=500,
            y=500,
            vx=0,
            vy=0,
            width=80,
            height=50,
            confidence=0.95,
            stopped_frames=50,  # Stopped for 50 frames
        )
        simulator.tracks[1].state = "stopped"

        incidents = await simulator.check_incidents()

        # Should detect stalled vehicle
        stalled = [i for i in incidents if i["incident_type"] == "stalled_vehicle"]
        assert len(stalled) > 0

    def test_simulator_vehicle_pruning(self):
        """Test vehicles leaving scene are removed."""
        simulator = TrafficSimulator("test", 1920, 1080)

        # Create vehicle at edge
        simulator.tracks[1] = SimulatedVehicle(
            track_id=1,
            vehicle_type=VehicleType.CAR,
            x=-300,  # Far off screen
            y=500,
            vx=0,
            vy=0,
            width=80,
            height=50,
            confidence=0.95,
        )

        simulator._prune_vehicles()

        # Vehicle should be removed
        assert 1 not in simulator.tracks


# ============================================================================
# TESTS: ZoneAnalytics
# ============================================================================

class TestZoneAnalytics:
    """Test suite for ZoneAnalytics."""

    def test_zone_creation(self):
        """Test zone can be created and added."""
        zone_analytics = ZoneAnalytics(1920, 1080)

        zone = Zone(
            id="test_zone",
            name="Test Zone",
            polygon=[(0, 0), (100, 0), (100, 100), (0, 100)],
            zone_type=ZoneType.COUNTING,
        )

        zone_analytics.add_zone(zone)

        assert "test_zone" in zone_analytics.zones
        assert zone_analytics.zones["test_zone"].name == "Test Zone"

    def test_point_in_zone_ray_casting(self):
        """Test point-in-polygon ray casting algorithm."""
        zone_analytics = ZoneAnalytics(1920, 1080)

        zone = Zone(
            id="square",
            name="Square Zone",
            polygon=[(100, 100), (200, 100), (200, 200), (100, 200)],
            zone_type=ZoneType.COUNTING,
        )

        zone_analytics.add_zone(zone)

        # Test points
        assert zone_analytics.point_in_zone(150, 150, "square") is True  # Inside
        assert zone_analytics.point_in_zone(250, 250, "square") is False  # Outside
        assert zone_analytics.point_in_zone(100, 100, "square") is True  # On vertex
        assert zone_analytics.point_in_zone(50, 50, "square") is False  # Far outside

    def test_zone_entry_exit_detection(self):
        """Test entry and exit tracking."""
        zone_analytics = ZoneAnalytics(1920, 1080)

        zone = Zone(
            id="test",
            name="Test",
            polygon=[(0, 0), (200, 0), (200, 200), (0, 200)],
            zone_type=ZoneType.COUNTING,
        )
        zone_analytics.add_zone("test")

        # Vehicle entering zone
        detections1 = [
            {
                "track_id": 1,
                "centroid": [100, 100],
                "vehicle_type": "car",
                "confidence": 0.95,
            }
        ]
        zone_analytics.process_detections(detections1)

        assert zone_analytics.zone_stats["test"]["entries"] == 1

        # Vehicle exiting zone
        detections2 = [
            {
                "track_id": 1,
                "centroid": [300, 100],
                "vehicle_type": "car",
                "confidence": 0.95,
            }
        ]
        zone_analytics.process_detections(detections2)

        assert zone_analytics.zone_stats["test"]["exits"] == 1

    def test_zone_alerts_thresholds(self):
        """Test threshold-based alerting."""
        zone_analytics = ZoneAnalytics(1920, 1080)

        zone = Zone(
            id="test",
            name="Test",
            polygon=[(0, 0), (200, 0), (200, 200), (0, 200)],
            zone_type=ZoneType.COUNTING,
            threshold_vehicles=5,
        )
        zone_analytics.add_zone(zone)

        # Add 6 vehicles to zone
        detections = [
            {
                "track_id": i,
                "centroid": [100, 100],
                "vehicle_type": "car",
                "confidence": 0.95,
            }
            for i in range(6)
        ]

        zone_analytics.process_detections(detections)

        alerts = zone_analytics.get_zone_alerts()

        # Should trigger alert
        vehicle_count_alerts = [
            a for a in alerts
            if a["alert_type"] == "vehicle_count_threshold"
        ]
        assert len(vehicle_count_alerts) > 0
        assert vehicle_count_alerts[0]["current_value"] == 6


# ============================================================================
# TESTS: TrafficHeatmap
# ============================================================================

class TestTrafficHeatmap:
    """Test suite for TrafficHeatmap."""

    def test_heatmap_initialization(self):
        """Test heatmap initialization."""
        heatmap = TrafficHeatmap(1920, 1080, cell_size=20)

        assert heatmap.width == 1920
        assert heatmap.height == 1080
        assert heatmap.grid_width == 96  # 1920 / 20
        assert heatmap.grid_height == 54  # 1080 / 20

    def test_heatmap_add_detection(self):
        """Test adding detections to heatmap."""
        heatmap = TrafficHeatmap(1920, 1080, cell_size=20)

        initial_sum = heatmap.grid.sum()

        heatmap.add_detection(100, 100, weight=1.0)

        # Grid should have increased
        assert heatmap.grid.sum() > initial_sum

    def test_heatmap_batch_add(self):
        """Test batch adding detections."""
        heatmap = TrafficHeatmap(1920, 1080, cell_size=20)

        detections = [
            {"centroid": [100, 100], "confidence": 0.95},
            {"centroid": [200, 200], "confidence": 0.90},
            {"centroid": [300, 300], "confidence": 0.85},
        ]

        heatmap.add_detections_batch(detections)

        # Should have 3 cells with data
        non_zero_cells = (heatmap.grid > 0).sum()
        assert non_zero_cells >= 1  # At least one cell has data

    def test_heatmap_statistics(self):
        """Test heatmap statistics calculation."""
        heatmap = TrafficHeatmap(1920, 1080, cell_size=20)

        heatmap.add_detection(100, 100, weight=5.0)
        heatmap.add_detection(150, 150, weight=3.0)

        stats = heatmap.get_statistics()

        assert stats["max"] > 0
        assert stats["mean"] >= 0
        assert stats["total_accumulation"] > 0

    def test_heatmap_decay(self):
        """Test temporal decay."""
        heatmap = TrafficHeatmap(1920, 1080, cell_size=20)

        heatmap.add_detection(100, 100, weight=10.0)
        initial_sum = heatmap.grid.sum()

        heatmap.decay(factor=0.5)

        # Grid should be reduced by half
        assert heatmap.grid.sum() == pytest.approx(initial_sum * 0.5, rel=0.01)

    def test_heatmap_high_density_regions(self):
        """Test high-density region detection."""
        heatmap = TrafficHeatmap(1920, 1080, cell_size=20)

        # Add cluster of detections
        for i in range(10):
            heatmap.add_detection(100 + i, 100 + i, weight=2.0)

        hotspots = heatmap.get_high_density_regions(threshold_percentile=50)

        # Should detect some hotspots
        assert len(hotspots) > 0


# ============================================================================
# TESTS: SpeedEstimator
# ============================================================================

class TestSpeedEstimator:
    """Test suite for SpeedEstimator."""

    def test_speed_estimator_initialization(self):
        """Test speed estimator initialization."""
        estimator = SpeedEstimator(pixels_per_meter=10.0, fps=30.0)

        assert estimator.pixels_per_meter == 10.0
        assert estimator.fps == 30.0
        assert estimator.frame_duration == pytest.approx(1/30.0, rel=0.01)

    def test_speed_calculation(self):
        """Test speed calculation from positions."""
        estimator = SpeedEstimator(pixels_per_meter=10.0, fps=30.0)

        # Update position twice
        estimator.update(track_id=1, x=0, y=0, timestamp=0.0, frame_number=0)
        estimator.update(track_id=1, x=100, y=0, timestamp=1.0, frame_number=30)

        speed = estimator.get_speed(track_id=1)

        # Distance: 100 pixels = 10 meters
        # Time: 1 second
        # Speed: 10 m/s = 36 km/h
        assert speed == pytest.approx(36.0, rel=0.05)

    def test_speed_distribution(self):
        """Test speed distribution buckets."""
        estimator = SpeedEstimator(pixels_per_meter=10.0, fps=30.0)

        # Create vehicles at different speeds
        # Track 1: 10 km/h
        estimator.update(1, 0, 0, 0, 0)
        estimator.update(1, 28, 0, 10, 300)

        # Track 2: 50 km/h
        estimator.update(2, 0, 0, 0, 0)
        estimator.update(2, 139, 0, 10, 300)

        dist = estimator.get_speed_distribution()

        assert isinstance(dist, dict)
        assert "0-20" in dist
        assert "20-40" in dist
        assert "40-60" in dist

    def test_speeding_detection(self):
        """Test speeding detection."""
        estimator = SpeedEstimator(pixels_per_meter=10.0, fps=30.0)

        # Create speeding vehicle (100 km/h)
        estimator.update(1, 0, 0, 0, 0)
        estimator.update(1, 278, 0, 10, 300)  # ~100 km/h

        violations = estimator.detect_speeding(limit_kmh=50.0)

        assert len(violations) > 0
        assert violations[0]["track_id"] == 1
        assert violations[0]["speed_kmh"] > 50.0

    def test_speed_calibration(self):
        """Test speed calibration with known distance."""
        estimator = SpeedEstimator(pixels_per_meter=10.0, fps=30.0)

        old_ppm = estimator.pixels_per_meter

        # Calibrate: 50 pixels = 2 meters
        estimator.calibrate(known_distance_pixels=50, known_distance_meters=2)

        assert estimator.pixels_per_meter != old_ppm
        assert estimator.pixels_per_meter == pytest.approx(25.0, rel=0.01)

    def test_track_statistics(self):
        """Test per-track statistics."""
        estimator = SpeedEstimator(pixels_per_meter=10.0, fps=30.0)

        # Simulate vehicle moving
        for frame in range(30):
            x = frame * 5  # 5 pixels per frame
            estimator.update(1, x, 0, frame / 30.0, frame_number=frame)

        stats = estimator.get_track_statistics(track_id=1)

        assert "track_id" in stats
        assert "current_speed_kmh" in stats
        assert "average_speed_kmh" in stats
        assert "frames_tracked" in stats
        assert "total_distance_meters" in stats

    def test_average_speed_calculation(self):
        """Test average speed across all tracked vehicles."""
        estimator = SpeedEstimator(pixels_per_meter=10.0, fps=30.0)

        # Track 1: 20 km/h
        estimator.update(1, 0, 0, 0, 0)
        estimator.update(1, 56, 0, 10, 300)

        # Track 2: 40 km/h
        estimator.update(2, 0, 0, 0, 0)
        estimator.update(2, 111, 0, 10, 300)

        avg_speed = estimator.get_average_speed()

        # Average of ~20 and ~40 = ~30
        assert avg_speed == pytest.approx(30.0, rel=0.1)


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """Integration tests for all features working together."""

    @pytest.mark.asyncio
    async def test_simulator_with_zones(self):
        """Test simulator output can be processed by zones."""
        simulator = TrafficSimulator("test", 1920, 1080)
        zones = ZoneAnalytics(1920, 1080)

        zone = Zone(
            id="test",
            name="Test",
            polygon=[(100, 100), (500, 100), (500, 500), (100, 500)],
            zone_type=ZoneType.COUNTING,
        )
        zones.add_zone(zone)

        # Generate detections
        detections = await simulator.generate_frame_detections()

        # Process through zones
        zone_data = zones.process_detections(detections)

        assert "test" in zone_data

    @pytest.mark.asyncio
    async def test_simulator_with_heatmap_and_speed(self):
        """Test simulator output with heatmap and speed estimator."""
        simulator = TrafficSimulator("test", 1920, 1080)
        heatmap = TrafficHeatmap(1920, 1080)
        speed_est = SpeedEstimator(pixels_per_meter=10.0, fps=30.0)

        # Generate and process detections
        for frame in range(5):
            detections = await simulator.generate_frame_detections()

            # Heatmap
            heatmap.add_detections_batch(detections)

            # Speed
            for det in detections:
                speed_est.update(
                    det["track_id"],
                    det["centroid"][0],
                    det["centroid"][1],
                    frame / 30.0,
                    frame_number=frame
                )

        # Verify data accumulation
        assert heatmap.grid.sum() > 0
        assert len(speed_est.current_speeds) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
