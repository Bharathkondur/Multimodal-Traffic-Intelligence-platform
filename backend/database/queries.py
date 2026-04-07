"""
Database query helpers for the Multimodal Traffic Intelligence Platform.

Provides async query methods for common operations like retrieving detection
summaries, vehicle counts, incidents, and traffic flow analysis.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from decimal import Decimal

from sqlalchemy import (
    select,
    func,
    and_,
    or_,
    desc,
    asc,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    DetectionEvent,
    IncidentEvent,
    TrafficSession,
    TrafficReport,
    VehicleCount,
    VehicleType,
    IncidentType,
    SeverityLevel,
)

logger = logging.getLogger(__name__)

# Module-level factory — set by main.py at startup
_factory = None


def init_db(factory) -> None:
    """Set the global AsyncSessionFactory for use by query helpers."""
    global _factory
    _factory = factory


from contextlib import asynccontextmanager


@asynccontextmanager
async def _get_db():
    """Provide a transactional database session from the module-level factory."""
    if _factory is None:
        raise RuntimeError("Database factory not initialised. Call init_db() first.")
    async with _factory.session_context() as db:
        yield db


async def get_detection_summary(
    session: AsyncSession,
    session_id: str,
    time_range: Optional[tuple[datetime, datetime]] = None,
) -> Dict[str, Any]:
    """
    Get a summary of detection events for a session.

    Provides statistics on detection counts, confidence, and vehicle types
    within an optional time range.

    Args:
        session: AsyncSession for database queries
        session_id: Traffic session identifier
        time_range: Optional tuple of (start_time, end_time) for filtering

    Returns:
        Dictionary containing:
            - total_detections: Total number of detections
            - unique_tracks: Number of unique tracked vehicles
            - vehicle_type_breakdown: Dict of vehicle type counts
            - confidence_stats: Min/max/avg confidence scores
            - time_range: Applied time range

    Raises:
        SQLAlchemyError: If database query fails
    """
    try:
        # Build base query
        query = select(DetectionEvent).where(
            DetectionEvent.session_id == session_id
        )

        # Apply time range filter if provided
        if time_range:
            start_time, end_time = time_range
            query = query.where(
                and_(
                    DetectionEvent.timestamp >= start_time,
                    DetectionEvent.timestamp <= end_time,
                )
            )

        result = await session.execute(query)
        detections = result.scalars().all()

        # Calculate statistics
        total_detections = len(detections)
        unique_tracks = len(set(d.track_id for d in detections if d.track_id))

        # Vehicle type breakdown
        vehicle_type_breakdown: Dict[str, int] = {}
        for detection in detections:
            vehicle_type_breakdown[detection.vehicle_type.value] = (
                vehicle_type_breakdown.get(detection.vehicle_type.value, 0) + 1
            )

        # Confidence statistics
        confidences = [d.confidence for d in detections]
        confidence_stats = {
            "min": min(confidences) if confidences else None,
            "max": max(confidences) if confidences else None,
            "avg": (
                sum(confidences) / len(confidences)
                if confidences
                else None
            ),
            "count": len(confidences),
        }

        return {
            "total_detections": total_detections,
            "unique_tracks": unique_tracks,
            "vehicle_type_breakdown": vehicle_type_breakdown,
            "confidence_stats": confidence_stats,
            "time_range": {
                "start": time_range[0] if time_range else None,
                "end": time_range[1] if time_range else None,
            },
        }

    except Exception as e:
        logger.error(f"Error getting detection summary: {str(e)}")
        raise


async def get_vehicle_counts(
    session_id: str,
    session: AsyncSession = None,
    interval: int = 60,
    vehicle_type: Optional[VehicleType] = None,
    direction: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get aggregated vehicle count statistics by interval.

    Retrieves pre-computed vehicle counts or generates them from
    detection events.

    Args:
        session: AsyncSession for database queries
        session_id: Traffic session identifier
        interval: Interval duration in seconds (default: 60)
        vehicle_type: Optional vehicle type filter
        direction: Optional direction filter

    Returns:
        List of count records with timestamp, count, and metadata

    Raises:
        SQLAlchemyError: If database query fails
    """
    async def _run(db: AsyncSession) -> Dict[str, Any]:
        conditions = [
            VehicleCount.session_id == session_id,
            VehicleCount.interval_seconds == interval,
        ]
        if vehicle_type:
            conditions.append(VehicleCount.vehicle_type == vehicle_type)
        if direction:
            conditions.append(VehicleCount.direction == direction)

        result = await db.execute(
            select(VehicleCount).where(and_(*conditions)).order_by(asc(VehicleCount.timestamp))
        )
        counts = result.scalars().all()

        by_class: Dict[str, int] = {}
        by_time_window: Dict[str, int] = {}
        peak_time = None
        peak_count = 0

        for c in counts:
            vt = c.vehicle_type.value if hasattr(c.vehicle_type, "value") else str(c.vehicle_type)
            by_class[vt] = by_class.get(vt, 0) + c.count
            ts_key = c.timestamp.isoformat() if c.timestamp else ""
            by_time_window[ts_key] = by_time_window.get(ts_key, 0) + c.count
            if by_time_window[ts_key] > peak_count:
                peak_count = by_time_window[ts_key]
                peak_time = ts_key

        total = sum(by_class.values())
        return {
            "total_vehicles": total,
            "unique_vehicles": total,
            "by_class": by_class,
            "by_time_window": by_time_window,
            "peak_time": peak_time,
            "peak_count": peak_count,
        }

    try:
        if session is not None:
            return await _run(session)
        async with _get_db() as db:
            return await _run(db)
    except Exception as e:
        logger.error(f"Error getting vehicle counts: {str(e)}")
        raise


async def get_incidents(
    session: AsyncSession = None,
    session_id: str = None,
    incident_type: Optional[IncidentType] = None,
    severity: Optional[SeverityLevel] = None,
    resolved: Optional[bool] = None,
    limit: int = 1000,
    # Routes compat kwargs
    filters: dict = None,
    page: int = 1,
    page_size: int = 20,
):
    """
    Get incident events with optional filtering.

    Returns either List[Dict] or Tuple[List[Dict], int] depending on
    whether filters/page/page_size kwargs are used (routes convention).
    """
    use_pagination = filters is not None

    # Normalise filters dict
    if filters is not None:
        session_id = session_id or filters.get("session_id")
        if severity is None and filters.get("severity"):
            severity = filters["severity"]
        if incident_type is None and filters.get("incident_type"):
            incident_type = filters["incident_type"]
        limit = page_size

    async def _run(db: AsyncSession):
        conditions = [IncidentEvent.session_id == session_id]
        if incident_type:
            conditions.append(IncidentEvent.incident_type == incident_type)
        if severity:
            conditions.append(IncidentEvent.severity == severity)
        if resolved is not None:
            conditions.append(IncidentEvent.resolved == resolved)

        count_result = await db.execute(
            select(func.count(IncidentEvent.id)).where(and_(*conditions))
        )
        total = count_result.scalar() or 0

        skip = (page - 1) * page_size if use_pagination else 0
        q = (
            select(IncidentEvent)
            .where(and_(*conditions))
            .order_by(desc(IncidentEvent.timestamp))
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(q)
        incidents = result.scalars().all()

        rows = []
        for i in incidents:
            ts = i.timestamp.isoformat() if i.timestamp else datetime.utcnow().isoformat()
            rows.append({
                "id": str(i.id),
                "session_id": i.session_id,
                "timestamp": ts,
                "detected_at": ts,
                "incident_type": i.incident_type.value if hasattr(i.incident_type, "value") else str(i.incident_type),
                "severity": i.severity.value if hasattr(i.severity, "value") else str(i.severity),
                "description": i.description,
                "location": i.location_description,
                "location_description": i.location_description,
                "bbox": i.bbox,
                "related_detections": i.related_track_ids or [],
                "related_track_ids": i.related_track_ids,
                "confidence": 0.8,
                "resolved": i.resolved,
                "resolved_at": i.resolved_at,
                "metadata": {},
            })
        return rows, total

    try:
        if session is not None:
            rows, total = await _run(session)
        else:
            async with _get_db() as db:
                rows, total = await _run(db)
        return (rows, total) if use_pagination else rows
    except Exception as e:
        logger.error(f"Error getting incidents: {str(e)}")
        raise


async def get_traffic_flow(
    session: AsyncSession,
    session_id: str,
    time_range: Optional[tuple[datetime, datetime]] = None,
) -> Dict[str, Any]:
    """
    Get traffic flow analysis for a session.

    Analyzes vehicle movement patterns, speeds, and directions
    within the time range.

    Args:
        session: AsyncSession for database queries
        session_id: Traffic session identifier
        time_range: Optional tuple of (start_time, end_time)

    Returns:
        Dictionary containing:
            - total_vehicles_passed: Total vehicle count
            - avg_speed: Average vehicle speed
            - speed_range: Min and max speeds
            - direction_distribution: Distribution by direction
            - peak_activity_time: Time with most detections
            - vehicle_type_distribution: Distribution by type

    Raises:
        SQLAlchemyError: If database query fails
    """
    try:
        query = select(DetectionEvent).where(
            DetectionEvent.session_id == session_id
        )

        if time_range:
            start_time, end_time = time_range
            query = query.where(
                and_(
                    DetectionEvent.timestamp >= start_time,
                    DetectionEvent.timestamp <= end_time,
                )
            )

        result = await session.execute(query)
        detections = result.scalars().all()

        # Calculate statistics
        speeds = [d.speed_estimate for d in detections if d.speed_estimate]
        directions = [d.direction for d in detections if d.direction]
        vehicle_types = [d.vehicle_type for d in detections]

        # Direction distribution
        direction_distribution: Dict[str, int] = {}
        for direction in directions:
            direction_distribution[direction] = (
                direction_distribution.get(direction, 0) + 1
            )

        # Vehicle type distribution
        vehicle_type_distribution: Dict[str, int] = {}
        for vehicle_type in vehicle_types:
            vehicle_type_distribution[vehicle_type.value] = (
                vehicle_type_distribution.get(vehicle_type.value, 0) + 1
            )

        # Find peak activity time (group by hour and find max)
        if detections:
            hourly_counts: Dict[datetime, int] = {}
            for detection in detections:
                hour = detection.timestamp.replace(
                    minute=0, second=0, microsecond=0
                )
                hourly_counts[hour] = hourly_counts.get(hour, 0) + 1
            peak_time = max(hourly_counts, key=hourly_counts.get)
        else:
            peak_time = None

        return {
            "total_vehicles_passed": len(detections),
            "unique_tracks": len(set(d.track_id for d in detections if d.track_id)),
            "avg_speed": (
                sum(speeds) / len(speeds) if speeds else None
            ),
            "speed_range": {
                "min": min(speeds) if speeds else None,
                "max": max(speeds) if speeds else None,
            },
            "direction_distribution": direction_distribution,
            "vehicle_type_distribution": vehicle_type_distribution,
            "peak_activity_time": peak_time,
            "time_range": {
                "start": time_range[0] if time_range else None,
                "end": time_range[1] if time_range else None,
            },
        }

    except Exception as e:
        logger.error(f"Error getting traffic flow: {str(e)}")
        raise


async def search_events(
    session: AsyncSession,
    session_id: str,
    vehicle_type: Optional[VehicleType] = None,
    min_confidence: Optional[float] = None,
    track_id: Optional[str] = None,
    time_range: Optional[tuple[datetime, datetime]] = None,
    limit: int = 10000,
) -> List[Dict[str, Any]]:
    """
    Flexible search for detection events with multiple filters.

    Provides comprehensive filtering capabilities for finding specific
    detection events based on various criteria.

    Args:
        session: AsyncSession for database queries
        session_id: Traffic session identifier
        vehicle_type: Optional vehicle type filter
        min_confidence: Optional minimum confidence threshold
        track_id: Optional track ID for finding single vehicle
        time_range: Optional tuple of (start_time, end_time)
        limit: Maximum number of results

    Returns:
        List of detection events with all details

    Raises:
        SQLAlchemyError: If database query fails
    """
    try:
        query = select(DetectionEvent).where(
            DetectionEvent.session_id == session_id
        )

        # Apply optional filters
        if vehicle_type:
            query = query.where(DetectionEvent.vehicle_type == vehicle_type)

        if min_confidence is not None:
            query = query.where(DetectionEvent.confidence >= min_confidence)

        if track_id:
            query = query.where(DetectionEvent.track_id == track_id)

        if time_range:
            start_time, end_time = time_range
            query = query.where(
                and_(
                    DetectionEvent.timestamp >= start_time,
                    DetectionEvent.timestamp <= end_time,
                )
            )

        query = query.order_by(asc(DetectionEvent.timestamp)).limit(limit)

        result = await session.execute(query)
        events = result.scalars().all()

        return [
            {
                "id": event.id,
                "timestamp": event.timestamp,
                "frame_number": event.frame_number,
                "vehicle_type": event.vehicle_type.value,
                "confidence": float(event.confidence),
                "track_id": event.track_id,
                "bbox": {
                    "x": float(event.bbox_x),
                    "y": float(event.bbox_y),
                    "w": float(event.bbox_w),
                    "h": float(event.bbox_h),
                },
                "speed_estimate": event.speed_estimate,
                "direction": event.direction,
            }
            for event in events
        ]

    except Exception as e:
        logger.error(f"Error searching events: {str(e)}")
        raise


async def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a single session by ID. Returns None if not found."""
    async with _get_db() as db:
        try:
            result = await db.execute(
                select(TrafficSession).where(TrafficSession.id == session_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            status_val = row.status.value if hasattr(row.status, "value") else str(row.status)
            source_type_val = row.source_type.value if hasattr(row.source_type, "value") else str(row.source_type)
            start_time_str = row.start_time.isoformat() if row.start_time else datetime.utcnow().isoformat()
            return {
                "id": row.id,
                "name": row.source_url or f"Session {row.id[:8]}",
                "type": source_type_val,
                "status": status_val,
                "source_type": source_type_val,
                "source_url": row.source_url,
                "source": row.source_url,
                "created_at": start_time_str,
                "updated_at": start_time_str,
                "start_time": row.start_time,
                "metadata": row.metadata_json,
            }
        except Exception as e:
            logger.error(f"Error fetching session {session_id}: {e}")
            return None


async def get_session_stats(
    session_id: str,
    session: AsyncSession = None,
) -> Dict[str, Any]:
    """
    Get comprehensive statistics for a traffic session.

    Provides an overview of session activity including detection counts,
    incident summaries, duration, and key metrics.

    Args:
        session: AsyncSession for database queries
        session_id: Traffic session identifier

    Returns:
        Dictionary containing:
            - session_info: Basic session details
            - detection_stats: Detection event statistics
            - incident_stats: Incident event statistics
            - vehicle_stats: Vehicle-related statistics
            - temporal_info: Duration and time-based metrics
            - data_quality: Confidence and coverage metrics

    Raises:
        SQLAlchemyError: If database query fails
    """
    async def _run(db: AsyncSession) -> Dict[str, Any]:
        # Get session info
        session_query = select(TrafficSession).where(
            TrafficSession.id == session_id
        )
        session_result = await db.execute(session_query)
        traffic_session = session_result.scalar_one_or_none()

        if not traffic_session:
            logger.warning(f"Session not found: {session_id}")
            return {}

        # Count detections
        detection_count_result = await db.execute(
            select(func.count(DetectionEvent.id)).where(
                DetectionEvent.session_id == session_id
            )
        )
        total_detections = detection_count_result.scalar() or 0

        # Count incidents
        incident_count_result = await db.execute(
            select(func.count(IncidentEvent.id)).where(
                IncidentEvent.session_id == session_id
            )
        )
        total_incidents = incident_count_result.scalar() or 0

        # Get average confidence
        avg_confidence_result = await db.execute(
            select(func.avg(DetectionEvent.confidence)).where(
                DetectionEvent.session_id == session_id
            )
        )
        avg_confidence = avg_confidence_result.scalar() or 0.0

        return {
            # Flat keys for routes.py SessionStatsResponse
            "detections_count": total_detections,
            "incidents_count": total_incidents,
            "avg_detection_confidence": float(avg_confidence),
            "total_frames": 0,
            "processing_fps": 0.0,
            # Nested keys for other consumers
            "session_info": {
                "id": traffic_session.id,
                "start_time": traffic_session.start_time,
                "end_time": traffic_session.end_time,
                "status": traffic_session.status.value if hasattr(traffic_session.status, "value") else traffic_session.status,
                "source_type": traffic_session.source_type.value if hasattr(traffic_session.source_type, "value") else traffic_session.source_type,
                "source_url": traffic_session.source_url,
            },
            "metadata": traffic_session.metadata_json,
        }

    try:
        if session is not None:
            return await _run(session)
        async with _get_db() as db:
            return await _run(db)
    except Exception as e:
        logger.error(f"Error getting session stats: {str(e)}")
        raise


async def create_session(
    name: str = "session",
    session_type: str = "upload",
    source: str = "",
    metadata: dict = None,
    # Legacy positional args (kept for internal callers that pass db explicitly)
    db: AsyncSession = None,
    source_type: str = None,
    source_url: str = None,
) -> dict:
    """
    Create a new TrafficSession in DB.

    Accepts either the simplified interface used by routes.py:
        create_session(name=..., session_type=..., source=...)
    or the legacy interface:
        create_session(db, source_type, source_url, metadata)
    """
    # Normalise kwargs from both calling conventions
    _source_type = source_type or session_type
    _source_url = source_url or source

    from uuid import uuid4

    async def _create(db: AsyncSession) -> dict:
        try:
            session_id = str(uuid4())
            traffic_session = TrafficSession(
                id=session_id,
                source_type=_source_type,
                source_url=_source_url,
                status="active",
                metadata_json=metadata,
            )
            db.add(traffic_session)
            await db.commit()
            await db.refresh(traffic_session)
            logger.info(f"Created traffic session: {session_id}")
            return {
                "id": traffic_session.id,
                "name": name,
                "status": traffic_session.status.value if hasattr(traffic_session.status, 'value') else traffic_session.status,
                "source_type": traffic_session.source_type.value if hasattr(traffic_session.source_type, 'value') else traffic_session.source_type,
                "source_url": traffic_session.source_url,
                "start_time": traffic_session.start_time,
                "metadata": traffic_session.metadata_json,
            }
        except Exception as e:
            logger.error(f"Error creating session: {str(e)}")
            await db.rollback()
            raise

    if db is not None:
        return await _create(db)
    async with _get_db() as db:
        return await _create(db)


async def count_active_sessions(db: AsyncSession = None) -> int:
    """Count sessions with status='active'."""
    async def _count(db: AsyncSession) -> int:
        try:
            query = select(func.count(TrafficSession.id)).where(
                TrafficSession.status == "active"
            )
            result = await db.execute(query)
            count = result.scalar() or 0
            logger.debug(f"Active sessions count: {count}")
            return count
        except Exception as e:
            logger.error(f"Error counting active sessions: {str(e)}")
            raise

    if db is not None:
        return await _count(db)
    async with _get_db() as db:
        return await _count(db)


async def get_detections(
    db: AsyncSession = None,
    session_id: str = None,
    skip: int = 0,
    limit: int = 50,
    vehicle_type: str = None,
    min_confidence: float = None,
    start_time=None,
    end_time=None,
    # Routes compat kwargs
    filters: dict = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict], int]:
    """
    Get paginated detections with filters.

    Supports two calling conventions:
        Legacy: get_detections(db, session_id, skip, limit, ...)
        Routes: get_detections(filters={...}, page=N, page_size=N)

    Returns:
        Tuple of (list of detection dicts, total count)
    """
    # Normalise calling convention
    if filters is not None:
        session_id = session_id or filters.get("session_id")
        if min_confidence is None:
            min_confidence = filters.get("confidence_min") or filters.get("min_confidence")
        vehicle_type = vehicle_type or filters.get("vehicle_type") or filters.get("class_name")
        skip = (page - 1) * page_size
        limit = page_size

    async def _run(db: AsyncSession) -> tuple[list[dict], int]:
        base_where = [DetectionEvent.session_id == session_id]
        if vehicle_type:
            base_where.append(DetectionEvent.vehicle_type == vehicle_type)
        if min_confidence is not None:
            base_where.append(DetectionEvent.confidence >= min_confidence)
        if start_time:
            base_where.append(DetectionEvent.timestamp >= start_time)
        if end_time:
            base_where.append(DetectionEvent.timestamp <= end_time)

        count_result = await db.execute(
            select(func.count(DetectionEvent.id)).where(and_(*base_where))
        )
        total_count = count_result.scalar() or 0

        data_result = await db.execute(
            select(DetectionEvent)
            .where(and_(*base_where))
            .order_by(asc(DetectionEvent.timestamp))
            .offset(skip)
            .limit(limit)
        )
        detections = data_result.scalars().all()

        detections_list = []
        for d in detections:
            x = float(d.bbox_x or 0)
            y = float(d.bbox_y or 0)
            w = float(d.bbox_w or 0)
            h = float(d.bbox_h or 0)
            detections_list.append({
                "id": str(d.id),
                "session_id": d.session_id,
                "frame_number": d.frame_number or 0,
                "timestamp": d.timestamp.isoformat() if d.timestamp else datetime.utcnow().isoformat(),
                "class_name": d.vehicle_type.value if hasattr(d.vehicle_type, "value") else str(d.vehicle_type),
                "vehicle_type": d.vehicle_type.value if hasattr(d.vehicle_type, "value") else str(d.vehicle_type),
                "confidence": float(d.confidence or 0),
                "track_id": d.track_id,
                "bbox": [x, y, x + w, y + h],
                "center": [x + w / 2, y + h / 2],
                "area": w * h,
                "speed_estimate": d.speed_estimate,
                "direction": d.direction,
            })

        logger.debug(f"Retrieved {len(detections_list)} detections for session {session_id}")
        return detections_list, total_count

    try:
        if db is not None:
            return await _run(db)
        async with _get_db() as db:
            return await _run(db)
    except Exception as e:
        logger.error(f"Error getting detections: {str(e)}")
        raise


async def update_session_status(
    session_id: str,
    status: str,
    db: AsyncSession = None,
) -> bool:
    """
    Update session status.

    Args:
        db: AsyncSession for database operations
        session_id: Traffic session identifier
        status: New status value (active, completed, failed, paused)

    Returns:
        True if updated, False if session not found

    Raises:
        SQLAlchemyError: If database operation fails
    """
    async def _run(db: AsyncSession) -> bool:
        query = select(TrafficSession).where(TrafficSession.id == session_id)
        result = await db.execute(query)
        traffic_session = result.scalar_one_or_none()

        if not traffic_session:
            logger.warning(f"Session not found: {session_id}")
            return False

        traffic_session.status = status
        if status in ("completed", "failed", "stopped"):
            traffic_session.end_time = datetime.utcnow()

        await db.commit()
        logger.info(f"Updated session {session_id} status to {status}")
        return True

    try:
        if db is not None:
            return await _run(db)
        async with _get_db() as db:
            return await _run(db)
    except Exception as e:
        logger.error(f"Error updating session status: {str(e)}")
        raise


async def create_report(
    db: AsyncSession = None,
    session_id: str = None,
    report_type: str = "summary",
    content=None,
    query_text: str = None,
) -> dict:
    """
    Create a TrafficReport record.

    Args:
        db: AsyncSession for database operations
        session_id: Traffic session identifier
        report_type: Type of report (summary, detailed, incident_analysis, etc.)
        content: Report content (flexible JSON structure)
        query_text: Optional original query or parameters used to generate report

    Returns:
        Dictionary with report details including id

    Raises:
        SQLAlchemyError: If database operation fails
    """
    import json as _json

    if content is None:
        content_json = {}
    elif isinstance(content, str):
        try:
            content_json = _json.loads(content)
        except _json.JSONDecodeError:
            content_json = {"text": content}
    else:
        content_json = content

    async def _run(db: AsyncSession) -> dict:
        report = TrafficReport(
            session_id=session_id,
            report_type=report_type,
            content=content_json,
            query_text=query_text,
        )
        db.add(report)
        await db.commit()
        await db.refresh(report)
        logger.info(f"Created report {report.id} of type {report_type} for session {session_id}")
        generated_str = report.generated_at.isoformat() if report.generated_at else datetime.utcnow().isoformat()
        return {
            "id": str(report.id),
            "session_id": report.session_id,
            "report_type": report.report_type,
            "content": report.content,
            "query_text": report.query_text,
            "generated_at": generated_str,
            "created_at": generated_str,
        }

    try:
        if db is not None:
            return await _run(db)
        async with _get_db() as db:
            return await _run(db)
    except Exception as e:
        logger.error(f"Error creating report: {str(e)}")
        raise


async def check_health(db: AsyncSession = None) -> bool:
    """Check database connectivity with a simple query."""
    async def _check(db: AsyncSession) -> bool:
        try:
            await db.execute(text("SELECT 1"))
            logger.debug("Database health check passed")
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {str(e)}")
            return False

    if db is not None:
        return await _check(db)
    async with _get_db() as db:
        return await _check(db)


async def batch_write_detections(
    db: AsyncSession,
    detections: list[dict],
) -> int:
    """
    Bulk insert detection events.

    Args:
        db: AsyncSession for database operations
        detections: List of detection dictionaries with required fields

    Returns:
        Integer count of inserted records

    Raises:
        SQLAlchemyError: If database operation fails
    """
    try:
        detection_objects = []

        for detection in detections:
            detection_event = DetectionEvent(
                session_id=detection["session_id"],
                timestamp=detection.get("timestamp", datetime.utcnow()),
                frame_number=detection.get("frame_number"),
                vehicle_type=detection.get("vehicle_type", "unknown"),
                confidence=detection.get("confidence", 0.0),
                track_id=detection.get("track_id"),
                bbox_x=detection.get("bbox_x", 0),
                bbox_y=detection.get("bbox_y", 0),
                bbox_w=detection.get("bbox_w", 0),
                bbox_h=detection.get("bbox_h", 0),
                speed_estimate=detection.get("speed_estimate"),
                direction=detection.get("direction"),
            )
            detection_objects.append(detection_event)

        db.add_all(detection_objects)
        await db.commit()

        logger.info(f"Batch inserted {len(detection_objects)} detection events")
        return len(detection_objects)

    except Exception as e:
        logger.error(f"Error batch writing detections: {str(e)}")
        await db.rollback()
        raise


async def batch_write_incidents(
    db: AsyncSession,
    incidents: list[dict],
) -> int:
    """
    Bulk insert incident events.

    Args:
        db: AsyncSession for database operations
        incidents: List of incident dictionaries with required fields

    Returns:
        Integer count of inserted records

    Raises:
        SQLAlchemyError: If database operation fails
    """
    try:
        incident_objects = []

        for incident in incidents:
            incident_event = IncidentEvent(
                session_id=incident["session_id"],
                timestamp=incident.get("timestamp", datetime.utcnow()),
                incident_type=incident.get("incident_type", "other"),
                severity=incident.get("severity", "low"),
                location_description=incident.get("location_description"),
                bbox=incident.get("bbox"),
                related_track_ids=incident.get("related_track_ids"),
                resolved=incident.get("resolved", False),
                resolved_at=incident.get("resolved_at"),
                description=incident.get("description"),
            )
            incident_objects.append(incident_event)

        db.add_all(incident_objects)
        await db.commit()

        logger.info(f"Batch inserted {len(incident_objects)} incident events")
        return len(incident_objects)

    except Exception as e:
        logger.error(f"Error batch writing incidents: {str(e)}")
        await db.rollback()
        raise
