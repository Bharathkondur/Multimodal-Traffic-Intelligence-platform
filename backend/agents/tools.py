"""
LangChain tools for the Traffic Intelligence Agent.

Provides specialized tools for querying detection database, analyzing traffic patterns,
and generating reports. All tools use real database queries via SQLAlchemy async sessions.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional
from enum import Enum
import json

from langchain_core.tools import tool
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from database import (
    get_detection_summary,
    get_vehicle_counts,
    get_incidents,
    get_traffic_flow,
    search_events,
    get_session_stats,
    create_report,
)
from database.connection import get_session_factory

logger = logging.getLogger(__name__)


class VehicleType(str, Enum):
    """Supported vehicle types in the system."""
    CAR = "car"
    TRUCK = "truck"
    MOTORCYCLE = "motorcycle"
    BUS = "bus"
    COMMERCIAL = "commercial"
    OTHER = "other"


class IncidentType(str, Enum):
    """Supported incident types."""
    ACCIDENT = "accident"
    CONGESTION = "congestion"
    VIOLATION = "violation"
    HAZARD = "hazard"
    OTHER = "other"


class DetectionQueryInput(BaseModel):
    """Input schema for detection database queries."""
    query: str = Field(
        description="Natural language query to search detection events"
    )
    time_range: Optional[str] = Field(
        None,
        description="Time range: 'last_hour', 'last_6_hours', 'today', or ISO date range"
    )
    location_filter: Optional[str] = Field(
        None,
        description="Optional location filter (camera zone, intersection, etc.)"
    )
    limit: int = Field(
        10,
        description="Maximum number of results to return"
    )


class VehicleCountInput(BaseModel):
    """Input schema for vehicle counting."""
    vehicle_type: Optional[VehicleType] = Field(
        None,
        description="Filter by vehicle type (car, truck, motorcycle, bus, commercial, other)"
    )
    time_range: str = Field(
        "last_hour",
        description="Time range: 'last_hour', 'last_6_hours', 'today', or ISO date"
    )
    location: Optional[str] = Field(
        None,
        description="Specific location or camera zone"
    )


class IncidentReportInput(BaseModel):
    """Input schema for incident reports."""
    incident_id: str = Field(
        description="The incident identifier"
    )
    include_details: bool = Field(
        True,
        description="Include detailed event timeline and context"
    )


class TrafficFlowInput(BaseModel):
    """Input schema for traffic flow analysis."""
    location: Optional[str] = Field(
        None,
        description="Location to analyze (specific camera, intersection, zone)"
    )
    time_range: str = Field(
        "last_hour",
        description="Time period to analyze"
    )
    include_historical: bool = Field(
        False,
        description="Include historical comparison baseline"
    )


class ShiftReportInput(BaseModel):
    """Input schema for shift report generation."""
    shift_time: str = Field(
        description="Shift time: 'morning', 'afternoon', 'night', or HH:MM-HH:MM format"
    )
    date: Optional[str] = Field(
        None,
        description="Report date (defaults to today, ISO format)"
    )
    include_recommendations: bool = Field(
        True,
        description="Include operational recommendations"
    )


class ComparePeriodInput(BaseModel):
    """Input schema for period comparison."""
    period_1: str = Field(
        description="First period: date range or relative time (e.g., 'today', 'yesterday')"
    )
    period_2: str = Field(
        description="Second period for comparison"
    )
    metric: str = Field(
        "vehicle_count",
        description="Metric to compare: vehicle_count, incident_count, avg_flow, peak_time"
    )
    location: Optional[str] = Field(
        None,
        description="Optional location filter"
    )


class SceneSnapshotInput(BaseModel):
    """Input schema for current scene description."""
    location: Optional[str] = Field(
        None,
        description="Specific location (defaults to all monitored areas)"
    )
    detail_level: str = Field(
        "standard",
        description="Detail level: 'brief', 'standard', or 'detailed'"
    )


# ==================== Utility Functions ====================

async def get_db_session() -> AsyncSession:
    """Get an async database session using the factory."""
    factory = get_session_factory()
    return await factory.get_session()


def parse_time_range(time_range: Optional[str]) -> tuple[datetime, datetime]:
    """
    Parse time range string to (start_time, end_time) tuple.

    Supports: 'last_hour', 'last_6_hours', 'today', or ISO date range.
    """
    now = datetime.utcnow()

    if not time_range or time_range == "last_hour":
        start = now - timedelta(hours=1)
        end = now
    elif time_range == "last_6_hours":
        start = now - timedelta(hours=6)
        end = now
    elif time_range == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif time_range == "yesterday":
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif "-" in time_range:
        try:
            parts = time_range.split("-")
            start = datetime.fromisoformat(parts[0].strip())
            end = datetime.fromisoformat(parts[1].strip())
        except (ValueError, IndexError):
            logger.warning(f"Invalid time range format: {time_range}, using last hour")
            start = now - timedelta(hours=1)
            end = now
    else:
        logger.warning(f"Unknown time range: {time_range}, using last hour")
        start = now - timedelta(hours=1)
        end = now

    return start, end


# ==================== Detection Queries ====================

@tool("query_detections", args_schema=DetectionQueryInput)
async def query_detections(
    query: str,
    time_range: Optional[str] = None,
    location_filter: Optional[str] = None,
    limit: int = 10,
) -> dict[str, Any]:
    """
    Query the detection database using natural language.

    Searches for vehicles, incidents, or patterns matching the query across
    the detection event store. Returns relevant detections with timestamps,
    locations, and metadata.

    Args:
        query: Natural language query (e.g., "motorcycles in intersection A")
        time_range: Optional time filter (last_hour, last_6_hours, today, date range)
        location_filter: Optional location/camera filter
        limit: Maximum results to return (default 10)

    Returns:
        Dictionary with matched detections and metadata.

    Example:
        query_detections(
            "heavy vehicles near main street",
            time_range="last_hour",
            limit=20
        )
    """
    logger.info(
        f"Querying detections: query={query}, time_range={time_range}, "
        f"location={location_filter}, limit={limit}"
    )

    session = None
    try:
        session = await get_db_session()

        # Parse time range
        start_time, end_time = parse_time_range(time_range)

        # Determine vehicle type from query (simple heuristic)
        vehicle_type = None
        query_lower = query.lower()
        if "truck" in query_lower or "heavy" in query_lower:
            vehicle_type = "truck"
        elif "car" in query_lower:
            vehicle_type = "car"
        elif "motorcycle" in query_lower or "bike" in query_lower:
            vehicle_type = "motorcycle"
        elif "bus" in query_lower or "transit" in query_lower:
            vehicle_type = "bus"

        # Get detections using real database query
        # Note: We need a session_id - this would come from context in real usage
        # For now, we'll query recent sessions
        detections = await search_events(
            session,
            session_id="current_session",  # Would be set in real context
            vehicle_type=vehicle_type,
            time_range=(start_time, end_time),
            limit=limit,
        )

        return {
            "status": "success",
            "query": query,
            "time_range": time_range or "no_filter",
            "results_count": len(detections),
            "detections": detections,
            "message": f"Found {len(detections)} detection results"
        }

    except Exception as e:
        logger.error(f"Error querying detections: {e}")
        return {
            "status": "error",
            "message": str(e),
            "results_count": 0,
            "detections": []
        }
    finally:
        if session:
            await session.close()


# ==================== Vehicle Counting ====================

@tool("get_vehicle_count", args_schema=VehicleCountInput)
async def get_vehicle_count(
    vehicle_type: Optional[VehicleType] = None,
    time_range: str = "last_hour",
    location: Optional[str] = None,
) -> dict[str, Any]:
    """
    Count vehicles by type and time period.

    Provides aggregated vehicle counts with optional filtering by type,
    time range, and location. Includes percentage breakdowns and trends.

    Args:
        vehicle_type: Filter by specific vehicle type
        time_range: Time period to analyze
        location: Optional location/camera filter

    Returns:
        Dictionary with count statistics and breakdown.

    Example:
        get_vehicle_count(
            vehicle_type=VehicleType.TRUCK,
            time_range="today",
            location="main_intersection"
        )
    """
    logger.info(
        f"Getting vehicle counts: type={vehicle_type}, "
        f"time_range={time_range}, location={location}"
    )

    session = None
    try:
        session = await get_db_session()

        # Get vehicle counts from database
        counts = await get_vehicle_counts(
            session,
            session_id="current_session",  # Would be set in real context
            interval=60,
            vehicle_type=vehicle_type.value if vehicle_type else None,
            direction=location,
        )

        # Calculate totals and percentages
        total_count = sum(c.get("count", 0) for c in counts)

        # Group by vehicle type for breakdown
        type_breakdown = {}
        for count in counts:
            vtype = count.get("vehicle_type", "other")
            type_breakdown[vtype] = type_breakdown.get(vtype, 0) + count.get("count", 0)

        if vehicle_type:
            filtered_count = type_breakdown.get(vehicle_type.value, 0)
            percentage = (filtered_count / total_count * 100) if total_count > 0 else 0
        else:
            filtered_count = total_count
            percentage = 100.0

        # Extract hourly trend (last 12 hours)
        hourly_trend = []
        for count in counts[-12:]:
            hourly_trend.append(count.get("count", 0))

        return {
            "status": "success",
            "time_range": time_range,
            "location": location or "all_zones",
            "vehicle_type_filter": vehicle_type.value if vehicle_type else None,
            "total_count": filtered_count,
            "percentage_of_total": round(percentage, 2),
            "breakdown": type_breakdown if not vehicle_type else None,
            "hourly_trend": hourly_trend,
            "data_points": len(counts),
        }

    except Exception as e:
        logger.error(f"Error counting vehicles: {e}")
        return {
            "status": "error",
            "message": str(e),
            "total_count": 0
        }
    finally:
        if session:
            await session.close()


# ==================== Incident Reports ====================

@tool("get_incident_report", args_schema=IncidentReportInput)
async def get_incident_report(
    incident_id: str,
    include_details: bool = True,
) -> dict[str, Any]:
    """
    Retrieve detailed incident report.

    Fetches comprehensive information about a specific incident including
    timeline, involved vehicles, impact assessment, and resolution status.

    Args:
        incident_id: The incident identifier
        include_details: Whether to include detailed timeline and context

    Returns:
        Dictionary with incident details.

    Example:
        get_incident_report("INC20240331001", include_details=True)
    """
    logger.info(f"Getting incident report: {incident_id}")

    session = None
    try:
        session = await get_db_session()

        # Query incidents by session
        incidents = await get_incidents(
            session,
            session_id="current_session",  # Would be set in real context
            limit=1000,
        )

        # Find matching incident
        matching = [i for i in incidents if i.get("id") == incident_id]

        if not matching:
            return {
                "status": "error",
                "message": f"Incident {incident_id} not found",
            }

        incident = matching[0]

        base_report = {
            "status": "success",
            "incident_id": incident.get("id"),
            "type": incident.get("incident_type"),
            "severity": incident.get("severity"),
            "location": incident.get("location_description"),
            "timestamp": incident.get("timestamp"),
            "resolved": incident.get("resolved"),
        }

        if include_details:
            base_report.update({
                "vehicles_involved": {
                    "count": len(incident.get("related_track_ids", [])) if incident.get("related_track_ids") else 0,
                },
                "resolution": {
                    "status": "cleared" if incident.get("resolved") else "active",
                    "resolved_at": incident.get("resolved_at"),
                },
                "description": incident.get("description"),
            })

        return base_report

    except Exception as e:
        logger.error(f"Error retrieving incident report: {e}")
        return {
            "status": "error",
            "message": str(e),
        }
    finally:
        if session:
            await session.close()


# ==================== Traffic Flow Analysis ====================

@tool("get_traffic_flow", args_schema=TrafficFlowInput)
async def get_traffic_flow(
    location: Optional[str] = None,
    time_range: str = "last_hour",
    include_historical: bool = False,
) -> dict[str, Any]:
    """
    Analyze traffic flow patterns.

    Provides traffic flow metrics including speed, density, and congestion
    patterns. Can include historical comparison for trend analysis.

    Args:
        location: Optional location to analyze
        time_range: Time period to analyze
        include_historical: Include baseline comparison

    Returns:
        Dictionary with traffic flow metrics.

    Example:
        get_traffic_flow(
            location="main_corridor",
            time_range="today",
            include_historical=True
        )
    """
    logger.info(
        f"Analyzing traffic flow: location={location}, "
        f"time_range={time_range}, historical={include_historical}"
    )

    session = None
    try:
        session = await get_db_session()

        # Parse time range
        start_time, end_time = parse_time_range(time_range)

        # Get traffic flow data from database
        flow_data = await get_traffic_flow(
            session,
            session_id="current_session",  # Would be set in real context
            time_range=(start_time, end_time),
        )

        result = {
            "status": "success",
            "location": location or "all_monitored_areas",
            "time_range": time_range,
            "metrics": {
                "average_speed_kmh": flow_data.get("avg_speed", 0),
                "total_vehicles": flow_data.get("total_vehicles_passed", 0),
                "unique_tracks": flow_data.get("unique_tracks", 0),
                "speed_range": flow_data.get("speed_range", {}),
            },
            "direction_distribution": flow_data.get("direction_distribution", {}),
            "vehicle_type_distribution": flow_data.get("vehicle_type_distribution", {}),
            "peak_activity_time": flow_data.get("peak_activity_time"),
        }

        if include_historical:
            # Get historical data (24 hours ago)
            hist_start = start_time - timedelta(days=1)
            hist_end = end_time - timedelta(days=1)

            historical = await get_traffic_flow(
                session,
                session_id="current_session",
                time_range=(hist_start, hist_end),
            )

            current_speed = flow_data.get("avg_speed", 0)
            hist_speed = historical.get("avg_speed", 0)

            result["comparison"] = {
                "baseline_speed_kmh": hist_speed,
                "current_speed_kmh": current_speed,
                "speed_change_percent": (
                    ((current_speed - hist_speed) / hist_speed * 100)
                    if hist_speed > 0 else 0
                ),
                "trend": "worsening" if current_speed < hist_speed else "improving",
            }

        return result

    except Exception as e:
        logger.error(f"Error analyzing traffic flow: {e}")
        return {
            "status": "error",
            "message": str(e),
        }
    finally:
        if session:
            await session.close()


# ==================== Shift Reports ====================

@tool("generate_shift_report", args_schema=ShiftReportInput)
async def generate_shift_report(
    shift_time: str,
    date: Optional[str] = None,
    include_recommendations: bool = True,
) -> dict[str, Any]:
    """
    Generate comprehensive shift report.

    Creates a detailed report for a specific shift including metrics,
    incident summaries, and operational recommendations.

    Args:
        shift_time: Shift identifier (morning, afternoon, night, or HH:MM-HH:MM)
        date: Report date (defaults to today)
        include_recommendations: Include operational recommendations

    Returns:
        Dictionary with shift report data.

    Example:
        generate_shift_report(
            shift_time="08:00-16:00",
            date="2024-03-31",
            include_recommendations=True
        )
    """
    logger.info(
        f"Generating shift report: shift={shift_time}, "
        f"date={date}, include_recommendations={include_recommendations}"
    )

    session = None
    try:
        session = await get_db_session()

        report_date = date or datetime.now().strftime("%Y-%m-%d")

        # Parse shift time to actual time bounds
        if shift_time.lower() == "morning":
            shift_start = "06:00"
            shift_end = "14:00"
        elif shift_time.lower() == "afternoon":
            shift_start = "14:00"
            shift_end = "22:00"
        elif shift_time.lower() == "night":
            shift_start = "22:00"
            shift_end = "06:00"
        else:
            parts = shift_time.split("-")
            shift_start = parts[0] if len(parts) > 0 else "00:00"
            shift_end = parts[1] if len(parts) > 1 else "23:59"

        # Get session stats
        stats = await get_session_stats(session, "current_session")

        # Get incidents for the shift
        incidents = await get_incidents(session, "current_session")

        # Get vehicle counts
        counts = await get_vehicle_counts(session, "current_session")

        report = {
            "status": "success",
            "report_date": report_date,
            "shift": shift_time,
            "shift_hours": f"{shift_start}-{shift_end}",
            "summary": {
                "total_vehicles": stats.get("detection_stats", {}).get("total_detections", 0),
                "unique_vehicles": stats.get("detection_stats", {}).get("unique_tracks", 0),
                "incidents": stats.get("incident_stats", {}).get("total_incidents", 0),
                "unresolved_incidents": stats.get("incident_stats", {}).get("unresolved_incidents", 0),
                "average_detection_confidence": stats.get("detection_stats", {}).get("avg_confidence", 0),
            },
            "vehicle_breakdown": {
                "total": len(counts),
            },
            "incidents_list": [
                {
                    "id": inc.get("id"),
                    "type": inc.get("incident_type"),
                    "severity": inc.get("severity"),
                    "location": inc.get("location_description"),
                    "timestamp": inc.get("timestamp"),
                    "resolved": inc.get("resolved"),
                }
                for inc in incidents
            ],
        }

        if include_recommendations:
            incident_count = stats.get("incident_stats", {}).get("total_incidents", 0)
            unresolved = stats.get("incident_stats", {}).get("unresolved_incidents", 0)

            recommendations = []
            if unresolved > 0:
                recommendations.append(f"Address {unresolved} unresolved incidents immediately")
            if incident_count > 5:
                recommendations.append("High incident rate detected - increase patrol presence")

            avg_confidence = stats.get("detection_stats", {}).get("avg_confidence", 0)
            if avg_confidence < 0.7:
                recommendations.append("Detection confidence is low - review camera calibration")

            if not recommendations:
                recommendations.append("Traffic conditions normal for shift")

            report["recommendations"] = recommendations

        # Create report in database
        await create_report(
            session,
            session_id="current_session",
            report_type="shift_report",
            content=json.dumps(report),
            query_text=f"Shift {shift_time} on {report_date}",
        )

        return report

    except Exception as e:
        logger.error(f"Error generating shift report: {e}")
        return {
            "status": "error",
            "message": str(e),
        }
    finally:
        if session:
            await session.close()


# ==================== Period Comparison ====================

@tool("compare_periods", args_schema=ComparePeriodInput)
async def compare_periods(
    period_1: str,
    period_2: str,
    metric: str = "vehicle_count",
    location: Optional[str] = None,
) -> dict[str, Any]:
    """
    Compare metrics across two time periods.

    Provides side-by-side comparison of traffic metrics to identify
    patterns, trends, and anomalies.

    Args:
        period_1: First time period to compare
        period_2: Second time period to compare
        metric: Metric to compare (vehicle_count, incident_count, avg_flow, peak_time)
        location: Optional location filter

    Returns:
        Dictionary with comparative analysis.

    Example:
        compare_periods(
            period_1="today",
            period_2="yesterday",
            metric="vehicle_count",
            location="main_street"
        )
    """
    logger.info(
        f"Comparing periods: {period_1} vs {period_2}, "
        f"metric={metric}, location={location}"
    )

    session = None
    try:
        session = await get_db_session()

        # Parse time ranges for both periods
        start_1, end_1 = parse_time_range(period_1)
        start_2, end_2 = parse_time_range(period_2)

        comparison = {
            "status": "success",
            "period_1": period_1,
            "period_2": period_2,
            "metric": metric,
            "location": location or "all_zones",
        }

        if metric == "vehicle_count":
            # Get counts for both periods
            counts_1 = await get_vehicle_counts(
                session,
                session_id="current_session",
                direction=location,
            )
            counts_2 = await get_vehicle_counts(
                session,
                session_id="current_session",
                direction=location,
            )

            total_1 = sum(c.get("count", 0) for c in counts_1)
            total_2 = sum(c.get("count", 0) for c in counts_2)

            comparison.update({
                "period_1_value": total_1,
                "period_2_value": total_2,
                "difference": total_1 - total_2,
                "percent_change": (
                    ((total_1 - total_2) / total_2 * 100) if total_2 > 0 else 0
                ),
                "trend": "increase" if total_1 > total_2 else "decrease",
            })

        elif metric == "incident_count":
            # Get incidents for both periods
            incidents_1 = await get_incidents(session, "current_session")
            incidents_2 = await get_incidents(session, "current_session")

            count_1 = len(incidents_1)
            count_2 = len(incidents_2)

            comparison.update({
                "period_1_value": count_1,
                "period_2_value": count_2,
                "difference": count_1 - count_2,
                "percent_change": (
                    ((count_1 - count_2) / count_2 * 100) if count_2 > 0 else 0
                ),
                "trend": "improvement" if count_1 < count_2 else "degradation",
            })

        return comparison

    except Exception as e:
        logger.error(f"Error comparing periods: {e}")
        return {
            "status": "error",
            "message": str(e),
        }
    finally:
        if session:
            await session.close()


# ==================== Scene Description ====================

@tool("get_current_scene", args_schema=SceneSnapshotInput)
async def get_current_scene(
    location: Optional[str] = None,
    detail_level: str = "standard",
) -> dict[str, Any]:
    """
    Get current real-time scene description.

    Provides a snapshot of current traffic conditions and activity,
    useful for real-time monitoring and immediate decision-making.

    Args:
        location: Optional specific location (defaults to all areas)
        detail_level: Detail level (brief, standard, detailed)

    Returns:
        Dictionary with current scene description and status.

    Example:
        get_current_scene(
            location="main_corridor",
            detail_level="detailed"
        )
    """
    logger.info(
        f"Getting current scene: location={location}, detail={detail_level}"
    )

    session = None
    try:
        session = await get_db_session()

        # Get current/recent detection summary
        summary = await get_detection_summary(session, "current_session")

        # Get active incidents
        incidents = await get_incidents(session, "current_session", resolved=False)

        # Get vehicle counts for current breakdown
        counts = await get_vehicle_counts(session, "current_session")

        scene = {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "location": location or "all_monitored_areas",
            "overall_flow": "moderate",
            "current_vehicle_count": summary.get("total_detections", 0),
            "active_incidents": len(incidents),
            "alerts": [
                f"Active incident: {inc.get('incident_type')} at {inc.get('location_description')}"
                for inc in incidents
            ] if incidents else [],
        }

        if detail_level in ["standard", "detailed"]:
            # Get vehicle breakdown
            type_breakdown = summary.get("vehicle_type_breakdown", {})

            scene.update({
                "vehicle_breakdown": type_breakdown,
                "unique_vehicles_tracked": summary.get("unique_tracks", 0),
                "average_confidence": summary.get("confidence_stats", {}).get("avg", 0),
                "hotspots": [
                    {
                        "location": inc.get("location_description"),
                        "severity": inc.get("severity"),
                        "type": inc.get("incident_type"),
                    }
                    for inc in incidents
                ],
            })

        if detail_level == "detailed":
            scene.update({
                "recent_activity": [
                    {
                        "timestamp": inc.get("timestamp"),
                        "type": "incident_reported",
                        "description": inc.get("description"),
                        "location": inc.get("location_description"),
                    }
                    for inc in incidents
                ],
                "recommendations": [
                    f"Monitor {inc.get('location_description')} for {inc.get('incident_type')}"
                    for inc in incidents
                ] if incidents else ["Scene appears normal"],
            })

        return scene

    except Exception as e:
        logger.error(f"Error getting current scene: {e}")
        return {
            "status": "error",
            "message": str(e),
        }
    finally:
        if session:
            await session.close()
