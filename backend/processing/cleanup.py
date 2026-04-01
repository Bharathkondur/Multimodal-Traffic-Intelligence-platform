"""
Session cleanup task for traffic sessions.

Handles stopping stream processors, cleaning up temporary files,
and updating session status in the database.
"""

import asyncio
import logging
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# Global store of active stream processors
_active_processors = {}


async def cleanup_session(
    session_id: str,
    db_session: Optional[object] = None,
) -> None:
    """
    Clean up resources for a traffic session.

    Stops any running stream processor, updates session status in database,
    removes temporary files, and logs cleanup actions.

    Args:
        session_id: Unique identifier for the traffic session
        db_session: SQLAlchemy AsyncSession (optional, creates new if None)

    Returns:
        None

    Cleanup Tasks:
        1. Stops any active StreamProcessor for the session
        2. Updates session status to "completed" in database
        3. Removes uploaded video files
        4. Removes temporary processing files
        5. Logs all cleanup actions

    Raises:
        Exception: Logs errors without raising (graceful degradation)

    Note:
        This function is designed to be called after session processing completes
        or when a session needs to be terminated.
    """
    try:
        logger.info(f"Starting cleanup for session {session_id}")

        # Step 1: Stop any active stream processor
        logger.debug(f"Checking for active processors for session {session_id}")
        if session_id in _active_processors:
            processor = _active_processors[session_id]
            try:
                logger.info(f"Stopping stream processor for session {session_id}")
                if hasattr(processor, "stop"):
                    await processor.stop()
                elif hasattr(processor, "close"):
                    await processor.close()
                logger.info(f"Stream processor stopped for session {session_id}")
            except Exception as e:
                logger.error(f"Error stopping processor: {e}")
            finally:
                del _active_processors[session_id]
        else:
            logger.debug(f"No active processor found for session {session_id}")

        # Step 2: Update session status in database
        logger.debug(f"Updating session status for {session_id}")
        try:
            from database.connection import AsyncSessionFactory
            from database.models import TrafficSession, SessionStatus
            from sqlalchemy import update

            # Create database session if not provided
            if db_session is None:
                from config import settings

                db_factory = AsyncSessionFactory(database_url=settings.get_database_url())
                await db_factory.init_models()
                db_session = db_factory.get_session()
                session_owner = db_factory
            else:
                session_owner = None

            try:
                # Update session status to completed
                stmt = (
                    update(TrafficSession)
                    .where(TrafficSession.id == session_id)
                    .values(status=SessionStatus.COMPLETED)
                )
                await db_session.execute(stmt)
                await db_session.commit()
                logger.info(f"Session {session_id} status updated to COMPLETED")
            finally:
                if session_owner is not None:
                    await session_owner.close()

        except Exception as e:
            logger.error(f"Failed to update session status: {e}")

        # Step 3: Clean up temporary files
        logger.debug(f"Cleaning up temporary files for session {session_id}")
        try:
            from config import settings

            # Define upload directory path
            session_upload_dir = Path(settings.upload_dir) / session_id

            if session_upload_dir.exists():
                logger.info(f"Removing session directory: {session_upload_dir}")
                shutil.rmtree(session_upload_dir)
                logger.info(f"Session directory removed successfully")
            else:
                logger.debug(f"Session directory not found: {session_upload_dir}")

            # Clean up any temporary processing files
            temp_dirs = [
                Path("/tmp") / f"traffic_{session_id}",
                Path("/tmp") / f"detections_{session_id}",
            ]

            for temp_dir in temp_dirs:
                if temp_dir.exists():
                    logger.info(f"Removing temporary directory: {temp_dir}")
                    shutil.rmtree(temp_dir)
                    logger.info(f"Temporary directory removed: {temp_dir}")

        except Exception as e:
            logger.error(f"Error cleaning up temporary files: {e}")

        logger.info(f"Session {session_id} cleanup completed successfully")

    except Exception as e:
        logger.error(f"Cleanup error for session {session_id}: {e}", exc_info=True)


async def register_processor(session_id: str, processor: object) -> None:
    """
    Register an active stream processor for a session.

    Args:
        session_id: Session identifier
        processor: StreamProcessor instance
    """
    _active_processors[session_id] = processor
    logger.debug(f"Registered processor for session {session_id}")


async def unregister_processor(session_id: str) -> None:
    """
    Unregister a stream processor for a session.

    Args:
        session_id: Session identifier
    """
    if session_id in _active_processors:
        del _active_processors[session_id]
        logger.debug(f"Unregistered processor for session {session_id}")


def get_active_sessions() -> list[str]:
    """
    Get list of sessions with active processors.

    Returns:
        List of session IDs with active processors
    """
    return list(_active_processors.keys())
