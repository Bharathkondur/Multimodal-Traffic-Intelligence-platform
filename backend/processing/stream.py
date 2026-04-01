"""
Stream pipeline for real-time RTSP and HTTP stream processing.

Handles live stream processing with automatic reconnection, frame extraction,
object detection, and incident alerts.
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def start_stream_pipeline(
    session_id: str,
    stream_url: str,
    settings: Optional[object] = None,
    stream_type: str = "rtsp",
) -> None:
    """
    Start the stream processing pipeline for RTSP or HTTP stream.

    Processes a live stream in real-time, handling reconnection attempts,
    frame extraction, object detection, and incident alerts.

    Args:
        session_id: Unique identifier for the traffic session
        stream_url: URL of the stream (RTSP or HTTP)
        settings: Application settings object (optional, uses global config if None)
        stream_type: Type of stream ("rtsp" or "http")

    Processing Pipeline:
        1. Loads YOLOv8 detection model
        2. Creates StreamProcessor for RTSP/HTTP source
        3. Connects to stream with auto-reconnection
        4. Extracts frames from stream
        5. Runs object detection on each frame
        6. Saves detections to database
        7. Handles stream disconnections and reconnects

    Returns:
        None (runs as background task)

    Features:
        - Automatic reconnection on stream failure
        - Real-time frame processing
        - Incident detection and alerting
        - Performance metrics tracking
        - Graceful error handling

    Raises:
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

    max_reconnect_attempts = 5
    reconnect_delay = 5  # seconds
    attempt = 0

    while attempt < max_reconnect_attempts:
        try:
            logger.info(
                f"Starting stream pipeline for session {session_id} "
                f"with stream {stream_url} (attempt {attempt + 1}/{max_reconnect_attempts})"
            )

            # Import stream processor
            from stream.processor import StreamProcessor, StreamSource, StreamSourceType, ProcessingConfig

            # Import models
            from models.detection import load_model

            # Import database
            from database.connection import AsyncSessionFactory

            # Determine stream source type
            if stream_type.lower() == "rtsp":
                source_type = StreamSourceType.RTSP_STREAM
            elif stream_type.lower() == "http":
                source_type = StreamSourceType.HTTP_STREAM
            else:
                logger.error(f"Unknown stream type: {stream_type}")
                return

            # Load YOLOv8 model
            logger.debug(f"Loading YOLOv8 model from {settings.model_path}")
            model = load_model(settings.model_path, device="auto")
            logger.info("YOLOv8 model loaded successfully")

            # Create stream source
            stream_source = StreamSource(
                type=source_type,
                source=stream_url,
                name=f"Session {session_id}",
                description=f"Stream processing for session {session_id}",
            )

            # Create processing configuration for streams
            processing_config = ProcessingConfig(
                fps=30,
                target_fps=15,  # Process at 15 FPS for real-time streams
                frame_width=1920,
                frame_height=1080,
                normalize=True,
                resize_mode="letterbox",
                batch_size=4,
                queue_size=50,
                num_workers=2,
                skip_frames=0,
                timeout=30.0,
                batch_db_writes=True,
                batch_write_interval=3.0,  # More frequent writes for live data
                batch_write_size=20,
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

            # Process stream with timeout
            logger.info("Starting stream processing")
            try:
                # Run stream processing with a timeout
                await asyncio.wait_for(
                    processor.process_stream(model=model),
                    timeout=settings.stream_timeout_seconds,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"Stream processing timeout for session {session_id}, "
                    "attempting reconnection"
                )
            finally:
                await db_factory.close()

            # Successful completion
            logger.info(f"Stream pipeline completed for session {session_id}")

            # Update session status to completed
            try:
                db_factory = AsyncSessionFactory(database_url=settings.get_database_url())
                await db_factory.init_models()

                async with db_factory.get_session() as db_session:
                    from database.models import TrafficSession, SessionStatus
                    from sqlalchemy import update

                    stmt = (
                        update(TrafficSession)
                        .where(TrafficSession.id == session_id)
                        .values(status=SessionStatus.COMPLETED)
                    )
                    await db_session.execute(stmt)
                    await db_session.commit()
                    logger.info(f"Session {session_id} status updated to COMPLETED")

                await db_factory.close()
            except Exception as e:
                logger.error(f"Failed to update session status: {e}")

            break  # Exit retry loop on success

        except Exception as e:
            attempt += 1
            logger.error(
                f"Stream pipeline error for session {session_id} "
                f"(attempt {attempt}/{max_reconnect_attempts}): {e}",
                exc_info=True,
            )

            if attempt < max_reconnect_attempts:
                logger.info(
                    f"Waiting {reconnect_delay}s before reconnection attempt..."
                )
                await asyncio.sleep(reconnect_delay)
            else:
                logger.error(
                    f"Max reconnection attempts ({max_reconnect_attempts}) "
                    f"reached for session {session_id}"
                )

                # Update session status to failed
                try:
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
                    logger.error(
                        f"Failed to update session status to FAILED: {update_error}"
                    )
