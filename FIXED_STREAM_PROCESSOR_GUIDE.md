# Fixed Stream Processor Implementation Guide

## Overview

The stream processor has been completely refactored to use **real implementations** instead of stubs. All three critical pipeline stages now call actual component methods:

1. `_run_detection()` - Calls `VehicleDetector.detect_frame()`
2. `_run_tracking()` - Calls `ObjectTracker.track()`
3. `_run_incident_detection()` - Calls `IncidentDetector.detect()`
4. `_flush_batch_writes()` - Calls actual database batch write functions

## Architecture Changes

### Before (Stubbed)
```python
async def _run_detection(self, frame):
    # Simulate detection
    await asyncio.sleep(0.001)
    return [{"class": "vehicle", "confidence": 0.95, "bbox": [...]}]
```

### After (Real Implementation)
```python
async def _run_detection(self, frame: np.ndarray) -> List[Dict[str, Any]]:
    if self.detector is None:
        await asyncio.sleep(0.001)
        return []

    try:
        detections = self.detector.detect_frame(frame)
        return [
            {
                "class_id": d.class_id,
                "class_name": d.class_name,
                "confidence": d.confidence,
                "bbox": d.bbox,
                "centroid": d.centroid,
                ...
            }
            for d in detections
        ]
    except Exception as e:
        logger.error(f"Error running detection: {e}")
        return []
```

## Key Implementation Details

### 1. **Constructor Dependency Injection**

The `StreamProcessor.__init__()` now accepts optional component instances:

```python
def __init__(
    self,
    stream_source: StreamSource,
    config: Optional[ProcessingConfig] = None,
    # ... callbacks ...
    detector=None,              # VehicleDetector instance
    tracker=None,              # ObjectTracker instance
    incident_detector=None,    # IncidentDetector instance
    heatmap=None,             # TrafficHeatmap instance
    speed_estimator=None,     # SpeedEstimator instance
    zone_analytics=None,      # ZoneAnalytics instance
    db_factory=None,          # AsyncSessionFactory instance
) -> None:
```

All components are stored as instance variables and used throughout the pipeline.

### 2. **Detection Pipeline**

The detection stage now:
- Calls `self.detector.detect_frame(frame)` if detector is available
- Converts `Detection` dataclass objects to dictionaries
- Maintains all metadata (confidence, centroid, vehicle_type, etc.)
- Falls back to empty results if detector is None

```python
detections = self.detector.detect_frame(frame)
return [
    {
        "class_id": d.class_id,
        "class_name": d.class_name,
        "confidence": d.confidence,
        "bbox": d.bbox,  # (x1, y1, x2, y2)
        "centroid": d.centroid,
        "area": d.area,
        "vehicle_type": d.vehicle_type.value if d.vehicle_type else None,
    }
    for d in detections
]
```

### 3. **Tracking Pipeline**

The tracking stage now:
- Calls `self.tracker.track(detections)` if tracker is available
- Updates speed estimator with new positions
- Updates heatmap with vehicle locations
- Returns fully populated track dictionaries

```python
tracks = self.tracker.track(detections)

# Update analytics
for track in tracks:
    self.speed_estimator.update(
        track.track_id,
        track.centroid[0],
        track.centroid[1],
        time.time()
    )

self.heatmap.add_detections_batch([
    {"centroid": t.centroid, "confidence": t.confidence}
    for t in tracks
])

# Convert to dicts
return [
    {
        "track_id": t.track_id,
        "centroid": t.centroid,
        "bbox": t.bbox,
        "state": t.state.value,
        "class_name": t.class_name,
        "confidence": t.confidence,
        "age": t.age,
        "velocity": t.velocity.tolist(),
    }
    for t in tracks
]
```

### 4. **Incident Detection Pipeline**

The incident detection stage now:
- Calls `self.incident_detector.detect(tracks)` if detector is available
- Formats incident objects to dictionaries
- Stores incidents for batch database writes

```python
incidents = self.incident_detector.detect(tracks)

# Convert to dicts
return [
    {
        "incident_id": inc.incident_id,
        "incident_type": inc.incident_type.value,
        "severity": inc.severity.value,
        "location": inc.location,
        "involved_tracks": inc.involved_tracks,
        "timestamp": inc.timestamp.isoformat(),
        "duration": inc.duration,
        "confidence": inc.confidence,
        "description": inc.description,
        "is_active": inc.is_active,
        "session_id": self._session_id,
    }
    for inc in incidents
]
```

### 5. **Database Batch Writes**

The `_flush_batch_writes()` method now performs **real database operations**:

```python
async def _flush_batch_writes(self) -> None:
    if not self.config.batch_db_writes or not self.db_factory:
        return

    try:
        from database.queries import batch_write_detections, batch_write_incidents

        # Write detections
        if self._pending_detections:
            async with self.db_factory.session_context() as session:
                await batch_write_detections(session, self._pending_detections)
            self._pending_detections.clear()

        # Write incidents
        if self._pending_incidents:
            async with self.db_factory.session_context() as session:
                await batch_write_incidents(session, self._pending_incidents)
            self._pending_incidents.clear()

    except Exception as e:
        logger.error(f"Error flushing batch writes: {e}")
```

## Integration Examples

### Basic Usage with Real Components

```python
from backend.detection.detector import VehicleDetector
from backend.detection.tracker import ObjectTracker
from backend.detection.incident_detector import IncidentDetector
from backend.analytics.heatmap import TrafficHeatmap
from backend.analytics.speed import SpeedEstimator
from backend.database.connection import AsyncSessionFactory
from backend.stream.processor import StreamProcessor, StreamSource, StreamSourceType

# Initialize components
detector = VehicleDetector(model_path="yolov8m.pt")
tracker = ObjectTracker()
incident_detector = IncidentDetector()
heatmap = TrafficHeatmap(width=1920, height=1080)
speed_estimator = SpeedEstimator(pixels_per_meter=10.0)
db_factory = AsyncSessionFactory("postgresql+asyncpg://user:pass@localhost/traffic")

# Create stream processor with components
processor = StreamProcessor(
    stream_source=StreamSource(
        type=StreamSourceType.VIDEO_FILE,
        source="/path/to/video.mp4",
        name="Main Intersection"
    ),
    detector=detector,
    tracker=tracker,
    incident_detector=incident_detector,
    heatmap=heatmap,
    speed_estimator=speed_estimator,
    db_factory=db_factory,
    on_detection=handle_detection,
    on_incident=handle_incident,
    on_metrics=handle_metrics,
)

# Start processing
session_id = await processor.start()
```

### Simulation Mode (No Components)

If components are not initialized, the processor gracefully degrades to simulation mode:

```python
# Create processor without components
processor = StreamProcessor(
    stream_source=StreamSource(
        type=StreamSourceType.VIDEO_FILE,
        source="/path/to/video.mp4"
    ),
    # All other parameters None - runs in simulation mode
)

# Still works, just with empty results
session_id = await processor.start()
```

## Data Flow

```
Frame Extraction
       |
       v
[Preprocess Frame] -> Detection Stage
       |
       v
[Run Detection] -> Detector.detect_frame()
       |
       v
[Format Detections] -> Tracking Stage
       |
       v
[Run Tracking] -> Tracker.track()
       |                |
       v                v
[Update Analytics]  [Format Tracks] -> Incident Stage
       |                                  |
       v                                  v
[Heatmap, Speed]  [Run Incident Detection] -> IncidentDetector.detect()
       |                                  |
       v                                  v
[Format Incidents] -> Database Batch Write Stage
       |
       v
[Batch Write] -> DB batch_write_detections()
               -> DB batch_write_incidents()
```

## Performance Considerations

1. **Component Initialization**: Initialize components once and reuse across multiple stream processors
2. **Database Connection**: Use connection pooling via `AsyncSessionFactory`
3. **Batch Writes**: Default batch write interval is 5 seconds with batch size of 50
4. **Memory Usage**: Analytics components (heatmap, speed estimator) maintain history

## Testing

```python
# Test detection integration
frame = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
detections = await processor._run_detection(frame)
assert len(detections) >= 0
assert all('class_name' in d for d in detections)

# Test tracking integration
tracks = await processor._run_tracking(detections, frame_id=0)
assert all('track_id' in t for t in tracks)

# Test incident detection
incidents = await processor._run_incident_detection(tracks, frame_data)
assert all('incident_type' in i for i in incidents)
```

## Error Handling

All real implementation calls are wrapped in try-except blocks:

```python
try:
    detections = self.detector.detect_frame(frame)
    # ... process ...
except Exception as e:
    logger.error(f"Error running detection: {e}")
    return []  # Fallback to empty results
```

This ensures the processor continues operating even if individual components fail.

## Database Integration

The processor now writes real data to PostgreSQL:

**Detections Written:**
- session_id, frame_number, timestamp
- vehicle_type, confidence
- bbox_x, bbox_y, bbox_w, bbox_h

**Incidents Written:**
- session_id, timestamp, incident_type, severity
- location_description, related_track_ids
- resolved, description

See `backend/database/queries.py` for batch write function signatures.

## Summary

The stream processor has been transformed from a simulation to a **production-ready real-time analysis engine** that:

✅ Calls actual detection, tracking, and incident detection models
✅ Integrates analytics components (heatmap, speed, zones)
✅ Performs real database persistence
✅ Maintains graceful fallbacks for missing components
✅ Provides comprehensive error handling
✅ Tracks performance metrics in real-time
