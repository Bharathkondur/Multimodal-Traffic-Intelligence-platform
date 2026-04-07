"""
Pydantic schemas for API request/response bodies.

Includes comprehensive type validation, JSON schema examples, and documentation.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any, Generic, TypeVar
from datetime import datetime
from enum import Enum


class DetectionClass(str, Enum):
    """Vehicle detection classes."""

    PERSON = "person"
    BICYCLE = "bicycle"
    CAR = "car"
    MOTORCYCLE = "motorcycle"
    AIRPLANE = "airplane"
    BUS = "bus"
    TRAIN = "train"
    TRUCK = "truck"
    BOAT = "boat"
    TRAFFIC_LIGHT = "traffic light"
    FIRE_HYDRANT = "fire hydrant"
    STOP_SIGN = "stop sign"
    PARKING_METER = "parking meter"
    BENCH = "bench"
    # DB vehicle types
    PEDESTRIAN = "pedestrian"
    VAN = "van"
    UNKNOWN = "unknown"


class IncidentSeverity(str, Enum):
    """Incident severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentType(str, Enum):
    """Types of traffic incidents."""

    ACCIDENT = "accident"
    CONGESTION = "congestion"
    ILLEGAL_PARKING = "illegal_parking"
    SPEEDING = "speeding"
    TRAFFIC_LIGHT_VIOLATION = "traffic_light_violation"
    LANE_VIOLATION = "lane_violation"
    UNUSUAL_ACTIVITY = "unusual_activity"
    # DB incident types
    COLLISION = "collision"
    STALLED_VEHICLE = "stalled_vehicle"
    HAZARD = "hazard"
    WEATHER_RELATED = "weather_related"
    INFRASTRUCTURE_DAMAGE = "infrastructure_damage"
    OTHER = "other"


class DetectionResponse(BaseModel):
    """
    Detection from a single frame.

    Attributes:
        id: Unique detection identifier
        session_id: Associated session ID
        frame_number: Frame number in video
        timestamp: Detection timestamp
        class_name: Detected object class
        confidence: Detection confidence score (0-1)
        bbox: Bounding box [x1, y1, x2, y2]
        center: Center point [x, y]
        area: Detection area in pixels
        track_id: Multi-object tracking ID (if available)
    """

    id: str = Field(..., description="Unique detection identifier")
    session_id: str = Field(..., description="Associated session ID")
    frame_number: int = Field(..., ge=0, description="Frame number in video")
    timestamp: datetime = Field(..., description="Detection timestamp")
    class_name: DetectionClass = Field(..., description="Detected object class")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    bbox: List[float] = Field(
        ..., min_length=4, max_length=4, description="Bounding box [x1, y1, x2, y2]"
    )
    center: List[float] = Field(
        ..., min_length=2, max_length=2, description="Center coordinates [x, y]"
    )
    area: float = Field(..., ge=0, description="Detection area in pixels")
    track_id: Optional[str] = Field(None, description="Multi-object tracking ID")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "det_12345",
                    "session_id": "sess_abc123",
                    "frame_number": 150,
                    "timestamp": "2026-03-31T10:30:45.123Z",
                    "class_name": "car",
                    "confidence": 0.95,
                    "bbox": [100, 150, 300, 400],
                    "center": [200, 275],
                    "area": 37500,
                    "track_id": 1,
                }
            ]
        }
    }


class IncidentResponse(BaseModel):
    """
    Detected traffic incident.

    Attributes:
        id: Unique incident identifier
        session_id: Associated session ID
        incident_type: Type of incident
        severity: Severity level
        description: Human-readable description
        detected_at: Detection timestamp
        confidence: Confidence score for incident
        related_detections: List of detection IDs
        location: Location information (if available)
        metadata: Additional incident metadata
    """

    id: str = Field(..., description="Unique incident identifier")
    session_id: str = Field(..., description="Associated session ID")
    incident_type: IncidentType = Field(..., description="Type of incident")
    severity: IncidentSeverity = Field(..., description="Severity level")
    description: Optional[str] = Field(None, max_length=1000, description="Description")
    detected_at: datetime = Field(..., description="Detection timestamp")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Confidence score")
    related_detections: List[Any] = Field(
        default_factory=list, description="Related detection IDs"
    )
    location: Optional[Any] = Field(None, description="Location coordinates")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "inc_12345",
                    "session_id": "sess_abc123",
                    "incident_type": "congestion",
                    "severity": "high",
                    "description": "Heavy traffic congestion detected in lane 2",
                    "detected_at": "2026-03-31T10:35:00.000Z",
                    "confidence": 0.88,
                    "related_detections": ["det_12345", "det_12346", "det_12347"],
                    "location": {"x": 200, "y": 300},
                    "metadata": {"affected_lanes": [2, 3], "vehicles_count": 45},
                }
            ]
        }
    }


class SessionResponse(BaseModel):
    """
    Traffic monitoring session.

    Attributes:
        id: Unique session identifier
        name: Session name
        type: Session type (upload or stream)
        status: Current session status
        created_at: Creation timestamp
        updated_at: Last update timestamp
        source: Source information (file path or stream URL)
        frame_count: Total frames processed
        duration_seconds: Total processing duration
        vehicle_count: Total vehicles detected
    """

    id: str = Field(..., description="Unique session identifier")
    name: str = Field(..., max_length=255, description="Session name")
    type: str = Field(..., description="Session type (upload or stream)")
    status: str = Field(
        ..., description="Session status (processing, completed, failed, stopped)"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    source: Optional[str] = Field(None, description="Source file path or stream URL")
    frame_count: int = Field(default=0, ge=0, description="Total frames processed")
    duration_seconds: float = Field(default=0.0, ge=0.0, description="Duration")
    vehicle_count: int = Field(default=0, ge=0, description="Total vehicles detected")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "sess_abc123",
                    "name": "Highway A1 Morning",
                    "type": "upload",
                    "status": "completed",
                    "created_at": "2026-03-31T08:00:00.000Z",
                    "updated_at": "2026-03-31T10:45:30.000Z",
                    "source": "/uploads/highway_a1.mp4",
                    "frame_count": 9000,
                    "duration_seconds": 300.0,
                    "vehicle_count": 523,
                }
            ]
        }
    }


class VehicleCountResponse(BaseModel):
    """
    Aggregated vehicle counts.

    Attributes:
        session_id: Associated session ID
        total_vehicles: Total vehicle detections
        unique_vehicles: Estimated unique vehicles
        by_class: Vehicle counts by class
        by_time_window: Vehicles counts in time windows
        peak_time: Peak detection timestamp
        peak_count: Peak vehicle count
    """

    session_id: str = Field(..., description="Associated session ID")
    total_vehicles: int = Field(..., ge=0, description="Total detections")
    unique_vehicles: int = Field(..., ge=0, description="Estimated unique vehicles")
    by_class: Dict[str, int] = Field(
        default_factory=dict, description="Counts by class"
    )
    by_time_window: Dict[str, int] = Field(
        default_factory=dict, description="Counts in time windows"
    )
    peak_time: Optional[datetime] = Field(None, description="Peak detection time")
    peak_count: int = Field(default=0, ge=0, description="Peak count")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "session_id": "sess_abc123",
                    "total_vehicles": 523,
                    "unique_vehicles": 287,
                    "by_class": {
                        "car": 412,
                        "truck": 78,
                        "bus": 23,
                        "motorcycle": 10,
                    },
                    "by_time_window": {
                        "08:00-08:15": 125,
                        "08:15-08:30": 142,
                        "08:30-08:45": 156,
                    },
                    "peak_time": "2026-03-31T08:30:00.000Z",
                    "peak_count": 156,
                }
            ]
        }
    }


class TrafficFlowResponse(BaseModel):
    """
    Traffic flow analysis.

    Attributes:
        session_id: Associated session ID
        average_speed: Average vehicle speed (km/h)
        congestion_level: Congestion level (0-1)
        flow_rate: Vehicles per minute
        density: Vehicle density (vehicles per 100m)
    """

    session_id: str = Field(..., description="Associated session ID")
    average_speed: float = Field(..., ge=0.0, description="Average speed in km/h")
    congestion_level: float = Field(
        ..., ge=0.0, le=1.0, description="Congestion level"
    )
    flow_rate: float = Field(..., ge=0.0, description="Vehicles per minute")
    density: float = Field(..., ge=0.0, description="Vehicle density")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "session_id": "sess_abc123",
                    "average_speed": 45.5,
                    "congestion_level": 0.75,
                    "flow_rate": 12.5,
                    "density": 35.2,
                }
            ]
        }
    }


class ChatRequest(BaseModel):
    """
    Chat message request.

    Attributes:
        session_id: Associated session ID
        message: User message
        include_context: Whether to include session context
    """

    session_id: str = Field(..., description="Associated session ID")
    message: str = Field(..., min_length=1, max_length=2000, description="User message")
    include_context: bool = Field(
        default=True, description="Include session context in response"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "session_id": "sess_abc123",
                    "message": "What was the peak traffic time?",
                    "include_context": True,
                }
            ]
        }
    }


class ChatResponse(BaseModel):
    """
    Chat message response from agent.

    Attributes:
        session_id: Associated session ID
        message: Agent response
        sources: Referenced data sources
        confidence: Response confidence
    """

    session_id: str = Field(..., description="Associated session ID")
    message: str = Field(..., description="Agent response message")
    sources: List[str] = Field(default_factory=list, description="Data sources")
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Response confidence"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "session_id": "sess_abc123",
                    "message": "The peak traffic time was at 08:30 AM with 156 vehicles detected.",
                    "sources": ["vehicle_counts", "detection_data"],
                    "confidence": 0.95,
                }
            ]
        }
    }


class ReportRequest(BaseModel):
    """
    Report generation request.

    Attributes:
        session_id: Associated session ID
        report_type: Type of report to generate
        include_detections: Include detection details
        include_incidents: Include incident analysis
        include_charts: Include visualizations
    """

    session_id: str = Field(..., description="Associated session ID")
    report_type: str = Field(
        default="summary", description="Report type (summary, detailed, executive)"
    )
    include_detections: bool = Field(default=True, description="Include detections")
    include_incidents: bool = Field(default=True, description="Include incidents")
    include_charts: bool = Field(default=True, description="Include charts")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "session_id": "sess_abc123",
                    "report_type": "detailed",
                    "include_detections": True,
                    "include_incidents": True,
                    "include_charts": True,
                }
            ]
        }
    }


class ReportResponse(BaseModel):
    """
    Generated report.

    Attributes:
        id: Report identifier
        session_id: Associated session ID
        report_type: Report type
        title: Report title
        summary: Executive summary
        generated_at: Generation timestamp
        download_url: URL to download report
    """

    id: str = Field(..., description="Report identifier")
    session_id: str = Field(..., description="Associated session ID")
    report_type: str = Field(..., description="Report type")
    title: str = Field(..., description="Report title")
    summary: str = Field(..., description="Executive summary")
    generated_at: datetime = Field(..., description="Generation timestamp")
    download_url: str = Field(..., description="Download URL")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "rep_12345",
                    "session_id": "sess_abc123",
                    "report_type": "detailed",
                    "title": "Highway A1 Traffic Analysis - March 31, 2026",
                    "summary": "Analysis of 9000 frames showing peak traffic at 08:30 AM.",
                    "generated_at": "2026-03-31T11:00:00.000Z",
                    "download_url": "/api/reports/rep_12345/download",
                }
            ]
        }
    }


class UploadResponse(BaseModel):
    """
    File upload response.

    Attributes:
        session_id: Created session identifier
        filename: Uploaded filename
        file_size: File size in bytes
        status: Processing status
        message: Status message
    """

    session_id: str = Field(..., description="Created session identifier")
    filename: str = Field(..., description="Uploaded filename")
    file_size: int = Field(..., ge=0, description="File size in bytes")
    status: str = Field(..., description="Processing status")
    message: str = Field(..., description="Status message")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "session_id": "sess_abc123",
                    "filename": "highway_a1.mp4",
                    "file_size": 1073741824,
                    "status": "processing",
                    "message": "File uploaded successfully, processing started",
                }
            ]
        }
    }


class StreamStartRequest(BaseModel):
    """
    Request to start streaming from RTSP or webcam.

    Attributes:
        name: Session name
        stream_url: RTSP stream URL or 'webcam' for default device
        fps: Target frames per second
    """

    name: str = Field(..., min_length=1, max_length=255, description="Session name")
    stream_url: str = Field(
        ..., description="RTSP URL or 'webcam' for device 0"
    )
    fps: int = Field(default=30, ge=1, le=120, description="Target FPS")

    @field_validator("stream_url")
    @classmethod
    def validate_stream_url(cls, v: str) -> str:
        """Validate stream URL format."""
        if v != "webcam" and not v.startswith("rtsp://") and not v.startswith("http"):
            raise ValueError(
                "stream_url must be 'webcam' or start with 'rtsp://' or 'http'"
            )
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Main Intersection Camera",
                    "stream_url": "rtsp://camera.example.com/stream",
                    "fps": 30,
                }
            ]
        }
    }


class SessionStatsResponse(BaseModel):
    """
    Session statistics.

    Attributes:
        session_id: Associated session ID
        total_frames: Total frames processed
        processing_fps: Processing frames per second
        detections_count: Total detections
        incidents_count: Total incidents
        avg_detection_confidence: Average confidence
    """

    session_id: str = Field(..., description="Associated session ID")
    total_frames: int = Field(..., ge=0, description="Total frames")
    processing_fps: float = Field(..., ge=0.0, description="Processing FPS")
    detections_count: int = Field(..., ge=0, description="Total detections")
    incidents_count: int = Field(..., ge=0, description="Total incidents")
    avg_detection_confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Average confidence"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "session_id": "sess_abc123",
                    "total_frames": 9000,
                    "processing_fps": 30.0,
                    "detections_count": 2500,
                    "incidents_count": 12,
                    "avg_detection_confidence": 0.87,
                }
            ]
        }
    }


class HealthResponse(BaseModel):
    """
    Health check response.

    Attributes:
        status: Overall health status
        timestamp: Health check timestamp
        components: Component-level status
        version: API version
    """

    status: str = Field(..., description="Overall status (healthy, degraded, unhealthy)")
    timestamp: datetime = Field(..., description="Check timestamp")
    components: Dict[str, str] = Field(
        default_factory=dict, description="Component status"
    )
    version: str = Field(..., description="API version")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "healthy",
                    "timestamp": "2026-03-31T11:00:00.000Z",
                    "components": {
                        "database": "healthy",
                        "redis": "healthy",
                        "models": "loaded",
                    },
                    "version": "1.0.0",
                }
            ]
        }
    }


# Generic pagination response
T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Paginated API response.

    Attributes:
        items: Page items
        total: Total item count
        page: Current page number
        page_size: Items per page
        total_pages: Total page count
    """

    items: List[T] = Field(..., description="Page items")
    total: int = Field(..., ge=0, description="Total count")
    page: int = Field(..., ge=1, description="Current page")
    page_size: int = Field(..., ge=1, description="Items per page")
    total_pages: int = Field(..., ge=0, description="Total pages")

    @property
    def has_next(self) -> bool:
        """Check if there's a next page."""
        return self.page < self.total_pages

    @property
    def has_previous(self) -> bool:
        """Check if there's a previous page."""
        return self.page > 1
