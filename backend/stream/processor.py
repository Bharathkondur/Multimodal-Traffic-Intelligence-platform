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
        ocr_reader=None,
        pose_estimator=None,
        pose_classifier=None,
        pose_frame_interval: int = 3,
        captioner=None,
        monitor=None,
        on_caption: Optional[Callable] = None,
        on_alert: Optional[Callable] = None,
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
        self.ocr_reader = ocr_reader
        self._ocr_frame_counter = 0  # only run OCR every N frames for performance

        # Scene Intelligence additions ------------------------------------
        self.pose_estimator = pose_estimator
        self.pose_classifier = pose_classifier
        self.pose_frame_interval = max(1, int(pose_frame_interval))
        self._pose_frame_counter = 0
        self._last_poses: List[Dict[str, Any]] = []  # cached between pose frames
        self.captioner = captioner
        self.monitor = monitor
        self._last_caption_ts = 0.0
        self._last_frame: Optional[np.ndarray] = None  # for captioner/snapshots

        # Callbacks
        self.on_detection = on_detection
        self.on_incident = on_incident
        self.on_metrics = on_metrics
        self.on_caption = on_caption
        self.on_alert = on_alert

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
                self._last_frame = frame_data.get("frame")

                # Pose estimation — every N frames, only if we have people.
                poses = await self._maybe_run_pose(
                    frame_data.get("frame"),
                    detections,
                )
                frame_data["poses"] = poses

                # Fire-and-forget: live captioning + rule evaluation.
                # Both are gated by their own configs and cooldowns.
                if self.captioner is not None:
                    asyncio.create_task(
                        self._maybe_caption(frame_data, detections, poses)
                    )
                if self.monitor is not None and (detections or poses):
                    asyncio.create_task(
                        self._run_monitor(frame_data, detections, poses)
                    )

                # Update metrics
                self.metrics.processed_frames += 1
                self.metrics.detection_count += len(detections)
                self.metrics.total_detections += len(detections)

                if detections:
                    logger.info(
                        f"Frame {frame_data.get('frame_id')}: "
                        f"{len(detections)} detections → broadcasting"
                    )

                # Encode frame as JPEG for live video streaming
                frame_b64 = None
                raw_frame = frame_data.get("frame")
                if raw_frame is not None and raw_frame.size > 0:
                    try:
                        import cv2
                        import base64 as _base64
                        orig_h, orig_w = raw_frame.shape[:2]
                        stream_w, stream_h = 1280, 720
                        stream_frame = cv2.resize(raw_frame, (stream_w, stream_h))
                        _, buf = cv2.imencode('.jpg', stream_frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
                        frame_b64 = _base64.b64encode(buf).decode('utf-8')

                        # Scale bboxes from original frame coords → 1280×720 stream coords
                        sx = stream_w / orig_w if orig_w else 1.0
                        sy = stream_h / orig_h if orig_h else 1.0
                        for det in detections:
                            if det.get("bbox") and len(det["bbox"]) == 4:
                                x1, y1, x2, y2 = det["bbox"]
                                det["bbox"] = [x1 * sx, y1 * sy, x2 * sx, y2 * sy]
                    except Exception as e:
                        logger.warning(f"Frame encoding failed: {e}")

                # Broadcast detections to websocket
                if self.on_detection:
                    try:
                        await self.on_detection(frame_data, detections, frame_b64)
                    except Exception as e:
                        logger.error(f"Error in on_detection callback: {e}")
                # Attach poses to the downstream queue payload so the
                # tracking/incident stages can see action labels.
                frame_data["poses"] = poses

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

    # ------------------------------------------------------------------
    # Scene Intelligence: pose / captioning / rule monitor
    # ------------------------------------------------------------------
    async def _maybe_run_pose(
        self,
        frame: Optional[np.ndarray],
        detections: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Run YOLO-pose every N frames. Returns pose dicts or cached ones."""
        if self.pose_estimator is None or frame is None:
            return []

        # Skip if no people in the frame — pose is a pure cost otherwise.
        has_person = any(
            (d.get("class_name") or d.get("type") or "").lower() == "person"
            for d in detections
        )
        if not has_person:
            self._last_poses = []
            return []

        self._pose_frame_counter += 1
        if self._pose_frame_counter % self.pose_frame_interval != 0:
            return self._last_poses

        try:
            loop = asyncio.get_event_loop()
            poses = await loop.run_in_executor(
                None, self.pose_estimator.estimate, frame
            )
            # Match pose to track_id by bbox IoU (best-effort).
            person_dets = [
                d for d in detections
                if (d.get("class_name") or d.get("type") or "").lower() == "person"
            ]
            for p in poses:
                tid = self._match_track_id(p.bbox, person_dets)
                if self.pose_classifier is not None:
                    self.pose_classifier.update_and_classify(p, tid)
                else:
                    p.track_id = tid
            pose_dicts = [p.to_dict() for p in poses]
            self._last_poses = pose_dicts

            # Tag action back onto the matching detection dict so the
            # frontend overlay can render it next to the class label.
            for pose in pose_dicts:
                tid = pose.get("track_id")
                action = pose.get("action")
                if not action or action == "unknown":
                    continue
                for det in detections:
                    if det.get("track_id") == tid:
                        det["action"] = action
                        det["action_confidence"] = pose.get("action_confidence")
                        break
            return pose_dicts
        except Exception as e:
            logger.debug(f"Pose stage error: {e}")
            return self._last_poses

    @staticmethod
    def _match_track_id(
        pose_bbox: tuple,
        person_dets: List[Dict[str, Any]],
    ) -> Optional[int]:
        """Pick the person-detection with highest IoU to this pose bbox."""
        best_iou = 0.0
        best_tid: Optional[int] = None
        px1, py1, px2, py2 = pose_bbox
        p_area = max(0.0, (px2 - px1) * (py2 - py1))
        if p_area <= 0:
            return None
        for det in person_dets:
            bbox = det.get("bbox")
            if not bbox or len(bbox) != 4:
                continue
            dx1, dy1, dx2, dy2 = bbox
            ix1 = max(px1, dx1)
            iy1 = max(py1, dy1)
            ix2 = min(px2, dx2)
            iy2 = min(py2, dy2)
            if ix2 <= ix1 or iy2 <= iy1:
                continue
            inter = (ix2 - ix1) * (iy2 - iy1)
            d_area = (dx2 - dx1) * (dy2 - dy1)
            union = p_area + d_area - inter
            iou = inter / union if union > 0 else 0.0
            if iou > best_iou:
                best_iou = iou
                best_tid = det.get("track_id")
        return best_tid if best_iou > 0.3 else None

    async def _maybe_caption(
        self,
        frame_data: Dict[str, Any],
        detections: List[Dict[str, Any]],
        poses: List[Dict[str, Any]],
    ) -> None:
        """Invoke the VLM captioner every caption_interval_s at most."""
        if self.captioner is None or self.on_caption is None:
            return
        now = time.time()
        interval = getattr(self.captioner, "interval_s", 3.0)
        if (now - self._last_caption_ts) < interval:
            return
        self._last_caption_ts = now

        frame = frame_data.get("frame")
        if frame is None:
            return
        try:
            caption = await self.captioner.caption(frame, detections, poses)
            if caption:
                payload = {
                    "caption": caption.get("text"),
                    "summary": caption.get("summary"),
                    "tags": caption.get("tags", []),
                    "timestamp": (
                        frame_data.get("timestamp").isoformat()
                        if frame_data.get("timestamp") else None
                    ),
                    "frame_id": frame_data.get("frame_id"),
                    "session_id": self._session_id,
                }
                await self.on_caption(payload)
        except Exception as e:
            logger.debug(f"Captioner error: {e}")

    async def _run_monitor(
        self,
        frame_data: Dict[str, Any],
        detections: List[Dict[str, Any]],
        poses: List[Dict[str, Any]],
    ) -> None:
        """Evaluate active rules against this frame and emit alerts."""
        if self.monitor is None or self.on_alert is None:
            return
        try:
            alerts = await self.monitor.evaluate(
                session_id=self._session_id,
                detections=detections,
                poses=poses,
                frame=frame_data.get("frame"),
                timestamp=frame_data.get("timestamp"),
                frame_id=frame_data.get("frame_id"),
            )
            for alert in alerts or []:
                try:
                    await self.on_alert(alert)
                except Exception as e:
                    logger.debug(f"on_alert error: {e}")
        except Exception as e:
            logger.debug(f"Monitor error: {e}")

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
        Open the video stream based on source type using OpenCV.

        Returns:
            cv2.VideoCapture object
        """
        import cv2 as cv
        logger.info(f"Opening stream: {self.stream_source.type} - {self.stream_source.source}")
        cap = cv.VideoCapture(self.stream_source.source)
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video: {self.stream_source.source}")
        logger.info(
            f"Video opened: {int(cap.get(cv.CAP_PROP_FRAME_COUNT))} frames, "
            f"{cap.get(cv.CAP_PROP_FPS):.1f} fps"
        )
        return cap

    async def _read_frames(self, stream: Any) -> AsyncGenerator:
        """
        Async generator to read frames from an OpenCV VideoCapture.

        Yields:
            Frame data dictionaries with actual video frames
        """
        import cv2 as cv
        cap = stream
        frame_id = 0
        loop = asyncio.get_event_loop()

        try:
            while self._running:
                # Read frame in executor so it doesn't block the event loop
                ret, frame = await loop.run_in_executor(None, cap.read)
                if not ret or frame is None:
                    logger.info(f"End of video stream after {frame_id} frames")
                    break

                yield {
                    "frame": frame,
                    "frame_id": frame_id,
                    "timestamp": datetime.utcnow(),
                    "session_id": self._session_id,
                }

                frame_id += 1
                # Yield control briefly so other coroutines can run
                await asyncio.sleep(0)
        finally:
            cap.release()

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
            # Run synchronous YOLO inference in a thread so we don't block the event loop.
            loop = asyncio.get_event_loop()
            detections = await loop.run_in_executor(None, self.detector.detect_frame, frame)
            # Convert Detection dataclass objects to dictionaries
            result_dets = [
                {
                    "class_id": d.class_id,
                    "class_name": d.class_name,
                    # "type" is what the frontend overlay expects for colour-coding
                    "type": d.vehicle_type.value if d.vehicle_type else d.class_name,
                    "confidence": d.confidence,
                    "bbox": list(d.bbox),
                    "centroid": d.centroid,
                    "area": d.area,
                    "vehicle_type": d.vehicle_type.value if d.vehicle_type else None,
                }
                for d in detections
            ]

            # License plate recognition via fast-alpr — run every 3 frames for performance
            self._ocr_frame_counter += 1
            if self.ocr_reader and result_dets and self._ocr_frame_counter % 3 == 0:
                try:
                    from models.ocr import run_alpr
                    plates = await loop.run_in_executor(
                        None, run_alpr, frame, self.ocr_reader
                    )
                    # Match each detected plate to the vehicle bbox that contains it
                    for plate in plates:
                        px1, py1, px2, py2 = plate["bbox"]
                        px_c = (px1 + px2) / 2
                        py_c = (py1 + py2) / 2
                        for det in result_dets:
                            dx1, dy1, dx2, dy2 = det["bbox"]
                            if dx1 <= px_c <= dx2 and dy1 <= py_c <= dy2:
                                det["plate_number"] = plate["text"]
                                det["plate_confidence"] = plate["confidence"]
                                break
                except Exception as e:
                    logger.debug(f"ALPR error: {e}")

            return result_dets
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
