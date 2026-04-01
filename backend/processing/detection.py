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

        # Import models
        from models.detection import load_model

        # Import database
        from database.connection import AsyncSessionFactory

        # Load YOLOv8 model
        logger.debug(f"Loading YOLOv8 model from {settings.model_path}")
        model = load_model(settings.model_path, device="auto")
        logger.info("YOLOv8 model loaded successfully")

        # Create stream source for video file
        stream_source = StreamSource(
            type=StreamSourceType.VIDEO_FILE,
            source=video_path,
            name=f"Session {session_id}",
            description=f"Video file processing for session {session_id}",
        )

        # Create processing configuration
        processing_config = ProcessingConfig(
            fps=30,
            target_fps=10,  # Process every 3 frames
            frame_width=1920,
            frame_height=1080,
            normalize=True,
            resize_mode="letterbox",
            batch_size=8,
            queue_size=100,
            num_workers=4,
            skip_frames=0,
            timeout=30.0,
            batch_db_writes=True,
            batch_write_interval=5.0,
            batch_write_size=50,
        )

        # Create stream processor
        processor = StreamProcessor(
            source=stream_source,
            config=processing_config,
            session_id=session_id,
        )

        # Initialize database session factory
        db_factory = AsyncSessionFactory(
            database_url=settings.get_database_url(),
            echo=False,
            pool_size=5,
        )

        # Initialize database
        await db_factory.init_models()

        # Process video frames
        logger.info("Starting frame processing")
        await processor.process(model=model)

        logger.info(f"Detection pipeline completed for session {session_id}")

        # Update session status to completed
        try:
            async with db_factory.get_session() as db_session:
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
                await db_session.commit()
                logger.info(f"Session {session_id} status updated to COMPLETED")
        except Exception as e:
            logger.error(f"Failed to update session status: {e}")

        # Close database connections
        await db_factory.close()

    except Exception as e:
        logger.error(f"Detection pipeline error for session {session_id}: {e}", exc_info=True)

        # Try to update session status to failed
        try:
            if settings and AsyncSession:
                from database.connection import AsyncSessionFactory
                from database.models import TrafficSession, SessionStatus
                from sqlalchemy import update

                db_factory = AsyncSessionFactory(database_url=settings.get_database_url())
                await db_factory.init_models()

                async with db_factory.get_session() as db_session:
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
