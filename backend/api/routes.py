"""
REST API routes for Multimodal Traffic Intelligence Platform.

Provides endpoints for session management, detection retrieval, incident analysis,
chat interactions, report generation, zone analytics, heatmaps, and demo simulation.
"""

import logging
import os
import base64
from typing import Optional, List
from datetime import datetime

from fastapi import (
    APIRouter,
    File,
    UploadFile,
    HTTPException,
    Query,
    BackgroundTasks,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel

from api.schemas import (
    UploadResponse,
    StreamStartRequest,
    SessionResponse,
    DetectionResponse,
    IncidentResponse,
    SessionStatsResponse,
    VehicleCountResponse,
    ChatRequest,
    ChatResponse,
    ReportRequest,
    ReportResponse,
    HealthResponse,
    PaginatedResponse,
)
from config import settings
from database.connection import AsyncSessionFactory
from database.queries import (
    create_session,
    get_session_stats,
    get_detection_summary,
    get_vehicle_counts,
    get_incidents,
    get_traffic_flow,
    search_events,
    update_session_status,
    create_report,
    check_health,
    count_active_sessions,
    get_detections,
    batch_write_detections,
    batch_write_incidents,
)
from processing.detection import start_detection_pipeline
from processing.stream import start_stream_pipeline
from processing.reports import generate_report_task
from processing.cleanup import cleanup_session
from processing.simulator import TrafficSimulator
from agents.langgraph_agent import process_message
from analytics.zones import ZoneAnalytics, Zone
from analytics.heatmap import TrafficHeatmap
from analytics.speed import SpeedEstimator
from models.detection import get_model

logger = logging.getLogger(__name__)

router = APIRouter(prefix=settings.api_prefix, tags=["api"])

# Demo mode state
_demo_simulator: Optional[TrafficSimulator] = None
_zone_analytics: Optional[ZoneAnalytics] = None
_heatmap_generator: Optional[TrafficHeatmap] = None
_speed_estimator: Optional[SpeedEstimator] = None


# Helper Schemas
class ZoneCreateRequest(BaseModel):
    """Request to create a new zone."""
    name: str
    polygon: List[tuple[float, float]]
    zone_type: str = "monitoring"
    metadata: dict = {}


class ZoneResponse(BaseModel):
    """Response containing zone information."""
    id: str
    name: str
    polygon: List[tuple[float, float]]
    zone_type: str
    metadata: dict
    created_at: datetime
    vehicle_count: int = 0
    avg_speed: float = 0.0


class DemoStartRequest(BaseModel):
    """Request to start demo simulation."""
    session_name: str = "Demo Traffic Simulation"
    duration_seconds: int = 3600
    vehicle_spawn_rate: float = 5.0


class SpeedStatsResponse(BaseModel):
    """Response containing speed statistics."""
    session_id: str
    avg_speed: float
    max_speed: float
    min_speed: float
    speed_distribution: dict
    speeding_violations: int


# Session Management Routes


@router.post(
    "/sessions/upload",
    response_model=UploadResponse,
    summary="Upload video file and start processing",
    responses={
        400: {"description": "Invalid file type"},
        413: {"description": "File too large"},
        500: {"description": "Processing error"},
    },
)
async def upload_session(
    file: UploadFile = File(..., media_type="video/*"),
    name: Optional[str] = Query(None, max_length=255),
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> UploadResponse:
    """
    Upload a video file and start traffic intelligence processing.

    Args:
        file: Video file to process (MP4, AVI, MOV, MKV, FLV)
        name: Optional custom session name
        background_tasks: FastAPI background tasks

    Returns:
        UploadResponse with session ID and status

    Raises:
        HTTPException: If file validation fails or processing error occurs
    """
    # Validate file type
    allowed_types = {".mp4", ".avi", ".mov", ".mkv", ".flv"}
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(allowed_types)}",
        )

    try:
        # Check file size
        file_content = await file.read()
        if len(file_content) > settings.max_upload_size:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Max size: {settings.max_upload_size / 1e9:.1f}GB",
            )

        # Create session in database
        session = await create_session(
            name=name or file.filename,
            session_type="upload",
            source=file.filename,
        )

        # Save file
        upload_path = os.path.join(settings.upload_dir, session["id"], file.filename)
        os.makedirs(os.path.dirname(upload_path), exist_ok=True)

        with open(upload_path, "wb") as f:
            f.write(file_content)

        # Start processing in background
        background_tasks.add_task(
            start_detection_pipeline,
            session["id"],
            upload_path,
        )

        return UploadResponse(
            session_id=session["id"],
            filename=file.filename,
            file_size=len(file_content),
            status="processing",
            message="File uploaded successfully, processing started",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Processing error occurred")


@router.post(
    "/sessions/stream",
    response_model=SessionResponse,
    summary="Start streaming from RTSP or webcam",
    responses={
        429: {"description": "Too many concurrent sessions"},
        500: {"description": "Stream connection error"},
    },
)
async def start_stream(
    request: StreamStartRequest,
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> SessionResponse:
    """
    Start live stream processing from RTSP camera or webcam.

    Features:
        - Support for RTSP streams and webcam input
        - Configurable frame rate
        - Real-time detection and incident alerts
    """
    try:
        # Check concurrent session limit
        active = await count_active_sessions()
        if active >= settings.max_concurrent_sessions:
            raise HTTPException(
                status_code=429,
                detail=f"Max concurrent sessions ({settings.max_concurrent_sessions}) reached",
            )

        # Create session
        session = await create_session(
            name=request.name,
            session_type="stream",
            source=request.stream_url,
        )

        # Start stream pipeline in background
        background_tasks.add_task(
            start_stream_pipeline,
            session["id"],
            request.stream_url,
            request.fps,
        )

        return SessionResponse(
            id=session["id"],
            name=session["name"],
            type="stream",
            status="processing",
            created_at=datetime.fromisoformat(session["created_at"]),
            updated_at=datetime.fromisoformat(session["updated_at"]),
            source=request.stream_url,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Stream start failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Stream connection failed")


@router.get(
    "/sessions/{session_id}",
    response_model=SessionResponse,
    summary="Get session information",
    responses={404: {"description": "Session not found"}},
)
async def get_session(session_id: str) -> SessionResponse:
    """Get session information and current status."""
    try:
        from database.queries import get_session as db_get_session

        session = await db_get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        return SessionResponse(
            id=session["id"],
            name=session["name"],
            type=session["type"],
            status=session["status"],
            created_at=datetime.fromisoformat(session["created_at"]),
            updated_at=datetime.fromisoformat(session["updated_at"]),
            source=session["source"],
            frame_count=session.get("frame_count", 0),
            duration_seconds=session.get("duration_seconds", 0),
            vehicle_count=session.get("vehicle_count", 0),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get session failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/sessions/{session_id}/detections",
    response_model=PaginatedResponse[DetectionResponse],
    summary="Get detections with filtering",
    responses={404: {"description": "Session not found"}},
)
async def get_detections_endpoint(
    session_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    class_name: Optional[str] = Query(None),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
) -> PaginatedResponse[DetectionResponse]:
    """Get detections for a session with optional filtering."""
    try:
        from database.queries import get_session as db_get_session

        # Verify session exists
        session = await db_get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Build filters
        filters = {
            "session_id": session_id,
            "confidence_min": min_confidence,
        }
        if class_name:
            filters["class_name"] = class_name

        # Get paginated results
        results, total = await get_detections(
            filters=filters,
            page=page,
            page_size=page_size,
        )

        items = [
            DetectionResponse(
                id=r["id"],
                session_id=r["session_id"],
                frame_number=r["frame_number"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
                class_name=r["class_name"],
                confidence=r["confidence"],
                bbox=r["bbox"],
                center=r["center"],
                area=r["area"],
                track_id=r.get("track_id"),
            )
            for r in results
        ]

        total_pages = (total + page_size - 1) // page_size

        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get detections failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/sessions/{session_id}/incidents",
    response_model=PaginatedResponse[IncidentResponse],
    summary="Get detected incidents",
    responses={404: {"description": "Session not found"}},
)
async def get_incidents_endpoint(
    session_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    severity: Optional[str] = Query(None),
    incident_type: Optional[str] = Query(None),
) -> PaginatedResponse[IncidentResponse]:
    """Get traffic incidents detected in a session."""
    try:
        from database.queries import get_session as db_get_session

        session = await db_get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        filters = {"session_id": session_id}
        if severity:
            filters["severity"] = severity
        if incident_type:
            filters["incident_type"] = incident_type

        results, total = await get_incidents(
            filters=filters,
            page=page,
            page_size=page_size,
        )

        items = [
            IncidentResponse(
                id=r["id"],
                session_id=r["session_id"],
                incident_type=r["incident_type"],
                severity=r["severity"],
                description=r["description"],
                detected_at=datetime.fromisoformat(r["detected_at"]),
                confidence=r["confidence"],
                related_detections=r.get("related_detections", []),
                location=r.get("location"),
                metadata=r.get("metadata", {}),
            )
            for r in results
        ]

        total_pages = (total + page_size - 1) // page_size

        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get incidents failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/sessions/{session_id}/stats",
    response_model=SessionStatsResponse,
    summary="Get session statistics",
    responses={404: {"description": "Session not found"}},
)
async def get_session_stats_endpoint(session_id: str) -> SessionStatsResponse:
    """Get aggregated statistics for a session."""
    try:
        stats = await get_session_stats(session_id)
        if not stats:
            raise HTTPException(status_code=404, detail="Session not found")

        return SessionStatsResponse(
            session_id=session_id,
            total_frames=stats.get("total_frames", 0),
            processing_fps=stats.get("processing_fps", 0.0),
            detections_count=stats.get("detections_count", 0),
            incidents_count=stats.get("incidents_count", 0),
            avg_detection_confidence=stats.get("avg_detection_confidence", 0.0),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get stats failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/sessions/{session_id}/vehicle-counts",
    response_model=VehicleCountResponse,
    summary="Get vehicle count aggregation",
    responses={404: {"description": "Session not found"}},
)
async def get_vehicle_counts_endpoint(session_id: str) -> VehicleCountResponse:
    """Get aggregated vehicle counts and statistics."""
    try:
        counts = await get_vehicle_counts(session_id)
        if not counts:
            raise HTTPException(status_code=404, detail="Session not found")

        return VehicleCountResponse(
            session_id=session_id,
            total_vehicles=counts.get("total_vehicles", 0),
            unique_vehicles=counts.get("unique_vehicles", 0),
            by_class=counts.get("by_class", {}),
            by_time_window=counts.get("by_time_window", {}),
            peak_time=(
                datetime.fromisoformat(counts["peak_time"])
                if counts.get("peak_time")
                else None
            ),
            peak_count=counts.get("peak_count", 0),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get vehicle counts failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Chat Routes


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Send message to LangGraph agent",
    responses={404: {"description": "Session not found"}},
)
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    """
    Send a message to the AI agent for session analysis.

    Features:
        - Context-aware responses using session data
        - Multi-turn conversation support
        - Source attribution for generated responses
    """
    try:
        from database.queries import get_session as db_get_session

        # Verify session exists
        session = await db_get_session(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Process message through LangGraph agent
        response = await process_message(
            session_id=request.session_id,
            user_message=request.message,
            include_context=request.include_context,
        )

        return ChatResponse(
            session_id=request.session_id,
            message=response.get("message", ""),
            sources=response.get("sources", []),
            confidence=response.get("confidence", 1.0),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Agent processing error")


# Report Routes


@router.post(
    "/reports/generate",
    response_model=ReportResponse,
    summary="Generate analysis report",
    responses={404: {"description": "Session not found"}},
)
async def generate_report_endpoint(
    request: ReportRequest,
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> ReportResponse:
    """
    Generate a traffic analysis report for a session.

    Report Types:
        - summary: Key metrics and findings
        - detailed: Full analysis with charts
        - executive: High-level overview for stakeholders
    """
    try:
        from database.queries import get_session as db_get_session

        session = await db_get_session(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Create report record
        report = await create_report(
            session_id=request.session_id,
            report_type=request.report_type,
        )

        # Generate in background
        background_tasks.add_task(
            generate_report_task,
            report["id"],
            request,
        )

        return ReportResponse(
            id=report["id"],
            session_id=request.session_id,
            report_type=request.report_type,
            title=f"{request.report_type.capitalize()} Report - {session['name']}",
            summary="Generating report...",
            generated_at=datetime.fromisoformat(report["created_at"]),
            download_url=f"{settings.api_prefix}/reports/{report['id']}/download",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Generate report failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Report generation failed")


# Health Check Route


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    tags=["system"],
)
async def health_check_endpoint() -> HealthResponse:
    """
    Check API and component health status.

    Components:
        - database: PostgreSQL connection
        - redis: Redis cache connection
        - models: YOLOv8 model loaded
    """
    try:
        components = {
            "database": "unknown",
            "redis": "unknown",
            "models": "unknown",
        }

        # Check database
        try:
            db_ok = await check_health()
            components["database"] = "healthy" if db_ok else "unhealthy"
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            components["database"] = "unhealthy"

        # Check models
        try:
            model = get_model()
            components["models"] = "loaded" if model else "unloaded"
        except Exception as e:
            logger.error(f"Model health check failed: {e}")
            components["models"] = "unloaded"

        # Overall status
        unhealthy = sum(1 for v in components.values() if "unhealthy" in v)
        if unhealthy > 0:
            status = "degraded" if unhealthy < 2 else "unhealthy"
        else:
            status = "healthy"

        return HealthResponse(
            status=status,
            timestamp=datetime.utcnow(),
            components=components,
            version=settings.api_version,
        )

    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return HealthResponse(
            status="unhealthy",
            timestamp=datetime.utcnow(),
            components={},
            version=settings.api_version,
        )


# Session Cleanup Route


@router.delete(
    "/sessions/{session_id}",
    summary="Stop and cleanup session",
    responses={404: {"description": "Session not found"}},
)
async def delete_session_endpoint(
    session_id: str,
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    Stop session processing and cleanup resources.

    Behavior:
        - Stops ongoing processing
        - Cleans up temporary files
        - Keeps database records (soft delete)
        - Returns immediately, cleanup happens in background
    """
    try:
        from database.queries import get_session as db_get_session

        session = await db_get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Mark as stopped
        await update_session_status(session_id, "stopped")

        # Cleanup in background
        background_tasks.add_task(cleanup_session, session_id)

        return {"status": "stopping", "session_id": session_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete session failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Cleanup failed")


# ============================================================================
# INNOVATIVE FEATURES: Demo Simulation, Zones, Heatmaps, Speed Analysis
# ============================================================================


# Demo Simulation Endpoints


@router.post(
    "/demo/start",
    summary="Start demo traffic simulation",
    tags=["demo"],
    responses={409: {"description": "Demo already running"}},
)
async def start_demo(
    request: DemoStartRequest = DemoStartRequest(),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    Start a realistic traffic simulation for portfolio demonstration.

    Generates:
        - Natural vehicle movement patterns
        - Lane-based traffic with realistic speeds
        - Periodic traffic incidents
        - WebSocket-compatible streaming data
    """
    global _demo_simulator

    try:
        if _demo_simulator and _demo_simulator.running:
            raise HTTPException(
                status_code=409,
                detail="Demo simulation already running",
            )

        # Create session for demo
        session = await create_session(
            name=request.session_name,
            session_type="demo",
            source="simulator",
        )

        # Create simulator instance
        _demo_simulator = TrafficSimulator(
            session_id=session["id"],
        )

        # Start simulation in background
        background_tasks.add_task(
            _demo_simulator.start,
            duration_seconds=request.duration_seconds,
        )

        return {
            "status": "started",
            "session_id": session["id"],
            "session_name": session["name"],
            "duration_seconds": request.duration_seconds,
            "message": "Demo simulation running. Connect to WebSocket for live stream.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Demo start failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Demo start failed")


@router.post(
    "/demo/stop",
    summary="Stop demo traffic simulation",
    tags=["demo"],
    responses={409: {"description": "Demo not running"}},
)
async def stop_demo():
    """Stop the running traffic simulation."""
    global _demo_simulator

    try:
        if not _demo_simulator or not _demo_simulator.running:
            raise HTTPException(status_code=409, detail="No demo running")

        await _demo_simulator.stop()

        return {
            "status": "stopped",
            "session_id": _demo_simulator.session_id,
            "message": "Demo simulation stopped",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Demo stop failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Demo stop failed")


# Zone Management Endpoints


@router.post(
    "/zones",
    response_model=ZoneResponse,
    summary="Create a monitoring zone",
    tags=["zones"],
)
async def create_zone(request: ZoneCreateRequest) -> ZoneResponse:
    """
    Create a geographic zone for traffic monitoring and analytics.

    Zones can be used for:
        - Speed monitoring
        - Vehicle counting in specific areas
        - Incident detection within zone
        - Heatmap generation
    """
    try:
        global _zone_analytics

        if not _zone_analytics:
            _zone_analytics = ZoneAnalytics()

        zone = await _zone_analytics.create_zone(
            name=request.name,
            polygon=request.polygon,
            zone_type=request.zone_type,
            metadata=request.metadata,
        )

        return ZoneResponse(
            id=zone.id,
            name=zone.name,
            polygon=zone.polygon,
            zone_type=zone.zone_type,
            metadata=zone.metadata,
            created_at=zone.created_at,
            vehicle_count=0,
            avg_speed=0.0,
        )

    except Exception as e:
        logger.error(f"Create zone failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create zone")


@router.get(
    "/zones",
    response_model=List[ZoneResponse],
    summary="List all zones",
    tags=["zones"],
)
async def list_zones() -> List[ZoneResponse]:
    """Get all defined zones."""
    try:
        global _zone_analytics

        if not _zone_analytics:
            return []

        zones = await _zone_analytics.get_all_zones()

        return [
            ZoneResponse(
                id=zone.id,
                name=zone.name,
                polygon=zone.polygon,
                zone_type=zone.zone_type,
                metadata=zone.metadata,
                created_at=zone.created_at,
            )
            for zone in zones
        ]

    except Exception as e:
        logger.error(f"List zones failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list zones")


@router.get(
    "/zones/{zone_id}/stats",
    summary="Get zone analytics",
    tags=["zones"],
    responses={404: {"description": "Zone not found"}},
)
async def get_zone_stats(zone_id: str):
    """Get traffic statistics for a specific zone."""
    try:
        global _zone_analytics

        if not _zone_analytics:
            raise HTTPException(status_code=404, detail="Zone not found")

        stats = await _zone_analytics.get_zone_stats(zone_id)
        if not stats:
            raise HTTPException(status_code=404, detail="Zone not found")

        return {
            "zone_id": zone_id,
            "vehicle_count": stats.get("vehicle_count", 0),
            "avg_speed": stats.get("avg_speed", 0.0),
            "peak_flow": stats.get("peak_flow", 0),
            "incidents_in_zone": stats.get("incidents", 0),
            "timestamp": datetime.utcnow(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get zone stats failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get zone stats")


@router.delete(
    "/zones/{zone_id}",
    summary="Delete a zone",
    tags=["zones"],
    responses={404: {"description": "Zone not found"}},
)
async def delete_zone(zone_id: str):
    """Remove a monitoring zone."""
    try:
        global _zone_analytics

        if not _zone_analytics:
            raise HTTPException(status_code=404, detail="Zone not found")

        deleted = await _zone_analytics.delete_zone(zone_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Zone not found")

        return {"status": "deleted", "zone_id": zone_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete zone failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete zone")


# Heatmap Endpoint


@router.get(
    "/sessions/{session_id}/heatmap",
    summary="Get traffic heatmap",
    tags=["analytics"],
    responses={404: {"description": "Session not found"}},
)
async def get_heatmap(session_id: str):
    """
    Get heatmap visualization of traffic density as base64 PNG.

    Shows vehicle density and movement patterns across the frame.
    """
    try:
        from database.queries import get_session as db_get_session

        # Verify session exists
        session = await db_get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        global _heatmap_generator

        if not _heatmap_generator:
            _heatmap_generator = TrafficHeatmap()

        # Generate heatmap
        heatmap_image = await _heatmap_generator.generate_heatmap(session_id)

        # Convert to base64 PNG
        import io
        buffer = io.BytesIO()
        heatmap_image.save(buffer, format="PNG")
        img_b64 = base64.b64encode(buffer.getvalue()).decode()

        return {
            "session_id": session_id,
            "heatmap": f"data:image/png;base64,{img_b64}",
            "format": "png",
            "timestamp": datetime.utcnow(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get heatmap failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate heatmap")


# Speed Analysis Endpoint


@router.get(
    "/sessions/{session_id}/speeds",
    response_model=SpeedStatsResponse,
    summary="Get speed statistics",
    tags=["analytics"],
    responses={404: {"description": "Session not found"}},
)
async def get_speed_stats(session_id: str) -> SpeedStatsResponse:
    """
    Get vehicle speed analysis and statistics.

    Includes:
        - Average, max, min speeds
        - Speed distribution histogram
        - Count of speeding violations
    """
    try:
        from database.queries import get_session as db_get_session

        # Verify session exists
        session = await db_get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        global _speed_estimator

        if not _speed_estimator:
            _speed_estimator = SpeedEstimator()

        # Calculate speed statistics
        stats = await _speed_estimator.analyze_session_speeds(session_id)

        return SpeedStatsResponse(
            session_id=session_id,
            avg_speed=stats.get("avg_speed", 0.0),
            max_speed=stats.get("max_speed", 0.0),
            min_speed=stats.get("min_speed", 0.0),
            speed_distribution=stats.get("distribution", {}),
            speeding_violations=stats.get("violations", 0),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get speed stats failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get speed statistics")
