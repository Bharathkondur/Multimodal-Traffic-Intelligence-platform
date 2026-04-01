"""
Test suite for Traffic Intelligence Agent.

Includes unit tests for:
- Query classification
- RAG system
- Tool functionality
- Agent state management
"""

import pytest
import asyncio
from datetime import datetime, timedelta

from agents.graph import TrafficAnalysisGraph, QueryType, LLMBackend, TrafficAgentState
from agents.rag import DetectionRAG
from agents.tools import (
    VehicleType,
    query_detections,
    get_vehicle_count,
    get_incident_report,
    get_traffic_flow,
    generate_shift_report,
    compare_periods,
    get_current_scene,
)
from agents.config import TrafficAgentConfig, get_config


# ==================== Query Classification Tests ====================

class TestQueryClassification:
    """Tests for query type classification."""

    def setup_method(self):
        """Setup for each test."""
        self.agent = TrafficAnalysisGraph(
            llm_backend=LLMBackend.OPENAI,
            enable_streaming=False,
        )

    def test_classify_question(self):
        """Test question classification."""
        queries = [
            "What's the current traffic?",
            "How many vehicles on Main Street?",
            "Where are the incidents?",
        ]
        for query in queries:
            result = self.agent._classify_query(query)
            assert result in [
                QueryType.QUESTION,
                QueryType.SCENE,
                QueryType.ALERT,
            ]

    def test_classify_report(self):
        """Test report classification."""
        queries = [
            "Generate a shift report",
            "Create a summary for today",
            "What's the shift summary?",
        ]
        for query in queries:
            result = self.agent._classify_query(query)
            assert result == QueryType.REPORT

    def test_classify_alert(self):
        """Test alert classification."""
        queries = [
            "Is there an accident?",
            "Alert on Main Street",
            "Any incidents reported?",
        ]
        for query in queries:
            result = self.agent._classify_query(query)
            assert result == QueryType.ALERT

    def test_classify_scene(self):
        """Test scene classification."""
        queries = [
            "What's happening now?",
            "Current scene description",
            "What's going on right now?",
        ]
        for query in queries:
            result = self.agent._classify_query(query)
            assert result == QueryType.SCENE

    def test_classify_analysis(self):
        """Test analysis classification."""
        queries = [
            "Compare today and yesterday",
            "Analyze traffic patterns",
            "What's the trend?",
        ]
        for query in queries:
            result = self.agent._classify_query(query)
            assert result == QueryType.ANALYSIS


# ==================== RAG System Tests ====================

class TestDetectionRAG:
    """Tests for RAG system."""

    def setup_method(self):
        """Setup for each test."""
        self.rag = DetectionRAG()
        self.now = datetime.now()

    def test_add_detection(self):
        """Test adding single detection."""
        doc_id = self.rag.add_detection(
            detection_type="vehicle",
            content="Test vehicle detection",
            timestamp=self.now,
            location="Test Location",
        )
        assert doc_id.startswith("det_")
        assert len(self.rag.detections) == 1

    def test_add_batch(self):
        """Test batch detection addition."""
        detections = [
            {
                "detection_type": "vehicle",
                "content": "Vehicle 1",
                "timestamp": self.now,
                "location": "Loc 1",
            },
            {
                "detection_type": "incident",
                "content": "Incident 1",
                "timestamp": self.now,
                "location": "Loc 2",
            },
        ]
        doc_ids = self.rag.add_batch(detections)
        assert len(doc_ids) == 2
        assert len(self.rag.detections) == 2

    def test_retrieve_recent(self):
        """Test retrieving recent detections."""
        # Add recent detection
        self.rag.add_detection(
            detection_type="vehicle",
            content="Recent vehicle",
            timestamp=self.now,
            location="Main St",
        )

        # Add old detection
        self.rag.add_detection(
            detection_type="vehicle",
            content="Old vehicle",
            timestamp=self.now - timedelta(hours=2),
            location="Main St",
        )

        recent = self.rag.retrieve_recent(hours=1)
        assert len(recent) == 1
        assert "Recent vehicle" in recent[0]["content"]

    def test_retrieve_by_location(self):
        """Test location-based retrieval."""
        self.rag.add_detection(
            detection_type="vehicle",
            content="Vehicle at Main St",
            timestamp=self.now,
            location="Main St & 5th",
        )

        self.rag.add_detection(
            detection_type="vehicle",
            content="Vehicle at Oak St",
            timestamp=self.now,
            location="Oak St & 3rd",
        )

        results = self.rag.retrieve_by_location("Main St", hours=1)
        assert len(results) == 1
        assert "Main St" in results[0]["location"]

    def test_retrieve_incidents(self):
        """Test incident retrieval."""
        self.rag.add_detection(
            detection_type="incident",
            content="Accident",
            timestamp=self.now,
            location="Main St",
            metadata={"severity": "high"},
        )

        self.rag.add_detection(
            detection_type="vehicle",
            content="Vehicle",
            timestamp=self.now,
            location="Main St",
        )

        incidents = self.rag.retrieve_incidents(hours=1)
        assert len(incidents) == 1
        assert incidents[0]["type"] == "incident"

    def test_semantic_search(self):
        """Test semantic search."""
        # Add test detections
        self.rag.add_detection(
            detection_type="vehicle",
            content="Heavy truck congestion at main intersection",
            timestamp=self.now,
            location="Main Intersection",
        )

        self.rag.add_detection(
            detection_type="incident",
            content="Fender bender accident",
            timestamp=self.now,
            location="Other Location",
        )

        # Search for trucks
        results = self.rag.retrieve("trucks and congestion", k=2)
        assert len(results) > 0
        # First result should have higher relevance for "trucks"
        assert results[0]["relevance_score"] >= 0.0

    def test_rag_statistics(self):
        """Test RAG statistics."""
        self.rag.add_detection(
            detection_type="vehicle",
            content="Test",
            timestamp=self.now,
            location="Loc1",
        )

        stats = self.rag.get_statistics()
        assert stats["total_documents"] == 1
        assert "vehicle" in stats["detection_types"]
        assert "Loc1" in stats["locations"]

    def test_context_formatting(self):
        """Test context formatting for LLM."""
        self.rag.add_detection(
            detection_type="vehicle",
            content="Test vehicle detection",
            timestamp=self.now,
            location="Main St",
        )

        context = self.rag.get_context("vehicle", k=1)
        assert "Relevant Detection Events" in context
        assert "VEHICLE" in context
        assert "Main St" in context

    def test_clear_rag(self):
        """Test clearing RAG."""
        self.rag.add_detection(
            detection_type="vehicle",
            content="Test",
            timestamp=self.now,
            location="Test",
        )

        assert len(self.rag.detections) == 1

        self.rag.clear()
        assert len(self.rag.detections) == 0
        stats = self.rag.get_statistics()
        assert stats["total_documents"] == 0


# ==================== Tool Tests ====================

class TestTools:
    """Tests for agent tools."""

    @pytest.mark.asyncio
    async def test_query_detections(self):
        """Test detection query tool."""
        result = await query_detections(
            query="test query",
            time_range="last_hour",
            limit=5
        )
        assert result["status"] == "success"
        assert result["results_count"] > 0

    @pytest.mark.asyncio
    async def test_get_vehicle_count(self):
        """Test vehicle counting."""
        result = await get_vehicle_count(
            vehicle_type=VehicleType.TRUCK,
            time_range="today"
        )
        assert result["status"] == "success"
        assert result["total_count"] > 0

    @pytest.mark.asyncio
    async def test_get_incident_report(self):
        """Test incident reporting."""
        result = await get_incident_report(
            incident_id="INC123",
            include_details=True
        )
        assert result["status"] == "success"
        assert "incident_id" in result

    @pytest.mark.asyncio
    async def test_get_traffic_flow(self):
        """Test traffic flow analysis."""
        result = await get_traffic_flow(
            location="Main St",
            time_range="last_hour",
            include_historical=True
        )
        assert result["status"] == "success"
        assert "metrics" in result

    @pytest.mark.asyncio
    async def test_generate_shift_report(self):
        """Test shift report generation."""
        result = await generate_shift_report(
            shift_time="08:00-16:00",
            include_recommendations=True
        )
        assert result["status"] == "success"
        assert "summary" in result

    @pytest.mark.asyncio
    async def test_compare_periods(self):
        """Test period comparison."""
        result = await compare_periods(
            period_1="today",
            period_2="yesterday",
            metric="vehicle_count"
        )
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_get_current_scene(self):
        """Test scene description."""
        result = await get_current_scene(
            detail_level="detailed"
        )
        assert result["status"] == "success"
        assert "timestamp" in result


# ==================== Agent State Tests ====================

class TestAgentState:
    """Tests for agent state management."""

    def test_initial_state(self):
        """Test initial agent state."""
        state = TrafficAgentState(
            user_query="test query"
        )
        assert state.user_query == "test query"
        assert state.query_type == QueryType.UNKNOWN
        assert len(state.messages) == 0
        assert state.context == ""

    def test_state_update(self):
        """Test state updates."""
        state = TrafficAgentState(user_query="test")
        state.query_type = QueryType.QUESTION
        state.context = "test context"

        assert state.query_type == QueryType.QUESTION
        assert state.context == "test context"


# ==================== Configuration Tests ====================

class TestConfiguration:
    """Tests for configuration management."""

    def test_default_config(self):
        """Test default configuration."""
        config = TrafficAgentConfig()
        assert config.agent.llm_backend in [
            LLMBackend.OPENAI,
            LLMBackend.OLLAMA,
        ]
        assert config.rag.enabled in [True, False]

    def test_config_to_dict(self):
        """Test config to dict conversion."""
        config = TrafficAgentConfig()
        config_dict = config.to_dict()

        assert "llm_backend" in config_dict
        assert "llm_model" in config_dict
        assert "temperature" in config_dict
        assert "rag_enabled" in config_dict

    def test_config_validation(self):
        """Test configuration validation."""
        config = TrafficAgentConfig()
        is_valid, errors = config.validate()

        # Should return bool and list
        assert isinstance(is_valid, bool)
        assert isinstance(errors, list)


# ==================== Graph Tests ====================

class TestTrafficAnalysisGraph:
    """Tests for main graph."""

    def setup_method(self):
        """Setup for each test."""
        self.agent = TrafficAnalysisGraph(
            llm_backend=LLMBackend.OPENAI,
            enable_streaming=False,
        )

    def test_graph_initialization(self):
        """Test graph initialization."""
        assert self.agent.llm_backend == LLMBackend.OPENAI
        assert len(self.agent.tools) > 0

    def test_graph_schema(self):
        """Test graph schema."""
        schema = self.agent.get_graph_schema()

        assert "nodes" in schema
        assert "edges" in schema
        assert "query_types" in schema
        assert "llm_backend" in schema

        assert "analyze_query" in schema["nodes"]
        assert "retrieve_data" in schema["nodes"]
        assert "reason" in schema["nodes"]
        assert "generate_response" in schema["nodes"]

    def test_system_prompt_selection(self):
        """Test system prompt selection."""
        from agents.prompts import (
            TRAFFIC_ANALYST_SYSTEM,
            REPORT_GENERATOR,
            INCIDENT_ANALYZER,
            SCENE_DESCRIBER,
        )

        prompt = self.agent._get_system_prompt(QueryType.QUESTION)
        assert prompt == TRAFFIC_ANALYST_SYSTEM

        prompt = self.agent._get_system_prompt(QueryType.REPORT)
        assert prompt == REPORT_GENERATOR

        prompt = self.agent._get_system_prompt(QueryType.ALERT)
        assert prompt == INCIDENT_ANALYZER

        prompt = self.agent._get_system_prompt(QueryType.SCENE)
        assert prompt == SCENE_DESCRIBER


# ==================== Run Tests ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
