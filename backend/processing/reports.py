"""
Report generation task for traffic intelligence analysis.

Generates structured reports using LangGraph agent, combining detection data
with natural language analysis for shift summaries, incident reports, and custom queries.
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

try:
    from sqlalchemy.ext.asyncio import AsyncSession
except ImportError:
    AsyncSession = None

logger = logging.getLogger(__name__)


async def generate_report_task(
    session_id: str,
    report_type: str,
    query: str,
    db_session: Optional[object] = None,
) -> Dict[str, Any]:
    """
    Generate a traffic intelligence report using LangGraph agent.

    Creates structured reports by querying detection data and feeding it
    through the LangGraph agent with appropriate prompts for different
    report types.

    Args:
        session_id: Unique identifier for the traffic session
        report_type: Type of report ("shift", "incident", "summary", "custom")
        query: User query or report specification
        db_session: SQLAlchemy AsyncSession (optional, creates new if None)

    Returns:
        Dictionary containing:
            {
                "report_id": str,
                "session_id": str,
                "report_type": str,
                "generated_at": datetime,
                "statistics": {
                    "total_detections": int,
                    "total_incidents": int,
                    "vehicle_type_breakdown": Dict[str, int],
                    "time_range": Dict[str, datetime],
                    "confidence_stats": Dict[str, float],
                },
                "summary": str,  # Natural language summary
                "incidents": List[Dict],  # List of detected incidents
                "recommendations": List[str],  # AI-generated recommendations
                "raw_data": Dict,  # Raw query results
            }

    Raises:
        Exception: Logs errors and returns error response

    Report Types:
        - shift: Summary of a shift's traffic activity
        - incident: Detailed incident analysis
        - summary: High-level overview of detections
        - custom: Custom analysis based on user query

    Processing:
        1. Queries detection and incident data from database
        2. Aggregates statistics
        3. Passes data to LangGraph agent with appropriate prompt
        4. Saves report to database
        5. Returns structured report response
    """
    import uuid

    report_id = str(uuid.uuid4())

    try:
        logger.info(f"Generating {report_type} report for session {session_id}")

        # Import database components
        from database.connection import AsyncSessionFactory
        from database.models import TrafficReport, ReportType
        from database.queries import (
            get_detection_summary,
            get_incidents,
            get_vehicle_counts,
        )

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
            # Query detection data
            logger.debug(f"Querying detection data for session {session_id}")
            detection_summary = await get_detection_summary(db_session, session_id)

            # Query incident data
            incidents = await get_incidents(db_session, session_id)
            incident_list = [
                {
                    "id": incident.id,
                    "type": incident.incident_type.value,
                    "severity": incident.severity_level.value,
                    "timestamp": incident.timestamp.isoformat(),
                    "description": incident.description,
                    "vehicles_involved": incident.vehicles_involved,
                }
                for incident in incidents[:10]  # Top 10 incidents
            ]

            # Query vehicle counts
            vehicle_counts = await get_vehicle_counts(db_session, session_id)
            vehicle_breakdown = {
                vc.vehicle_type.value: vc.count for vc in vehicle_counts
            }

            # Prepare context data for LangGraph agent
            context_data = {
                "session_id": session_id,
                "detection_summary": detection_summary,
                "incidents": incident_list,
                "vehicle_breakdown": vehicle_breakdown,
                "report_type": report_type,
                "user_query": query,
            }

            logger.debug("Querying complete, preparing LangGraph agent")

            # Process through LangGraph agent
            from agents.langgraph_agent import process_message

            # Create appropriate prompt based on report type
            if report_type == "shift":
                agent_message = (
                    f"Generate a shift report for session {session_id}. "
                    f"Total detections: {detection_summary.get('total_detections', 0)}, "
                    f"Incidents: {len(incident_list)}. "
                    f"Provide a professional shift summary with statistics and recommendations."
                )
            elif report_type == "incident":
                agent_message = (
                    f"Analyze incidents for session {session_id}. "
                    f"Found {len(incident_list)} incidents. "
                    f"Provide detailed analysis and recommendations. Query: {query}"
                )
            elif report_type == "summary":
                agent_message = (
                    f"Summarize traffic activity for session {session_id}. "
                    f"Total detections: {detection_summary.get('total_detections', 0)}, "
                    f"Vehicle types: {vehicle_breakdown}. "
                    f"Provide a concise traffic summary."
                )
            else:  # custom
                agent_message = (
                    f"Analyze traffic data for session {session_id}. "
                    f"Available data: {detection_summary.get('total_detections', 0)} detections, "
                    f"{len(incident_list)} incidents. "
                    f"User query: {query}"
                )

            # Get LLM response
            agent_response = await process_message(
                session_id=session_id,
                message=agent_message,
                db_session=db_session,
            )

            logger.info(f"LangGraph agent generated response for report {report_id}")

            # Extract response content
            response_text = agent_response.get("response", "")
            recommendations = []

            # Parse recommendations from response if available
            if "recommendation" in response_text.lower():
                # Simple extraction of recommendations
                lines = response_text.split("\n")
                for line in lines:
                    if (
                        "recommend" in line.lower()
                        or "suggest" in line.lower()
                        or "should" in line.lower()
                    ):
                        recommendations.append(line.strip())

            # Build report response
            report_response = {
                "report_id": report_id,
                "session_id": session_id,
                "report_type": report_type,
                "generated_at": datetime.now().isoformat(),
                "statistics": {
                    "total_detections": detection_summary.get("total_detections", 0),
                    "total_incidents": len(incident_list),
                    "vehicle_type_breakdown": vehicle_breakdown,
                    "unique_tracks": detection_summary.get("unique_tracks", 0),
                    "time_range": {
                        "start": detection_summary.get("time_range", {}).get("start"),
                        "end": detection_summary.get("time_range", {}).get("end"),
                    },
                    "confidence_stats": detection_summary.get("confidence_stats", {}),
                },
                "summary": response_text,
                "incidents": incident_list,
                "recommendations": recommendations[:5],  # Top 5 recommendations
                "raw_data": {
                    "detection_summary": detection_summary,
                    "vehicle_breakdown": vehicle_breakdown,
                },
            }

            # Save report to database
            try:
                logger.debug(f"Saving report {report_id} to database")

                from sqlalchemy import insert

                stmt = insert(TrafficReport).values(
                    id=report_id,
                    session_id=session_id,
                    report_type=report_type,
                    summary=response_text,
                    statistics={
                        "total_detections": report_response["statistics"][
                            "total_detections"
                        ],
                        "total_incidents": report_response["statistics"]["total_incidents"],
                        "vehicle_breakdown": vehicle_breakdown,
                    },
                    generated_at=datetime.now(),
                )
                await db_session.execute(stmt)
                await db_session.commit()
                logger.info(f"Report {report_id} saved to database successfully")
            except Exception as save_error:
                logger.error(f"Failed to save report to database: {save_error}")
                # Continue anyway, report is still generated in memory

            logger.info(f"Report generation completed for {report_id}")
            return report_response

        finally:
            # Clean up session if we created it
            if session_owner is not None:
                await session_owner.close()

    except Exception as e:
        logger.error(f"Report generation error for session {session_id}: {e}", exc_info=True)

        # Return error response
        return {
            "report_id": report_id,
            "session_id": session_id,
            "report_type": report_type,
            "generated_at": datetime.now().isoformat(),
            "error": str(e),
            "statistics": {},
            "summary": f"Error generating report: {e}",
            "incidents": [],
            "recommendations": [],
            "raw_data": {},
        }
