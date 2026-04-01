"""
Integration Example: Using Traffic Intelligence Features Together

This example demonstrates how to integrate all four new features:
1. Demo/Simulation Mode (simulator.py)
2. Zone Analytics Engine (analytics/zones.py)
3. Heatmap Generator (analytics/heatmap.py)
4. Speed Estimation (analytics/speed.py)

Perfect for portfolio presentations and understanding feature usage.
"""

import asyncio
import logging
from datetime import datetime

from backend.processing.simulator import TrafficSimulator
from backend.analytics import ZoneAnalytics, Zone, ZoneType, TrafficHeatmap, SpeedEstimator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def demo_complete_system():
    """
    Demonstrate the complete traffic intelligence system with all features.

    This example shows:
    - Running a realistic traffic simulation
    - Creating custom zones and tracking traffic within them
    - Generating heatmaps from detection data
    - Estimating vehicle speeds
    - Detecting incidents and speed violations
    """

    # ============================================================================
    # SETUP
    # ============================================================================
    session_id = "demo_session_001"
    frame_width, frame_height = 1920, 1080

    # Initialize components
    simulator = TrafficSimulator(session_id, frame_width, frame_height)
    zone_analytics = ZoneAnalytics(frame_width, frame_height)
    heatmap = TrafficHeatmap(frame_width, frame_height, cell_size=20)
    speed_estimator = SpeedEstimator(pixels_per_meter=10.0, fps=30.0)

    # ============================================================================
    # ZONE SETUP
    # ============================================================================
    # Define zones for traffic monitoring

    # Zone 1: Intersection counting area (rectangular)
    intersection_zone = Zone(
        id="zone_intersection",
        name="Main Intersection",
        polygon=[
            (400, 300),
            (1000, 300),
            (1000, 700),
            (400, 700),
        ],
        zone_type=ZoneType.COUNTING,
        direction="north",
        threshold_vehicles=20,  # Alert if > 20 vehicles
    )
    zone_analytics.add_zone(intersection_zone)

    # Zone 2: Speed trap area
    speed_trap_zone = Zone(
        id="zone_speed_trap",
        name="Speed Monitoring Corridor",
        polygon=[
            (100, 150),
            (500, 100),
            (600, 450),
            (200, 500),
        ],
        zone_type=ZoneType.SPEED_TRAP,
        threshold_speed=50.0,  # Alert if speed > 50 km/h
    )
    zone_analytics.add_zone(speed_trap_zone)

    # Zone 3: Restricted area
    restricted_zone = Zone(
        id="zone_restricted",
        name="Restricted Parking Area",
        polygon=[
            (1400, 800),
            (1800, 750),
            (1850, 1000),
            (1400, 1050),
        ],
        zone_type=ZoneType.RESTRICTED,
    )
    zone_analytics.add_zone(restricted_zone)

    logger.info(f"Created {len(zone_analytics.zones)} monitoring zones")

    # ============================================================================
    # CALLBACKS FOR DATA PROCESSING
    # ============================================================================

    async def on_frame_generated(frame_data):
        """
        Process simulated frame data through all analytics components.

        This callback is called for each generated frame and demonstrates
        the full analytics pipeline.
        """
        detections = frame_data.get("detections", [])
        timestamp = frame_data.get("timestamp", datetime.now().isoformat())

        # Process through zone analytics
        zone_data = zone_analytics.process_detections(detections)

        # Add detections to heatmap
        heatmap.add_detections_batch(detections)

        # Update speed estimates
        for detection in detections:
            track_id = detection.get("track_id")
            centroid = detection.get("centroid", [0, 0])
            speed_estimator.update(track_id, centroid[0], centroid[1], datetime.now().timestamp())

        # Check for incidents
        zone_alerts = zone_analytics.get_zone_alerts()
        speed_violations = speed_estimator.detect_speeding(limit_kmh=50.0)

        # Log key metrics
        if frame_data.get("frame_count") % 30 == 0:  # Every second at 30fps
            logger.info(
                f"Frame {frame_data.get('frame_count')}: "
                f"{len(detections)} detections, "
                f"{len(zone_alerts)} zone alerts, "
                f"{len(speed_violations)} speeding violations"
            )

            # Log zone statistics
            for zone_id in zone_analytics.zones.keys():
                stats = zone_analytics.get_zone_stats(zone_id)
                logger.debug(
                    f"  Zone '{stats.get('zone_name')}': "
                    f"{stats.get('vehicle_count')} vehicles, "
                    f"entries: {stats.get('total_entries')}, "
                    f"exits: {stats.get('total_exits')}"
                )

        # Apply temporal decay to heatmap (emphasizes recent activity)
        if frame_data.get("frame_count") % 10 == 0:
            heatmap.decay(factor=0.98)

        return {
            "zone_data": zone_data,
            "zone_alerts": zone_alerts,
            "speed_violations": speed_violations,
        }

    async def on_frame_db_store(frame_data):
        """
        Store frame data to database (simulated).

        In a real system, this would write to the database.
        """
        # Placeholder for database storage
        pass

    # ============================================================================
    # RUN SIMULATION
    # ============================================================================

    logger.info(f"Starting simulation for session: {session_id}")
    logger.info(f"Frame size: {frame_width}x{frame_height}")
    logger.info(f"Duration: 60 seconds")

    try:
        # Run 60-second simulation at 10 fps
        await simulator.start(
            fps=10.0,
            duration_seconds=60.0,
            broadcast_callback=on_frame_generated,
            db_callback=on_frame_db_store,
        )
    except Exception as e:
        logger.error(f"Simulation error: {e}")

    # ============================================================================
    # FINAL STATISTICS AND REPORTS
    # ============================================================================

    logger.info("\n" + "=" * 80)
    logger.info("SIMULATION COMPLETE - SUMMARY REPORT")
    logger.info("=" * 80)

    # Simulator statistics
    sim_stats = simulator.get_statistics()
    logger.info("\nSIMULATOR STATISTICS:")
    logger.info(f"  Session: {sim_stats['session_id']}")
    logger.info(f"  Frames: {sim_stats['frame_count']}")
    logger.info(f"  Total Vehicles: {sim_stats['total_vehicles_processed']}")
    logger.info(f"  Incidents: {sim_stats['incident_count']}")

    # Zone statistics
    logger.info("\nZONE ANALYTICS:")
    for zone_id in zone_analytics.zones.keys():
        stats = zone_analytics.get_zone_stats(zone_id)
        logger.info(f"\n  Zone: {stats.get('zone_name')} ({stats.get('zone_type')})")
        logger.info(f"    Total Entries: {stats.get('total_entries')}")
        logger.info(f"    Total Exits: {stats.get('total_exits')}")
        logger.info(f"    Vehicle Types: {stats.get('vehicles_by_type')}")

    # Speed statistics
    logger.info("\nSPEED STATISTICS:")
    speed_stats = speed_estimator.get_statistics()
    logger.info(f"  Tracked Vehicles: {speed_stats.get('tracked_vehicles')}")
    logger.info(f"  Average Speed: {speed_stats.get('average_speed_kmh'):.1f} km/h")
    logger.info(f"  Max Speed: {speed_stats.get('max_speed_kmh'):.1f} km/h")
    logger.info(f"  Speed Distribution:")
    for bucket, count in speed_stats.get('distribution', {}).items():
        logger.info(f"    {bucket} km/h: {count} vehicles")

    # Heatmap statistics
    logger.info("\nHEATMAP STATISTICS:")
    heatmap_stats = heatmap.get_statistics()
    logger.info(f"  Grid Size: {heatmap.grid_width}x{heatmap.grid_height} cells")
    logger.info(f"  Max Density: {heatmap_stats['max']:.1f}")
    logger.info(f"  Mean Density: {heatmap_stats['mean']:.1f}")
    logger.info(f"  Total Accumulation: {heatmap_stats['total_accumulation']:.0f}")

    # Get high-density regions
    high_density = heatmap.get_high_density_regions(threshold_percentile=75)
    logger.info(f"  High Density Regions: {len(high_density)} cells")

    # Export heatmap visualization
    heatmap_base64 = heatmap.to_base64_png(apply_blur=True, alpha=0.4)
    logger.info(f"  Heatmap PNG exported (base64): {len(heatmap_base64)} characters")

    logger.info("\n" + "=" * 80)
    logger.info("Demo complete! All features demonstrated successfully.")
    logger.info("=" * 80)

    return {
        "simulator_stats": sim_stats,
        "zone_stats": {
            zone_id: zone_analytics.get_zone_stats(zone_id)
            for zone_id in zone_analytics.zones.keys()
        },
        "speed_stats": speed_stats,
        "heatmap_stats": heatmap_stats,
    }


async def demo_zone_analytics_only():
    """
    Demonstrate zone analytics features with manual detection input.

    Useful for testing zones without running full simulation.
    """
    logger.info("\nDEMO: Zone Analytics Only")
    logger.info("=" * 80)

    zone_analytics = ZoneAnalytics(1920, 1080)

    # Create a test zone
    test_zone = Zone(
        id="test_zone_1",
        name="Test Intersection",
        polygon=[(100, 100), (400, 100), (400, 300), (100, 300)],
        zone_type=ZoneType.COUNTING,
    )
    zone_analytics.add_zone(test_zone)

    # Simulate detections
    detections = [
        {
            "track_id": 1,
            "centroid": [150, 150],  # Inside zone
            "vehicle_type": "car",
            "confidence": 0.95,
        },
        {
            "track_id": 2,
            "centroid": [250, 200],  # Inside zone
            "vehicle_type": "truck",
            "confidence": 0.90,
        },
        {
            "track_id": 3,
            "centroid": [500, 500],  # Outside zone
            "vehicle_type": "car",
            "confidence": 0.92,
        },
    ]

    zone_data = zone_analytics.process_detections(detections)
    logger.info(f"Zone Analytics Results: {zone_data}")

    stats = zone_analytics.get_zone_stats("test_zone_1")
    logger.info(f"Zone Stats: {stats}")


async def demo_speed_estimation_only():
    """
    Demonstrate speed estimation with simulated track data.
    """
    logger.info("\nDEMO: Speed Estimation Only")
    logger.info("=" * 80)

    speed_estimator = SpeedEstimator(pixels_per_meter=10.0, fps=30.0)

    # Simulate a vehicle moving at constant velocity
    track_id = 100
    for frame in range(30):
        x = 100 + (frame * 5)  # Moving at 5 pixels per frame
        y = 200
        timestamp = frame / 30.0  # 30 fps

        speed_estimator.update(track_id, x, y, timestamp, frame_number=frame)

    current_speed = speed_estimator.get_speed(track_id)
    logger.info(f"Track {track_id} speed: {current_speed:.1f} km/h")

    # With pixels_per_meter=10, fps=30: 5px/frame * 30fps / 10px/m * 3.6 = 54 km/h
    expected_speed = (5 * 30 / 10) * 3.6  # ~54 km/h
    logger.info(f"Expected speed: {expected_speed:.1f} km/h")


async def main():
    """Run all demonstrations."""
    # Run complete system demo
    await demo_complete_system()

    # Run isolated feature demos
    await demo_zone_analytics_only()
    await demo_speed_estimation_only()


if __name__ == "__main__":
    asyncio.run(main())
