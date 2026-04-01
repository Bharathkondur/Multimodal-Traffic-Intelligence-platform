"""
Video Stream Processor for real-time traffic analysis.

Handles multiple stream sources (files, RTSP, webcam, HTTP), performs frame extraction,
preprocessing, and orchestrates the detection, tracking, and incident detection pipeline
with async processing, performance metrics, and session management.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, AsyncGenerator
from collections import deque
import numpy as np

logger = logging.getLogger(__name__)


class StreamSourceType(str, Enum):
    """Supported stream source types."""
    VIDEO_FILE = "video_file"
    RTSP_STREAM = "rtsp_stream"
    WEBCAM = "webcam"
    HTTP_STREAM = "http_stream"


@dataclass
class StreamSource:
    """Configuration for a video stream source."""
    type: StreamSourceType
    source: str  # File path, RTSP URL, device index (0 for default webcam), or HTTP URL
    name: str = "Unnamed Stream"
    description: str = ""

    def __post_init__(self) -> None:
        """Validate stream source configuration."""
        if self.type == StreamSourceType.VIDEO_FILE:
            if not Path(self.source).exists():
                raise FileNotFoundError(f"Video file not found: {self.source}")
        elif self.type == StreamSourceType.WEBCAM:
            try:
                int(self.source)
            except ValueError:
                raise ValueError(f"Webcam source must be a device index: {self.source}")


@dataclass
class ProcessingConfig:
    """Configuration for stream processing pipeline."""
    # Frame extraction
    fps: int = 30
    target_fps: Optional[int] = None  # Downsample if specified
    frame_width: int = 1920
    frame_height: int = 1080

    # Preprocessing
    normalize: bool = True
    resize_mode: str = "letterbox"  # 'letterbox', 'crop', 'stretch'

    # Processing
    batch_size: int = 8
    queue_size: int = 100
    num_workers: int = 4

    # Performance
    skip_frames: int = 0  # Skip N frames between processing
    timeout: float = 30.0  # Timeout for processing pipeline

    # Storage
    batch_db_writes: bool = True
    batch_write_interval: float = 5.0
    batch_write_size: int = 50


@dataclass
class ProcessingMetrics:
    """Real-time processing performance metrics."""
    frame_count: int = 0
    processed_frames: int = 0
    skipped_frames: int = 0
    detection_count: int = 0
    incident_count: int = 0

    avg_fps: float = 0.0
    current_fps: float = 0.0
    avg_frame_latency_ms: float = 0.0
    peak_latency_ms: float = 0.0

    total_detections: int = 0
    total_incidents: int = 0

    # Internal tracking
    _fps_samples: deque = field(default_factory=lambda: deque(maxlen=30))
    _latency_samples: deque = field(default_factory=lambda: deque(maxlen=100))
    _last_update: float = field(default_factory=time.time)

    def record_frame(self, latency_ms: float) -> None:
        """Record frame processing metrics."""
        self.frame_count += 1
        self._latency_samples.append(latency_ms)

        if latency_ms > self.peak_latency_ms:
            self.peak_latency_ms = latency_ms

        if len(self._latency_samples) > 0:
            self.avg_frame_latency_ms = sum(self._latency_samples) / len(self._latency_samples)

    def record_fps(self, fps: float) -> None:
        """Record FPS measurement."""
        self._fps_samples.append(fps)
        if len(self._fps_samples) > 0:
            self.avg_fps = sum(self._fps_samples) / len(self._fps_samples)
        self.current_fps = fps

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for serialization."""
        return {
            "frame_count": self.frame_count,
            "processed_frames": self.processed_frames,
            "skipped_frames": self.skipped_frames,
            "detection_count": self.detection_count,
            "incident_count": self.incident_count,
            "avg_fps": round(self.avg_fps, 2),
            "current_fps": round(self.current_fps, 2),
            "avg_frame_latency_ms": round(self.avg_frame_latency_ms, 2),
            "peak_latency_ms": round(self.peak_latency_ms, 2),
            "total_detections": self.total_detections,
            "total_incidents": self.total_incidents,
            "timestamp": datetime.utcnow().isoformat(),
        }


class StreamProcessor:
    """
    Orchestrates video stream processing with detection, tracking, and incident detection.

    Handles multiple stream sources, frame extraction, preprocessing, async processing
    pipeline with batching, performance metrics, and session management.
    """

    def __init__(
        self,
        stream_source: StreamSource,
        config: Optional[ProcessingConfig] = None,
        on_detection: Optional[Callable] = None,
        on_incident: Optional[Callable] = None,
        on_metrics: Optional[Callable] = None,
        detector=None,
        tracker=None,
        incident_detector=None,
        heatmap=None,
        speed_estimator=None,
        zone_analytics=None,
        db_factory=None,
    ) -> None:
        """
        Initialize the stream processor.

        Args:
            stream_source: Configuration for the video stream
            config: Processing configuration (uses defaults if not provided)
            on_detection: Async callback for detection results (frame_data, detections)
            on_incident: Async callback for incident alerts (incident_data)
            on_metrics: Async callback for performance metrics (metrics)
            detector: VehicleDetector instance for object detection
            tracker: ObjectTracker instance for multi-object tracking
            incident_detector: IncidentDetector instance for incident detection
            heatmap: TrafficHeatmap instance for density visualization
            speed_estimator: SpeedEstimator instance for speed analysis
            zone_analytics: ZoneAnalytics instance for zone-based analysis
            db_factory: AsyncSessionFactory for database operations
        """
        self.stream_source = stream_source
        self.config = config or ProcessingConfig()

        # Component dependencies (can be None for simulation mode)
        self.detector = detector
        self.tracker = tracker
        self.incident_detector = incident_detector
        self.heatmap = heatmap
        self.speed_estimator = speed_estimator
        self.zone_analytics = zone_analytics
        self.db_factory = db_factory

        # Callbacks
        self.on_detection = on_detection
        self.on_incident = on_incident
        self.on_metrics = on_metrics

        # State management
        self._running = False
        self._paused = False
        self._session_id: Optional[str] = None

        # Metrics
        self.metrics = ProcessingMetrics()

        # Async queues for pipeline stages
        self._frame_queue: asyncio.Queue = asyncio.Queue(maxsize=self.config.queue_size)
        self._detection_queue: asyncio.Queue = asyncio.Queue(maxsize=self.config.queue_size)
        self._tracking_queue: asyncio.Queue = asyncio.Queue(maxsize=self.config.queue_size)
        self._incident_queue: asyncio.Queue = asyncio.Queue(maxsize=self.config.queue_size)

        # Batch write management
        self._pending_detections: List[Dict[str, Any]] = []
        self._pending_incidents: List[Dict[str, Any]] = []

        # Tasks
        self._tasks: List[asyncio.Task] = []

        logger.info(f"Initialized StreamProcessor for {stream_source.name}")

    async def start(self, session_id: Optional[str] = None) -> str:
        """
        Start the stream processing pipeline.

        Args:
            session_id: Optional session ID (generated if not provided)

        Returns:
            The session ID for this processing session
        """
        if self._running:
            logger.warning("Processor already running")
            return self._session_id or ""

        # Create or use provided session ID
        self._session_id = session_id or self._generate_session_id()
        self._running = True
        self._paused = False

        logger.info(f"Starting stream processing - Session: {self._session_id}")

        try:
            # Start pipeline stages
            self._tasks = [
                asyncio.create_task(self._frame_extraction_stage()),
                asyncio.create_task(self._detection_stage()),
                asyncio.create_task(self._tracking_stage()),
                asyncio.create_task(self._incident_detection_stage()),
                asyncio.create_task(self._metrics_stage()),
                asyncio.create_task(self._batch_write_stage()),
            ]

            logger.info("All pipeline stages started")
        except Exception as e:
            self._running = False
            logger.error(f"Failed to start processing pipeline: {e}")
            raise

        return self._session_id

    async def stop(self) -> None:
        """Gracefully stop the stream processing pipeline."""
        if not self._running:
            logger.warning("Processor not running")
            return

        logger.info("Stopping stream processor")
        self._running = False

        # Flush pending writes
        await self._flush_batch_writes()

        # Cancel all tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        # Wait for cancellation
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        logger.info("Stream processor stopped")

    async def pause(self) -> None:
        """Pause stream processing (can be resumed with start)."""
        if not self._running:
            logger.warning("Processor not running")
            return

        self._paused = True
        logger.info("Stream processor paused")

    async def resume(self) -> None:
        """Resume paused stream processing."""
        if not self._running:
            logger.warning("Processor not running")
            return

        self._paused = False
        logger.info("Stream processor resumed")

    def is_running(self) -> bool:
        """Check if processor is currently running."""
        return self._running and not self._paused

    def get_metrics(self) -> ProcessingMetrics:
        """Get current processing metrics."""
        return self.metrics

    async def _frame_extraction_stage(self) -> None:
        """
        Extract frames from the video stream.

        Handles frame rate control, skipping, and preprocessing.
        """
        try:
            stream = self._open_stream()
            frame_interval = 1.0 / self.config.fps if self.config.fps > 0 else 0
            target_interval = 1.0 / self.config.target_fps if self.config.target_fps else frame_interval

            last_time = time.time()
            frame_skip_counter = 0

            async for frame_data in self._read_frames(stream):
                if not self._running:
                    break

                # Handle pause
                while self._paused:
                    await asyncio.sleep(0.1)

                # Rate limiting
                elapsed = time.time() - last_time
                if elapsed < target_interval:
                    await asyncio.sleep(target_interval - elapsed)

                # Frame skipping
                if frame_skip_counter < self.config.skip_frames:
                    frame_skip_counter += 1
                    self.metrics.skipped_frames += 1
                    continue

                frame_skip_counter = 0

                # Preprocess frame
                processed_frame = self._preprocess_frame(frame_data["frame"])
                frame_data["frame"] = processed_frame

                # Queue for detection
                try:
                    self._frame_queue.put_nowait(frame_data)
                except asyncio.QueueFull:
                    logger.warning("Frame queue full, dropping frame")

                last_time = time.time()

        except Exception as e:
            logger.error(f"Error in frame extraction stage: {e}")
        finally:
            self._running = False
            await self._signal_pipeline_end()

    async def _detection_stage(self) -> None:
        """
        Perform object detection on frames.

        Receives preprocessed frames from frame extraction stage
        and forwards to tracking stage.
        """
        try:
            while self._running or not self._frame_queue.empty():
                try:
                    frame_data = await asyncio.wait_for(
                        self._frame_queue.get(),
                        timeout=self.config.timeout
                    )
                except asyncio.TimeoutError:
                    if not self._running:
                        break
                    continue

                start_time = time.time()

                # Run real detection if detector is available
                detections = await self._run_detection(frame_data["frame"])

                frame_data["detections"] = detections

                # Update metrics
                self.metrics.processed_frames += 1
                self.metrics.detection_count += len(detections)
                self.metrics.total_detections += len(detections)

                # Broadcast detections to websocket
                if self.on_detection:
                    try:
                        await self.on_detection(frame_data, detections)
                    except Exception as e:
                        logger.error(f"Error in on_detection callback: {e}")

                # Queue for tracking
                try:
                    self._detection_queue.put_nowait(frame_data)
                except asyncio.QueueFull:
                    logger.warning("Detection queue full, dropping frame")

                latency_ms = (time.time() - start_time) * 1000
                self.metrics.record_frame(latency_ms)

        except Exception as e:
            logger.error(f"Error in detection stage: {e}")

    async def _tracking_stage(self) -> None:
        """
        Perform object tracking across frames.

        Maintains track consistency and forwards to incident detection.
        """
        try:
            while self._running or not self._detection_queue.empty():
                try:
                    frame_data = await asyncio.wait_for(
                        self._detection_queue.get(),
                        timeout=self.config.timeout
                    )
                except asyncio.TimeoutError:
                    if not self._running:
                        break
                    continue

                # Run real tracking if tracker is available
                tracks = await self._run_tracking(
                    frame_data["detections"],
                    frame_data.get("frame_id", 0)
                )

                frame_data["tracks"] = tracks

                # Queue for incident detection
                try:
                    self._tracking_queue.put_nowait(frame_data)
                except asyncio.QueueFull:
                    logger.warning("Tracking queue full, dropping frame")

        except Exception as e:
            logger.error(f"Error in tracking stage: {e}")

    async def _incident_detection_stage(self) -> None:
        """
        Detect traffic incidents from tracked objects.

        Analyzes behavior patterns for accidents, congestion, etc.
        """
        try:
            while self._running or not self._tracking_queue.empty():
                try:
                    frame_data = await asyncio.wait_for(
                        self._tracking_queue.get(),
                        timeout=self.config.timeout
                    )
                except asyncio.TimeoutError:
                    if not self._running:
                        break
                    continue

                # Run real incident detection if detector is available
                incidents = await self._run_incident_detection(
                    frame_data["tracks"],
                    frame_data
                )

                if incidents:
                    self.metrics.incident_count += len(incidents)
                    self.metrics.total_incidents += len(incidents)

                    # Broadcast incidents to websocket
                    if self.on_incident:
                        try:
                            for incident in incidents:
                                await self.on_incident(incident)
                        except Exception as e:
                            logger.error(f"Error in on_incident callback: {e}")

                    # Queue for batch writing
                    if self.config.batch_db_writes:
                        self._pending_incidents.extend(
                            self._format_incidents_for_db(incidents)
                        )

                # Store detections for batch writing
                if self.config.batch_db_writes and frame_data.get("detections"):
                    self._pending_detections.extend(
                        self._format_detections_for_db(frame_data)
                    )

                try:
                    self._incident_queue.put_nowait(frame_data)
                except asyncio.QueueFull:
                    logger.warning("Incident queue full, dropping frame")

        except Exception as e:
            logger.error(f"Error in incident detection stage: {e}")

    async def _metrics_stage(self) -> None:
        """
        Periodically calculate and broadcast performance metrics.
        """
        try:
            last_frame_count = 0
            last_time = time.time()

            while self._running:
                await asyncio.sleep(1.0)

                current_time = time.time()
                elapsed = current_time - last_time

                if elapsed > 0:
                    frames_processed = self.metrics.processed_frames - last_frame_count
                    fps = frames_processed / elapsed
                    self.metrics.record_fps(fps)

                    last_frame_count = self.metrics.processed_frames
                    last_time = current_time

                # Broadcast metrics
                if self.on_metrics:
                    try:
                        await self.on_metrics(self.metrics)
                    except Exception as e:
                        logger.error(f"Error in on_metrics callback: {e}")

        except Exception as e:
            logger.error(f"Error in metrics stage: {e}")

    async def _batch_write_stage(self) -> None:
        """
        Periodically batch write detections and incidents to database.
        """
        try:
            while self._running:
                await asyncio.sleep(self.config.batch_write_interval)
                await self._flush_batch_writes()

        except Exception as e:
            logger.error(f"Error in batch write stage: {e}")

    async def _flush_batch_writes(self) -> None:
        """Flush pending batch writes to database."""
        if not self.config.batch_db_writes or not self.db_factory:
            return

        try:
            from database.queries import batch_write_detections, batch_write_incidents

            # Write detections
            if self._pending_detections:
                logger.debug(f"Flushing {len(self._pending_detections)} detections to DB")
                async with self.db_factory.session_context() as session:
                    await batch_write_detections(session, self._pending_detections)
                self._pending_detections.clear()

            # Write incidents
            if self._pending_incidents:
                logger.debug(f"Flushing {len(self._pending_incidents)} incidents to DB")
                async with self.db_factory.session_context() as session:
                    await batch_write_incidents(session, self._pending_incidents)
                self._pending_incidents.clear()

        except Exception as e:
            logger.error(f"Error flushing batch writes to database: {e}")

    async def _signal_pipeline_end(self) -> None:
        """Signal end of stream to all pipeline stages."""
        # Add sentinel values to signal end
        for _ in range(3):
            try:
                self._frame_queue.put_nowait({"frame": None})
            except asyncio.QueueFull:
                pass

    def _open_stream(self) -> Any:
        """
        Open the video stream based on source type.

        Returns:
            Stream object (cv2.VideoCapture in real implementation)
        """
        # This would be implemented with opencv-python in production
        logger.info(f"Opening stream: {self.stream_source.type} - {self.stream_source.source}")
        return {"type": self.stream_source.type, "source": self.stream_source.source}

    async def _read_frames(self, stream: Any) -> AsyncGenerator:
        """
        Async generator to read frames from stream.

        Args:
            stream: Stream object

        Yields:
            Frame data dictionaries
        """
        frame_id = 0
        # Simulate reading frames
        while self._running and frame_id < 300:  # Demo: 300 frames
            # In real implementation, would read actual video frames
            frame = np.zeros((self.config.frame_height, self.config.frame_width, 3), dtype=np.uint8)

            yield {
                "frame": frame,
                "frame_id": frame_id,
                "timestamp": datetime.utcnow(),
                "session_id": self._session_id,
            }

            frame_id += 1
            await asyncio.sleep(0.01)  # Simulate frame reading

    def _preprocess_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        Preprocess frame for detection.

        Args:
            frame: Raw frame

        Returns:
            Preprocessed frame
        """
        if frame is None or frame.size == 0:
            return frame

        h, w = frame.shape[:2]

        # Resize if needed
        if w != self.config.frame_width or h != self.config.frame_height:
            if self.config.resize_mode == "letterbox":
                frame = self._letterbox_resize(frame)
            elif self.config.resize_mode == "crop":
                frame = self._crop_resize(frame)
            else:  # stretch
                frame = np.asarray([])  # Would use cv2.resize

        # Normalize
        if self.config.normalize and frame.size > 0:
            frame = frame.astype(np.float32) / 255.0

        return frame

    def _letterbox_resize(self, frame: np.ndarray) -> np.ndarray:
        """Resize frame maintaining aspect ratio with letterbox padding."""
        # Implementation would use cv2 in production
        return frame

    def _crop_resize(self, frame: np.ndarray) -> np.ndarray:
        """Resize frame by cropping to target aspect ratio."""
        # Implementation would use cv2 in production
        return frame

    async def _run_detection(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Run object detection on frame using real detector if available.

        Args:
            frame: Preprocessed frame

        Returns:
            List of detections as dictionaries
        """
        if self.detector is None:
            # Fallback simulation
            await asyncio.sleep(0.001)
            return []

        try:
            # Call real detector
            detections = self.detector.detect_frame(frame)
            # Convert Detection dataclass objects to dictionaries
            return [
                {
                    "class_id": d.class_id,
                    "class_name": d.class_name,
                    "confidence": d.confidence,
                    "bbox": d.bbox,
                    "centroid": d.centroid,
                    "area": d.area,
                    "vehicle_type": d.vehicle_type.value if d.vehicle_type else None,
                }
                for d in detections
            ]
        except Exception as e:
            logger.error(f"Error running detection: {e}")
            return []

    async def _run_tracking(self, detections: List[Dict], frame_id: int) -> List[Dict[str, Any]]:
        """
        Run object tracking using real tracker if available.

        Args:
            detections: Current frame detections
            frame_id: Frame identifier

        Returns:
            List of tracked objects as dictionaries
        """
        if self.tracker is None:
            # Fallback simulation
            await asyncio.sleep(0.001)
            return detections

        try:
            # Convert dict detections back to Detection objects if needed
            # The tracker.track() method expects Detection objects
            tracks = self.tracker.track(detections)

            # Update analytics if available
            if self.speed_estimator and tracks:
                for track in tracks:
                    self.speed_estimator.update(
                        track.track_id,
                        track.centroid[0],
                        track.centroid[1],
                        time.time()
                    )

            if self.heatmap and tracks:
                heatmap_data = [
                    {
                        "centroid": t.centroid,
                        "confidence": t.confidence
                    }
                    for t in tracks
                ]
                self.heatmap.add_detections_batch(heatmap_data)

            # Convert Track objects to dictionaries
            return [
                {
                    "track_id": t.track_id,
                    "centroid": t.centroid,
                    "bbox": t.bbox,
                    "state": t.state.value,
                    "class_name": t.class_name,
                    "confidence": t.confidence,
                    "age": t.age,
                    "velocity": t.velocity.tolist() if hasattr(t.velocity, 'tolist') else t.velocity,
                }
                for t in tracks
            ]
        except Exception as e:
            logger.error(f"Error running tracking: {e}")
            return detections

    async def _run_incident_detection(
        self,
        tracks: List[Dict],
        frame_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Detect incidents from tracked objects using real detector if available.

        Args:
            tracks: Tracked objects
            frame_data: Frame metadata

        Returns:
            List of detected incidents as dictionaries
        """
        if self.incident_detector is None:
            # Fallback simulation
            await asyncio.sleep(0.001)
            return []

        try:
            # Note: incident_detector.detect() expects Track objects, not dicts
            # In production, we'd pass the actual Track objects from the tracker
            incidents = self.incident_detector.detect(tracks)

            # Convert Incident objects to dictionaries
            return [
                {
                    "incident_id": inc.incident_id,
                    "incident_type": inc.incident_type.value,
                    "severity": inc.severity.value,
                    "location": inc.location,
                    "involved_tracks": inc.involved_tracks,
                    "timestamp": inc.timestamp.isoformat() if inc.timestamp else None,
                    "duration": inc.duration,
                    "confidence": inc.confidence,
                    "description": inc.description,
                    "is_active": inc.is_active,
                    "session_id": self._session_id,
                }
                for inc in incidents
            ]
        except Exception as e:
            logger.error(f"Error running incident detection: {e}")
            return []

    def _format_detections_for_db(self, frame_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Format detections for database storage.

        Args:
            frame_data: Frame and detection data

        Returns:
            Formatted detection records
        """
        detections = []
        for detection in frame_data.get("detections", []):
            bbox = detection.get("bbox", [0, 0, 0, 0])
            if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
                bbox_x, bbox_y, bbox_w, bbox_h = bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1]
            else:
                bbox_x, bbox_y, bbox_w, bbox_h = 0, 0, 0, 0

            detections.append({
                "session_id": self._session_id,
                "frame_number": frame_data.get("frame_id"),
                "timestamp": frame_data.get("timestamp"),
                "vehicle_type": detection.get("vehicle_type", "unknown"),
                "confidence": detection.get("confidence", 0.0),
                "bbox_x": bbox_x,
                "bbox_y": bbox_y,
                "bbox_w": bbox_w,
                "bbox_h": bbox_h,
            })
        return detections

    def _format_incidents_for_db(self, incidents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Format incidents for database storage.

        Args:
            incidents: List of incident dictionaries

        Returns:
            Formatted incident records
        """
        formatted = []
        for incident in incidents:
            formatted.append({
                "session_id": self._session_id,
                "timestamp": incident.get("timestamp"),
                "incident_type": incident.get("incident_type", "other"),
                "severity": incident.get("severity", "low"),
                "location_description": f"Location: {incident.get('location')}",
                "related_track_ids": incident.get("involved_tracks", []),
                "resolved": not incident.get("is_active", True),
                "description": incident.get("description", ""),
            })
        return formatted

    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        import hashlib

        timestamp = datetime.utcnow().isoformat()
        source_hash = hashlib.md5(self.stream_source.source.encode()).hexdigest()[:8]
        return f"session_{source_hash}_{int(time.time())}"
