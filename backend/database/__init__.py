"""
Database layer for Multimodal Traffic Intelligence Platform.

Exports the primary database components including connection management,
ORM models, and query helpers.
"""

from .connection import (
    AsyncSessionFactory,
    get_db,
    init_db,
    health_check,
    close_db,
)
from .models import (
    DetectionEvent,
    IncidentEvent,
    TrafficSession,
    TrafficReport,
    VehicleCount,
    Base,
)
from .queries import (
    get_detection_summary,
    get_vehicle_counts,
    get_incidents,
    get_traffic_flow,
    search_events,
    get_session_stats,
    create_session,
    count_active_sessions,
    get_detections,
    update_session_status,
    create_report,
    check_health,
    batch_write_detections,
    batch_write_incidents,
)

__all__ = [
    "AsyncSessionFactory",
    "get_db",
    "init_db",
    "health_check",
    "close_db",
    "DetectionEvent",
    "IncidentEvent",
    "TrafficSession",
    "TrafficReport",
    "VehicleCount",
    "Base",
    "get_detection_summary",
    "get_vehicle_counts",
    "get_incidents",
    "get_traffic_flow",
    "search_events",
    "get_session_stats",
    "create_session",
    "count_active_sessions",
    "get_detections",
    "update_session_status",
    "create_report",
    "check_health",
    "batch_write_detections",
    "batch_write_incidents",
]
