"""
Traffic Intelligence Platform - AI Agent Module

This module provides a LangGraph-based AI agent system for analyzing
traffic data, incidents, and generating insights and reports.
"""

from agents.graph import TrafficAnalysisGraph
from agents.tools import (
    query_detections,
    get_vehicle_count,
    get_incident_report,
    get_traffic_flow,
    generate_shift_report,
    compare_periods,
    get_current_scene,
)
from agents.rag import DetectionRAG
from agents.prompts import (
    TRAFFIC_ANALYST_SYSTEM,
    REPORT_GENERATOR,
    INCIDENT_ANALYZER,
    SCENE_DESCRIBER,
)

__all__ = [
    "TrafficAnalysisGraph",
    # Tools
    "query_detections",
    "get_vehicle_count",
    "get_incident_report",
    "get_traffic_flow",
    "generate_shift_report",
    "compare_periods",
    "get_current_scene",
    # RAG
    "DetectionRAG",
    # Prompts
    "TRAFFIC_ANALYST_SYSTEM",
    "REPORT_GENERATOR",
    "INCIDENT_ANALYZER",
    "SCENE_DESCRIBER",
]
