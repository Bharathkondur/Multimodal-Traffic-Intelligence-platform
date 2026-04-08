"""
Detection pipeline for video file processing.

Handles loading YOLOv8 models, processing video frames, detecting objects,
and persisting results to the database.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

try:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
except ImportError:
    AsyncSession = None

logger = logging.getLogger(__name__)


async def start_detection_pipeline(
    session_id: str,
    video_path: str,
    settings: Optional[object] = None,
) -> None:
    """
    Start the detection pipeline for a video file.

    Processes a video file frame-by-frame using YOLOv8 model, detects objects,
    and saves detection results to the database.

    Args:
        session_id: Unique identifier for the traffic session
        video_path: Path to the video file to process
        settings: Application settings object (optional, uses global config if None)

    Processing Pipeline:
        1. Loads YOLOv8 detection model
        2. Creates StreamProcessor for video file
        3. Extracts frames from video
        4. Runs object detection on each frame
        5. Saves detections to database
        6. Updates session status upon completion

    Returns:
        None (runs as background task)

    Raises:
        FileNotFoundError: If video file doesn't exist
        Exception: Logs errors without raising (graceful degradation)

    Note:
        This function is designed to run as a background asyncio task
        and handles all errors internally with logging.
    """
    if settings is None:
        try:
            from config import settings as global_settings
            settings = global_settings
        except ImportError:
            logger.warning("Settings not provided and cannot import global settings")
            return

    try:
        # Validate video file exists
        if not Path(video_path).exists():
            logger.error(f"Video file not found: {video_path}")
            return

        logger.info(
            f"Starting detection pipeline for session {session_id} with video {video_path}"
        )

        # Import stream processor
        from stream.processor import StreamProcessor, StreamSource, StreamSourceType, ProcessingConfig
        from detection.detector import VehicleDetector

        # Import models
        from models.detection import load_model

        # Import database
        from database.connection import AsyncSessionFactory
        from api.websocket_routes import broadcast_detection, broadcast_incident, broadcast_metrics

        # Load YOLOv8 model
        logger.debug(f"Loading YOLOv8 model from {settings.model_path}")
        model = load_model(settings.model_path, device="auto")
        logger.info("YOLOv8 model loaded successfully")

        # Create detector wrapping YOLO model
        detector = VehicleDetector(model_path=settings.model_path)

        # Create stream source for video file
        stream_source = StreamSource(
            type=StreamSourceType.VIDEO_FILE,
            source=video_path,
            name=f"Session {session_id}",
            description=f"Video file processing for session {session_id}",
        )

        # Create processing configuration
        # normalize=False: YOLO expects uint8 BGR; normalising to float32 here is redundant
        # and can cause issues when YOLO's internal check skips its own /255 step.
        processing_config = ProcessingConfig(
            fps=30,
            target_fps=10,
            frame_width=1920,
            frame_height=1080,
            normalize=False,
            batch_size=8,
            queue_size=100,
        )

        # Initialize database session factory
        db_factory = AsyncSessionFactory(
            database_url=settings.get_database_url(),
            echo=False,
            pool_size=5,
        )

        # Broadcast callbacks
        async def on_detection(frame_data, detections, frame_b64=None):
            payload = {
                "detections": detections,
                "frame_id": frame_data.get("frame_id"),
                "timestamp": frame_data.get("timestamp").isoformat()
                    if frame_data.get("timestamp") else None,
                "session_id": session_id,
            }
            if frame_b64:
                payload["frame_data"] = frame_b64
            await broadcast_detection(session_id, payload)

        async def on_incident(incident):
            await broadcast_incident(session_id, incident)

        async def on_metrics(metrics):
            await broadcast_metrics(session_id, metrics)

        # Determine compute device for GPU acceleration
        import torch
        use_gpu = torch.cuda.is_available()
        device_str = "cuda" if use_gpu else "cpu"
        logger.info(f"Compute device: {device_str}")

        # Load fast-ALPR for license plate recognition (GPU-accelerated when available)
        ocr_reader = None
        try:
            from models.ocr import get_alpr_reader
            ocr_reader = get_alpr_reader(device=device_str)
            logger.info(f"fast-ALPR loaded on {device_str}")
        except Exception as e:
            logger.warning(f"fast-ALPR not available (plates skipped): {e}")

        # Give the WebSocket client time to connect before we start broadcasting frames.
        # Without this delay, early frames are broadcast to no one when the browser
        # navigates to the dashboard right after upload.
        logger.info("Waiting 2 s for WebSocket clients to connect...")
        await asyncio.sleep(2.0)

        # Create stream processor
        processor = StreamProcessor(
            stream_source=stream_source,
            config=processing_config,
            detector=detector,
            db_factory=db_factory,
            on_detection=on_detection,
            on_incident=on_incident,
            on_metrics=on_metrics,
            ocr_reader=ocr_reader,
        )

        # Process video frames
        logger.info("Starting frame processing")
        await processor.start(session_id=session_id)
        # Wait for all pipeline tasks to complete
        if processor._tasks:
            await asyncio.gather(*processor._tasks, return_exceptions=True)

        logger.info(f"Detection pipeline completed for session {session_id}")

        # Update session status to completed
        try:
            async with db_factory.session_context() as db_session:
                from database.models import TrafficSession, SessionStatus
                from sqlalchemy import update

                stmt = (
                    update(TrafficSession)
                    .where(TrafficSession.id == session_id)
                    .values(
                        status=SessionStatus.COMPLETED,
                    )
                )
                await db_session.execute(stmt)
                logger.info(f"Session {session_id} status updated to COMPLETED")
        except Exception as e:
            logger.error(f"Failed to update session status: {e}")

        # Close database connections
        await db_factory.dispose()

    except Exception as e:
        logger.error(f"Detection pipeline error for session {session_id}: {e}", exc_info=True)

        # Try to update session status to failed
        try:
            if settings and AsyncSession:
                from database.connection import AsyncSessionFactory
                from database.models import TrafficSession, SessionStatus
                from sqlalchemy import update

                db_factory = AsyncSessionFactory(database_url=settings.get_database_url())

                async with db_factory.session_context() as db_session:
                    stmt = (
                        update(TrafficSession)
                        .where(TrafficSession.id == session_id)
                        .values(status=SessionStatus.FAILED)
                    )
                    await db_session.execute(stmt)
                    await db_session.commit()

                await db_factory.close()
        except Exception as update_error:
            logger.error(f"Failed to update session status to FAILED: {update_error}")
