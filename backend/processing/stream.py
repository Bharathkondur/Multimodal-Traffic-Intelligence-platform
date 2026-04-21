"""
Stream pipeline for real-time RTSP, HTTP, and YouTube/video-URL processing.

Handles live-stream processing with URL resolution (yt-dlp for YouTube/web
videos), automatic reconnection, frame extraction, object detection,
license-plate OCR, tracking, incident detection, and WebSocket broadcast.

This module mirrors the wiring pattern used by ``processing.detection`` for
uploaded files, so both file and stream sessions produce identical WebSocket
output for the frontend.
"""

import asyncio
import logging
import re
from typing import Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# URL classification + resolution
# --------------------------------------------------------------------------- #

_YT_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtu.be",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}


def _classify_stream_url(url: str) -> str:
    """Return a coarse stream-type label used to configure OpenCV.

    One of: ``"rtsp"``, ``"youtube"``, ``"http"``, ``"webcam"``.
    """
    if url == "webcam" or (isinstance(url, str) and url.isdigit()):
        return "webcam"
    if url.lower().startswith("rtsp://"):
        return "rtsp"
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        host = ""
    if host.lower() in _YT_HOSTS:
        return "youtube"
    return "http"


def _resolve_youtube_url(url: str) -> str:
    """Resolve a YouTube/video-site URL to a direct media URL OpenCV can open.

    Uses yt-dlp to extract the best progressive stream (prefers 720p mp4 to
    balance fidelity and latency). Returns the direct media URL.

    Raises ``RuntimeError`` on failure so the caller can surface the error
    and mark the session FAILED.
    """
    try:
        import yt_dlp  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "yt-dlp is not installed; cannot resolve YouTube URLs."
        ) from e

    ydl_opts = {
        # Prefer a single progressive file (mp4) at ~720p to keep OpenCV happy.
        # Fall back to any playable format if nothing matches.
        "format": (
            "best[protocol^=http][vcodec!=none][acodec!=none][height<=720]/"
            "best[protocol^=http][vcodec!=none][height<=720]/"
            "best"
        ),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "socket_timeout": 15,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:  # yt_dlp raises a variety of types
        raise RuntimeError(f"yt-dlp failed to resolve {url!r}: {e}") from e

    direct_url: Optional[str] = info.get("url") if info else None
    if not direct_url and info and info.get("entries"):
        # Playlist fallback: take first entry
        first = info["entries"][0]
        direct_url = first.get("url")
    if not direct_url:
        raise RuntimeError(
            f"yt-dlp returned no playable URL for {url!r}"
        )

    logger.info(
        "Resolved %s → %s (%s)",
        url,
        re.sub(r"\?.*$", "?<params>", direct_url),
        info.get("format_id", "unknown-format") if info else "unknown",
    )
    return direct_url


def _resolve_stream_url(url: str) -> Tuple[str, str]:
    """Return ``(resolved_url, stream_type)`` for the given user-supplied URL.

    ``stream_type`` is the coarse label from :func:`_classify_stream_url` and
    reflects the *original* URL, not the resolved one — this is what the
    StreamProcessor uses to decide on buffering / reconnect behaviour.
    """
    stream_type = _classify_stream_url(url)
    if stream_type == "youtube":
        resolved = _resolve_youtube_url(url)
        return resolved, "http"  # yt-dlp returns an http(s) URL
    return url, stream_type


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #

async def start_stream_pipeline(
    session_id: str,
    stream_url: str,
    fps: int = 15,
    settings: Optional[object] = None,
) -> None:
    """Start the live-stream processing pipeline for RTSP / HTTP / YouTube.

    Args:
        session_id: Unique identifier for the traffic session (also used as
            the WebSocket channel key).
        stream_url: RTSP, HTTP, or YouTube URL submitted by the client. The
            pipeline will auto-detect the type and resolve YouTube URLs via
            yt-dlp.
        fps: Target processing frame rate. The pipeline will down-sample the
            source to this rate to keep detection latency low.
        settings: Optional override for the global settings object (mainly for
            tests).

    Runs as a long-lived background task. All errors are caught, logged, and
    propagated to the database session status; nothing is re-raised.
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

    # Resolve the URL once up-front — resolution failures should fail fast
    # rather than consume all reconnect attempts.
    try:
        resolved_url, stream_type = _resolve_stream_url(stream_url)
    except Exception as e:
        logger.error(
            "Failed to resolve stream URL for session %s: %s",
            session_id,
            e,
            exc_info=True,
        )
        await _mark_session_failed(session_id, settings, reason=str(e))
        return

    logger.info(
        "Session %s: stream_url=%s, stream_type=%s, resolved=%s",
        session_id,
        stream_url,
        stream_type,
        "<same>" if resolved_url == stream_url else "<yt-dlp>",
    )

    while attempt < max_reconnect_attempts:
        try:
            logger.info(
                "Starting stream pipeline for session %s "
                "(attempt %d/%d)",
                session_id,
                attempt + 1,
                max_reconnect_attempts,
            )

            # Lazy imports so we don't pay the cost if this task is never spawned.
            from stream.processor import (
                StreamProcessor,
                StreamSource,
                StreamSourceType,
                ProcessingConfig,
            )
            from detection.detector import VehicleDetector
            from models.detection import load_model
            from database.connection import AsyncSessionFactory
            from api.websocket_routes import (
                broadcast_detection,
                broadcast_incident,
                broadcast_metrics,
                broadcast_status,
            )

            # Map coarse stream_type → StreamSourceType enum.
            if stream_type == "rtsp":
                source_type = StreamSourceType.RTSP_STREAM
            elif stream_type == "http":
                source_type = StreamSourceType.HTTP_STREAM
            elif stream_type == "webcam":
                source_type = StreamSourceType.WEBCAM
            else:
                logger.error("Unknown stream type: %s", stream_type)
                await _mark_session_failed(
                    session_id, settings, reason=f"Unknown stream type: {stream_type}"
                )
                return

            # Load YOLO weights + build detector wrapper.
            logger.debug("Loading YOLOv8 model from %s", settings.model_path)
            load_model(settings.model_path, device="auto")
            detector = VehicleDetector(model_path=settings.model_path)

            # Best-effort ALPR.
            ocr_reader = None
            try:
                import torch
                device_str = "cuda" if torch.cuda.is_available() else "cpu"
                from models.ocr import get_alpr_reader
                ocr_reader = get_alpr_reader(device=device_str)
                logger.info("fast-ALPR loaded on %s", device_str)
            except Exception as e:
                logger.warning("fast-ALPR not available for stream (plates skipped): %s", e)

            # Wire broadcasts so the frontend sees the same payloads as for file uploads.
            async def on_detection(frame_data, detections, frame_b64=None):
                payload = {
                    "detections": detections,
                    "frame_id": frame_data.get("frame_id"),
                    "timestamp": (
                        frame_data.get("timestamp").isoformat()
                        if frame_data.get("timestamp")
                        else None
                    ),
                    "session_id": session_id,
                }
                if frame_b64:
                    payload["frame_data"] = frame_b64
                await broadcast_detection(session_id, payload)

            async def on_incident(incident):
                await broadcast_incident(session_id, incident)

            async def on_metrics(metrics):
                await broadcast_metrics(session_id, metrics)

            # Configure the source; for webcam we need the device index as a string.
            source_value = resolved_url if stream_type != "webcam" else "0"
            stream_source = StreamSource(
                type=source_type,
                source=source_value,
                name=f"Session {session_id}",
                description=f"Stream processing for session {session_id}",
            )

            # Live streams: process at a lower target FPS, write DB more often.
            # normalize=False: YOLO handles its own scaling; normalising here
            # hands the detector float32 in [0,1] which breaks inference.
            processing_config = ProcessingConfig(
                fps=30,
                target_fps=max(1, min(int(fps or 15), 30)),
                frame_width=1920,
                frame_height=1080,
                normalize=False,
                resize_mode="letterbox",
                batch_size=4,
                queue_size=50,
                num_workers=2,
                skip_frames=0,
                timeout=30.0,
                batch_db_writes=True,
                batch_write_interval=3.0,
                batch_write_size=20,
            )

            db_factory = AsyncSessionFactory(
                database_url=settings.get_database_url(),
                echo=False,
                pool_size=5,
            )

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

            # Let the WebSocket client attach before the first frame lands.
            await asyncio.sleep(2.0)

            # Let the frontend know the stream is about to start.
            try:
                await broadcast_status(
                    session_id,
                    {
                        "status": "stream_starting",
                        "stream_type": stream_type,
                        "url_preview": _safe_url_preview(stream_url),
                    },
                )
            except Exception:
                pass

            logger.info("Starting stream processing for session %s", session_id)

            # Fire the pipeline and wait for it to drain.
            await processor.start(session_id=session_id)
            if processor._tasks:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*processor._tasks, return_exceptions=True),
                        timeout=getattr(settings, "stream_timeout_seconds", None),
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "Stream processing timeout for session %s; attempting reconnection",
                        session_id,
                    )
                    await processor.stop()

            logger.info("Stream pipeline iteration ended for session %s", session_id)
            await _mark_session_completed(session_id, settings)
            return

        except Exception as e:
            attempt += 1
            logger.error(
                "Stream pipeline error for session %s (attempt %d/%d): %s",
                session_id,
                attempt,
                max_reconnect_attempts,
                e,
                exc_info=True,
            )

            # Notify the frontend so it can show a reconnect banner.
            try:
                from api.websocket_routes import broadcast_status
                await broadcast_status(
                    session_id,
                    {
                        "status": "stream_error",
                        "attempt": attempt,
                        "max_attempts": max_reconnect_attempts,
                        "error": str(e)[:200],
                    },
                )
            except Exception:
                pass

            if attempt < max_reconnect_attempts:
                logger.info("Waiting %ds before reconnection attempt…", reconnect_delay)
                await asyncio.sleep(reconnect_delay)
            else:
                logger.error(
                    "Max reconnection attempts (%d) reached for session %s",
                    max_reconnect_attempts,
                    session_id,
                )
                await _mark_session_failed(session_id, settings, reason=str(e))


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _safe_url_preview(url: str) -> str:
    """Strip query strings / credentials for safe display in WS messages."""
    try:
        parsed = urlparse(url)
        netloc = parsed.hostname or ""
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        path = parsed.path or ""
        scheme = parsed.scheme or ""
        return f"{scheme}://{netloc}{path}" if scheme else url
    except Exception:
        return url


async def _mark_session_completed(session_id: str, settings) -> None:
    """Mark the session row COMPLETED. Errors are logged only."""
    try:
        from database.connection import AsyncSessionFactory
        from database.models import TrafficSession, SessionStatus
        from sqlalchemy import update

        db_factory = AsyncSessionFactory(database_url=settings.get_database_url())
        async with db_factory.session_context() as db_session:
            await db_session.execute(
                update(TrafficSession)
                .where(TrafficSession.id == session_id)
                .values(status=SessionStatus.COMPLETED)
            )
        await db_factory.dispose()
    except Exception as e:
        logger.error("Failed to mark session %s COMPLETED: %s", session_id, e)


async def _mark_session_failed(session_id: str, settings, reason: str = "") -> None:
    """Mark the session row FAILED and notify any WS clients."""
    try:
        from database.connection import AsyncSessionFactory
        from database.models import TrafficSession, SessionStatus
        from sqlalchemy import update

        db_factory = AsyncSessionFactory(database_url=settings.get_database_url())
        async with db_factory.session_context() as db_session:
            await db_session.execute(
                update(TrafficSession)
                .where(TrafficSession.id == session_id)
                .values(status=SessionStatus.FAILED)
            )
        await db_factory.dispose()
    except Exception as e:
        logger.error("Failed to mark session %s FAILED: %s", session_id, e)

    try:
        from api.websocket_routes import broadcast_status
        await broadcast_status(
            session_id,
            {"status": "failed", "reason": reason[:500] if reason else "unknown"},
        )
    except Exception:
        pass
