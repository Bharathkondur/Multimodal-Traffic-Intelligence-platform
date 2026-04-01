# Quick Start: New Traffic Intelligence Features

This guide shows how to quickly get started with the four new features for demo/portfolio purposes.

## 1. Running the Demo Simulator

The simplest way to showcase the platform is to use the simulator—no real video needed.

```python
import asyncio
from backend.processing.simulator import TrafficSimulator

async def main():
    # Create simulator
    simulator = TrafficSimulator(session_id="demo_1", frame_width=1920, frame_height=1080)

    # Define callbacks for data
    async def on_frame(frame_data):
        print(f"Frame {frame_data['frame_count']}: "
              f"{len(frame_data['detections'])} vehicles detected")

    # Run for 5 minutes
    await simulator.start(
        fps=10.0,
        duration_seconds=300.0,
        broadcast_callback=on_frame
    )

    # Get stats
    stats = simulator.get_statistics()
    print(f"Simulation complete: {stats['total_vehicles_processed']} total vehicles")

asyncio.run(main())
```

## 2. Creating Custom Zones

Add zone tracking to monitor specific areas.

```python
from backend.analytics import Zone, ZoneAnalytics, ZoneType

# Initialize zone analytics
zones = ZoneAnalytics(frame_width=1920, frame_height=1080)

# Create a zone (polygon-based)
my_zone = Zone(
    id="zone_1",
    name="Main Intersection",
    polygon=[
        (100, 100),
        (800, 100),
        (800, 600),
        (100, 600),
    ],
    zone_type=ZoneType.COUNTING,
    threshold_vehicles=15,  # Alert if > 15 vehicles
)
zones.add_zone(my_zone)

# Process detections (from simulator or real pipeline)
zone_results = zones.process_detections(detections)

# Get zone stats
stats = zones.get_zone_stats("zone_1")
print(f"Vehicles in zone: {stats['vehicle_count']}")
print(f"Entries: {stats['total_entries']}")
print(f"Exits: {stats['total_exits']}")

# Check for alerts
alerts = zones.get_zone_alerts()
for alert in alerts:
    print(f"ZONE ALERT: {alert['alert_type']} in {alert['zone_name']}")
```

## 3. Generating Heatmaps

Visualize traffic density as a heatmap.

```python
from backend.analytics import TrafficHeatmap

# Create heatmap
heatmap = TrafficHeatmap(width=1920, height=1080, cell_size=20)

# Add detection data
heatmap.add_detections_batch(detections)

# Get statistics
stats = heatmap.get_statistics()
print(f"Peak density: {stats['max']:.1f}")

# Apply decay for recent-activity emphasis
heatmap.decay(factor=0.98)

# Export as base64 PNG (for web display)
png_base64 = heatmap.to_base64_png(apply_blur=True, alpha=0.4)

# Save visualization to file
heatmap.save_to_file("traffic_heatmap.png")

# Find hotspots
hotspots = heatmap.get_high_density_regions(threshold_percentile=75)
print(f"Hotspot cells: {len(hotspots)}")
```

## 4. Estimating Speeds

Track and analyze vehicle speeds.

```python
from backend.analytics import SpeedEstimator

# Initialize
speed_est = SpeedEstimator(pixels_per_meter=10.0, fps=30.0)

# Update with each frame's detections
for detection in detections:
    track_id = detection['track_id']
    x, y = detection['centroid']

    speed_est.update(
        track_id=track_id,
        x=x,
        y=y,
        timestamp=datetime.now().timestamp(),
        frame_number=frame_num
    )

# Get current speed of a vehicle
speed = speed_est.get_speed(track_id=100)
print(f"Vehicle 100: {speed:.1f} km/h")

# Find speeding violations
violations = speed_est.detect_speeding(limit_kmh=50.0)
for v in violations:
    print(f"SPEEDING: Track {v['track_id']} at {v['speed_kmh']:.1f} km/h "
          f"(limit: {v['speed_limit_kmh']} km/h)")

# Speed distribution
dist = speed_est.get_speed_distribution()
print(f"Speed distribution: {dist}")
# Output: {'0-20': 5, '20-40': 12, '40-60': 8, '60-80': 2, '80-100': 0, '100+': 0}

# Get overall statistics
stats = speed_est.get_statistics()
print(f"Average speed: {stats['average_speed_kmh']:.1f} km/h")
print(f"Max speed: {stats['max_speed_kmh']:.1f} km/h")
print(f"Vehicles tracked: {stats['tracked_vehicles']}")
```

## 5. Complete Integration (All Features Together)

See `backend/integration_example.py` for a complete working example.

Run it:
```bash
cd backend
python integration_example.py
```

This demonstrates:
- Simulator generating realistic traffic
- Zones tracking vehicles in custom areas
- Heatmap showing traffic density
- Speed estimator monitoring velocities

## Typical Workflow for Portfolio Demo

```
1. Start the simulator
   ↓
2. Define custom zones for monitoring
   ↓
3. Generate heatmap visualization
   ↓
4. Calculate speed statistics
   ↓
5. Display alerts and statistics on dashboard
   ↓
6. Export results and visualizations
```

## WebSocket Integration Example

To broadcast simulation data to dashboard via WebSocket:

```python
async def broadcast_callback(frame_data):
    """Called for each frame during simulation."""
    # Send to all connected WebSocket clients
    await broadcast_to_clients({
        "type": "detection_frame",
        "data": {
            "detections": frame_data['detections'],
            "zones": zone_analytics.process_detections(frame_data['detections']),
            "heatmap": heatmap.to_base64_png(),
            "speeds": speed_est.get_statistics(),
        }
    })

# In your FastAPI app:
async def start_demo():
    simulator = TrafficSimulator("demo_session")
    await simulator.start(
        fps=10.0,
        duration_seconds=300.0,
        broadcast_callback=broadcast_callback,
    )
```

## Key Configuration Parameters

### Simulator
- `fps`: Frame rate (10-30 fps typical)
- `duration_seconds`: How long to run
- `pixels_per_meter`: For realistic scaling

### Zones
- `threshold_vehicles`: Alert if count exceeds
- `threshold_speed`: Alert if speed exceeds (km/h)
- `direction`: Filter by traffic direction

### Heatmap
- `cell_size`: Smaller = more detail, slower. Default 20px
- `blur_kernel`: Smoothness (21 or 31 typical)
- `alpha`: Transparency (0.3-0.5 typical)

### Speed Estimator
- `pixels_per_meter`: Camera calibration (vary based on camera angle)
- `fps`: Match your video frame rate

## Troubleshooting

### Zones not detecting vehicles
- Check polygon coordinates match frame resolution
- Verify detection centroid calculation is correct
- Debug with: `zones.point_in_zone(x, y, zone_id)`

### Heatmap looks empty
- Check if detections have `centroid` field
- Verify frame dimensions match initialization
- Try reducing `cell_size` for more sensitive grid

### Speeds seem wrong
- Check `pixels_per_meter` calibration
- Verify FPS parameter matches your video
- Calibrate with known distance: `speed_est.calibrate(pixels, meters)`

### Performance issues
- Reduce number of zones
- Increase heatmap `cell_size`
- Lower simulator `fps`
- Limit detection count

## Next Steps

1. **Integrate with dashboard**: Connect WebSocket to send frame data
2. **Add database storage**: Save detections, incidents, and statistics
3. **Create alerts**: Trigger notifications on violations
4. **Build analytics**: Aggregate statistics over time
5. **Deploy**: Run in production pipeline

See `FEATURES.md` for detailed API documentation.
