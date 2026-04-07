"""
SQLAlchemy ORM models for the Multimodal Traffic Intelligence Platform.

Defines the database schema for detection events, incidents, traffic sessions,
reports, and vehicle counts with proper relationships and constraints.
"""

from datetime import datetime
from typing import Optional, List
from decimal import Decimal

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Boolean,
    Text,
    JSON,
    ForeignKey,
    Index,
    UniqueConstraint,
    Enum,
    DECIMAL,
    CheckConstraint,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()


class SourceType(str, enum.Enum):
    """Enumeration of traffic data sources."""

    VIDEO_STREAM = "video_stream"
    VIDEO_FILE = "video_file"
    CAMERA_FEED = "camera_feed"
    RTSP = "rtsp"
    HTTP_STREAM = "http_stream"
    FILE_UPLOAD = "file_upload"
    SIMULATOR = "simulator"
    UPLOAD = "upload"
    STREAM = "stream"
    DEMO = "demo"


class VehicleType(str, enum.Enum):
    """Enumeration of vehicle types."""

    CAR = "car"
    TRUCK = "truck"
    BUS = "bus"
    MOTORCYCLE = "motorcycle"
    BICYCLE = "bicycle"
    PEDESTRIAN = "pedestrian"
    VAN = "van"
    UNKNOWN = "unknown"


class IncidentType(str, enum.Enum):
    """Enumeration of incident types."""

    COLLISION = "collision"
    CONGESTION = "congestion"
    STALLED_VEHICLE = "stalled_vehicle"
    HAZARD = "hazard"
    UNUSUAL_ACTIVITY = "unusual_activity"
    WEATHER_RELATED = "weather_related"
    INFRASTRUCTURE_DAMAGE = "infrastructure_damage"
    OTHER = "other"


class SeverityLevel(str, enum.Enum):
    """Enumeration of incident severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SessionStatus(str, enum.Enum):
    """Enumeration of traffic session status."""

    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class TrafficSession(Base):
    """
    Represents a traffic monitoring session.

    A session is a continuous monitoring period from a single source
    (video file, live stream, etc.).
    """

    __allow_unmapped__ = True
    __tablename__ = "traffic_sessions"

    id = Column(String(36), primary_key=True, doc="Unique session identifier (UUID)")
    start_time = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        doc="Session start timestamp",
    )
    end_time = Column(
        DateTime(timezone=True),
        nullable=True,
        doc="Session end timestamp (null if ongoing)",
    )
    source_type = Column(
        Enum(SourceType),
        nullable=False,
        doc="Type of data source",
    )
    source_url = Column(
        String(500),
        nullable=True,
        doc="URL or path to the source data",
    )
    status = Column(
        Enum(SessionStatus),
        nullable=False,
        default=SessionStatus.ACTIVE,
        doc="Current session status",
    )
    metadata_json = Column(
        JSON,
        nullable=True,
        doc="Additional session metadata (resolution, fps, codec, etc.)",
    )

    # Relationships
    detection_events: List["DetectionEvent"] = relationship(
        "DetectionEvent",
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="select",
    )
    incident_events: List["IncidentEvent"] = relationship(
        "IncidentEvent",
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="select",
    )
    vehicle_counts: List["VehicleCount"] = relationship(
        "VehicleCount",
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="select",
    )
    reports: List["TrafficReport"] = relationship(
        "TrafficReport",
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="select",
    )

    __table_args__ = (
        Index("ix_traffic_sessions_start_time", "start_time"),
        Index("ix_traffic_sessions_status", "status"),
        CheckConstraint("end_time IS NULL OR end_time > start_time"),
    )

    def __repr__(self) -> str:
        return (
            f"TrafficSession(id={self.id}, start_time={self.start_time}, "
            f"status={self.status})"
        )


class DetectionEvent(Base):
    """
    Represents a single vehicle detection event from object detection model.

    Contains bounding box coordinates, confidence score, vehicle type,
    and tracking information.
    """

    __tablename__ = "detection_events"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        doc="Unique event identifier",
    )
    timestamp = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        doc="Detection timestamp",
    )
    session_id = Column(
        String(36),
        ForeignKey("traffic_sessions.id", ondelete="CASCADE"),
        nullable=False,
        doc="Session identifier",
    )
    frame_number = Column(
        Integer,
        nullable=False,
        doc="Frame number in the video sequence",
    )
    vehicle_type = Column(
        Enum(VehicleType),
        nullable=False,
        doc="Type of detected vehicle",
    )
    confidence = Column(
        Float,
        nullable=False,
        doc="Detection confidence score (0.0-1.0)",
    )
    track_id = Column(
        String(36),
        nullable=True,
        doc="Vehicle track identifier (for multi-frame tracking)",
    )
    # Bounding box in normalized coordinates (0.0-1.0)
    bbox_x = Column(
        DECIMAL(5, 4),
        nullable=False,
        doc="Bounding box top-left X coordinate (normalized 0.0-1.0)",
    )
    bbox_y = Column(
        DECIMAL(5, 4),
        nullable=False,
        doc="Bounding box top-left Y coordinate (normalized 0.0-1.0)",
    )
    bbox_w = Column(
        DECIMAL(5, 4),
        nullable=False,
        doc="Bounding box width (normalized 0.0-1.0)",
    )
    bbox_h = Column(
        DECIMAL(5, 4),
        nullable=False,
        doc="Bounding box height (normalized 0.0-1.0)",
    )
    speed_estimate = Column(
        Float,
        nullable=True,
        doc="Estimated vehicle speed in km/h",
    )
    direction = Column(
        String(50),
        nullable=True,
        doc="Movement direction (e.g., 'north', 'southeast', angle)",
    )

    # Relationships
    session = relationship(
        "TrafficSession",
        back_populates="detection_events",
        lazy="joined",
    )

    __table_args__ = (
        Index("ix_detection_events_session_id", "session_id"),
        Index("ix_detection_events_timestamp", "timestamp"),
        Index("ix_detection_events_track_id", "track_id"),
        Index("ix_detection_events_session_timestamp", "session_id", "timestamp"),
        Index("ix_detection_events_vehicle_type", "vehicle_type"),
        CheckConstraint("confidence >= 0.0 AND confidence <= 1.0"),
        CheckConstraint("bbox_x >= 0.0 AND bbox_x <= 1.0"),
        CheckConstraint("bbox_y >= 0.0 AND bbox_y <= 1.0"),
        CheckConstraint("bbox_w >= 0.0 AND bbox_w <= 1.0"),
        CheckConstraint("bbox_h >= 0.0 AND bbox_h <= 1.0"),
    )

    def __repr__(self) -> str:
        return (
            f"DetectionEvent(id={self.id}, vehicle_type={self.vehicle_type}, "
            f"confidence={self.confidence}, track_id={self.track_id})"
        )


class IncidentEvent(Base):
    """
    Represents a traffic incident detected in the scene.

    Incidents are higher-level events (collisions, congestion, hazards)
    that may involve multiple detection events.
    """

    __tablename__ = "incident_events"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        doc="Unique incident identifier",
    )
    timestamp = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        doc="Incident detection timestamp",
    )
    session_id = Column(
        String(36),
        ForeignKey("traffic_sessions.id", ondelete="CASCADE"),
        nullable=False,
        doc="Session identifier",
    )
    incident_type = Column(
        Enum(IncidentType),
        nullable=False,
        doc="Type of incident",
    )
    severity = Column(
        Enum(SeverityLevel),
        nullable=False,
        default=SeverityLevel.MEDIUM,
        doc="Incident severity level",
    )
    location_description = Column(
        String(256),
        nullable=True,
        doc="Human-readable location description",
    )
    bbox = Column(
        JSON,
        nullable=True,
        doc="Bounding box of incident area (same format as detection events)",
    )
    related_track_ids = Column(
        JSON,
        nullable=True,
        doc="List of track IDs involved in the incident",
    )
    resolved = Column(
        Boolean,
        nullable=False,
        default=False,
        doc="Whether the incident has been resolved",
    )
    resolved_at = Column(
        DateTime(timezone=True),
        nullable=True,
        doc="Incident resolution timestamp",
    )
    description = Column(
        Text,
        nullable=True,
        doc="Detailed incident description",
    )

    # Relationships
    session = relationship(
        "TrafficSession",
        back_populates="incident_events",
        lazy="joined",
    )

    __table_args__ = (
        Index("ix_incident_events_session_id", "session_id"),
        Index("ix_incident_events_timestamp", "timestamp"),
        Index("ix_incident_events_incident_type", "incident_type"),
        Index("ix_incident_events_severity", "severity"),
        Index("ix_incident_events_resolved", "resolved"),
        Index("ix_incident_events_session_timestamp", "session_id", "timestamp"),
        CheckConstraint("resolved_at IS NULL OR resolved_at > timestamp"),
    )

    def __repr__(self) -> str:
        return (
            f"IncidentEvent(id={self.id}, incident_type={self.incident_type}, "
            f"severity={self.severity}, resolved={self.resolved})"
        )


class VehicleCount(Base):
    """
    Aggregated vehicle count statistics for a time interval.

    Provides summarized traffic statistics at regular intervals
    for performance and reporting purposes.
    """

    __tablename__ = "vehicle_counts"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        doc="Unique record identifier",
    )
    session_id = Column(
        String(36),
        ForeignKey("traffic_sessions.id", ondelete="CASCADE"),
        nullable=False,
        doc="Session identifier",
    )
    timestamp = Column(
        DateTime(timezone=True),
        nullable=False,
        doc="Time period start timestamp",
    )
    interval_seconds = Column(
        Integer,
        nullable=False,
        default=60,
        doc="Duration of the counting interval in seconds",
    )
    vehicle_type = Column(
        Enum(VehicleType),
        nullable=False,
        doc="Type of vehicle being counted",
    )
    count = Column(
        Integer,
        nullable=False,
        default=0,
        doc="Number of vehicles detected in this interval",
    )
    direction = Column(
        String(50),
        nullable=True,
        doc="Direction filter (optional)",
    )

    # Relationships
    session = relationship(
        "TrafficSession",
        back_populates="vehicle_counts",
        lazy="joined",
    )

    __table_args__ = (
        Index("ix_vehicle_counts_session_id", "session_id"),
        Index("ix_vehicle_counts_timestamp", "timestamp"),
        Index("ix_vehicle_counts_vehicle_type", "vehicle_type"),
        Index("ix_vehicle_counts_session_timestamp", "session_id", "timestamp"),
        UniqueConstraint(
            "session_id",
            "timestamp",
            "vehicle_type",
            "direction",
            name="uq_vehicle_counts_session_type_direction",
        ),
        CheckConstraint("count >= 0"),
        CheckConstraint("interval_seconds > 0"),
    )

    def __repr__(self) -> str:
        return (
            f"VehicleCount(session_id={self.session_id}, "
            f"vehicle_type={self.vehicle_type}, count={self.count})"
        )


class TrafficReport(Base):
    """
    Generated traffic analysis report for a session.

    Contains summaries, insights, and analytics generated from
    detection and incident data.
    """

    __tablename__ = "traffic_reports"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        doc="Unique report identifier",
    )
    session_id = Column(
        String(36),
        ForeignKey("traffic_sessions.id", ondelete="CASCADE"),
        nullable=False,
        doc="Session identifier",
    )
    generated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        doc="Report generation timestamp",
    )
    report_type = Column(
        String(50),
        nullable=False,
        doc="Type of report (e.g., 'summary', 'detailed', 'incident_analysis')",
    )
    content = Column(
        JSON,
        nullable=False,
        doc="Report content (flexible JSON structure)",
    )
    query_text = Column(
        Text,
        nullable=True,
        doc="Original query or parameters used to generate report",
    )

    # Relationships
    session = relationship(
        "TrafficSession",
        back_populates="reports",
        lazy="joined",
    )

    __table_args__ = (
        Index("ix_traffic_reports_session_id", "session_id"),
        Index("ix_traffic_reports_generated_at", "generated_at"),
        Index("ix_traffic_reports_report_type", "report_type"),
        Index("ix_traffic_reports_session_type", "session_id", "report_type"),
    )

    def __repr__(self) -> str:
        return (
            f"TrafficReport(id={self.id}, session_id={self.session_id}, "
            f"report_type={self.report_type})"
        )
