"""
Multi-Agent Traffic Intelligence System.

Instead of one monolithic agent, this system uses specialized agents that collaborate:
1. DetectionAnalyst — Interprets CV detection data, explains what's happening
2. IncidentResponder — Focuses on incident analysis, severity assessment, recommendations
3. ReportGenerator — Creates structured reports with statistics and insights
4. PredictiveAnalyst — Analyzes patterns, predicts congestion, suggests optimizations
5. Coordinator — Routes queries to the right specialist, combines responses

This multi-agent approach is more accurate and produces richer responses than a single agent.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, List, Any, Callable

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langchain_core.language_model import BaseLLM
from langgraph.graph import StateGraph, START, END
from langgraph.graph.graph import CompiledGraph

logger = logging.getLogger(__name__)


class AgentRole(str, Enum):
    """Roles in the multi-agent system."""
    COORDINATOR = "coordinator"
    DETECTION_ANALYST = "detection_analyst"
    INCIDENT_RESPONDER = "incident_responder"
    REPORT_GENERATOR = "report_generator"
    PREDICTIVE_ANALYST = "predictive_analyst"


class QueryType(str, Enum):
    """Classification of user queries."""
    DETECTION = "detection"
    INCIDENT = "incident"
    REPORT = "report"
    PREDICTION = "prediction"
    GENERAL = "general"


@dataclass
class MultiAgentState:
    """State shared across all agents in the workflow."""
    # Input/Output
    query: str = ""
    final_response: str = ""

    # Query analysis
    query_type: QueryType = QueryType.GENERAL
    assigned_agents: List[AgentRole] = field(default_factory=list)

    # Specialist responses
    agent_responses: Dict[AgentRole, str] = field(default_factory=dict)

    # Context and data
    context_data: Dict[str, Any] = field(default_factory=dict)
    frame_data: Optional[Dict[str, Any]] = None
    detection_data: Optional[List[Dict[str, Any]]] = None
    incident_data: Optional[List[Dict[str, Any]]] = None
    track_data: Optional[List[Dict[str, Any]]] = None

    # Metadata
    session_id: Optional[str] = None
    timestamp: Optional[str] = None
    messages: List[BaseMessage] = field(default_factory=list)


class TrafficMultiAgentSystem:
    """
    Multi-agent system with specialized traffic intelligence agents.

    The Coordinator analyzes the query and routes it to 1-3 specialists.
    Each specialist has its own system prompt and tool access.
    The Coordinator then synthesizes specialist responses into a final answer.
    """

    def __init__(
        self,
        llm: BaseLLM,
        tools_dict: Optional[Dict[AgentRole, List[Any]]] = None,
        db_context: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the multi-agent system.

        Args:
            llm: BaseLLM instance for all agents (e.g., ChatGoogleGenerativeAI)
            tools_dict: Dictionary mapping AgentRole to list of tools available to that agent
            db_context: Database connection or context for querying real data
        """
        self.llm = llm
        self.tools_dict = tools_dict or {}
        self.db_context = db_context or {}

        # Create specialized LLMs with different parameters
        self.agents = {
            AgentRole.COORDINATOR: self._create_agent(AgentRole.COORDINATOR, temperature=0.2),
            AgentRole.DETECTION_ANALYST: self._create_agent(AgentRole.DETECTION_ANALYST, temperature=0.3),
            AgentRole.INCIDENT_RESPONDER: self._create_agent(AgentRole.INCIDENT_RESPONDER, temperature=0.3),
            AgentRole.REPORT_GENERATOR: self._create_agent(AgentRole.REPORT_GENERATOR, temperature=0.2),
            AgentRole.PREDICTIVE_ANALYST: self._create_agent(AgentRole.PREDICTIVE_ANALYST, temperature=0.7),
        }

        # Build the LangGraph
        self.graph = self._build_graph()

        logger.info("TrafficMultiAgentSystem initialized with 5 specialized agents")

    def _create_agent(self, role: AgentRole, temperature: float = 0.3) -> BaseLLM:
        """
        Create an LLM instance for a specific agent role.

        Args:
            role: The role of the agent
            temperature: Sampling temperature (lower = more deterministic, higher = more creative)

        Returns:
            Configured LLM instance
        """
        # Clone the LLM with different temperature
        if hasattr(self.llm, "with_config"):
            return self.llm.with_config({"temperature": temperature})
        elif hasattr(self.llm, "bind"):
            return self.llm.bind(temperature=temperature)
        else:
            # Fallback: return the same LLM
            return self.llm

    def _build_graph(self) -> CompiledGraph:
        """
        Build the LangGraph workflow for multi-agent coordination.

        Structure:
            START -> classify_query -> route_to_specialists -> parallel_specialist_calls
                  -> synthesize_responses -> final_response -> END

        Returns:
            Compiled LangGraph workflow
        """
        workflow = StateGraph(MultiAgentState)

        # Add nodes
        workflow.add_node("classify_query", self._classify_query_node)
        workflow.add_node("route_specialists", self._route_specialists_node)
        workflow.add_node("detection_analyst", self._detection_analyst_node)
        workflow.add_node("incident_responder", self._incident_responder_node)
        workflow.add_node("report_generator", self._report_generator_node)
        workflow.add_node("predictive_analyst", self._predictive_analyst_node)
        workflow.add_node("synthesize", self._synthesize_responses_node)

        # Add edges
        workflow.add_edge(START, "classify_query")
        workflow.add_edge("classify_query", "route_specialists")
        workflow.add_conditional_edges(
            "route_specialists",
            self._route_to_specialists,
            {
                AgentRole.DETECTION_ANALYST.value: "detection_analyst",
                AgentRole.INCIDENT_RESPONDER.value: "incident_responder",
                AgentRole.REPORT_GENERATOR.value: "report_generator",
                AgentRole.PREDICTIVE_ANALYST.value: "predictive_analyst",
                "synthesize": "synthesize",
            }
        )

        # All specialists feed into synthesis
        workflow.add_edge("detection_analyst", "synthesize")
        workflow.add_edge("incident_responder", "synthesize")
        workflow.add_edge("report_generator", "synthesize")
        workflow.add_edge("predictive_analyst", "synthesize")

        workflow.add_edge("synthesize", END)

        return workflow.compile()

    def _classify_query_node(self, state: MultiAgentState) -> MultiAgentState:
        """
        Classify the query into one of several types.

        Args:
            state: Current workflow state

        Returns:
            Updated state with query_type
        """
        query = state.query.lower()

        # Simple keyword-based classification
        if any(word in query for word in ["detect", "vehicle", "car", "truck", "person", "object"]):
            state.query_type = QueryType.DETECTION
        elif any(word in query for word in ["incident", "accident", "collision", "congestion", "stopped", "wrong way"]):
            state.query_type = QueryType.INCIDENT
        elif any(word in query for word in ["report", "summary", "statistics", "count", "aggregate"]):
            state.query_type = QueryType.REPORT
        elif any(word in query for word in ["predict", "forecast", "trend", "optimize", "pattern"]):
            state.query_type = QueryType.PREDICTION
        else:
            state.query_type = QueryType.GENERAL

        logger.debug(f"Query classified as: {state.query_type.value}")
        return state

    def _route_specialists_node(self, state: MultiAgentState) -> MultiAgentState:
        """
        Determine which specialists should handle this query.

        Args:
            state: Current workflow state

        Returns:
            Updated state with assigned_agents
        """
        assigned = []

        # Route based on query type
        if state.query_type == QueryType.DETECTION:
            assigned = [AgentRole.DETECTION_ANALYST]
        elif state.query_type == QueryType.INCIDENT:
            assigned = [AgentRole.INCIDENT_RESPONDER, AgentRole.DETECTION_ANALYST]
        elif state.query_type == QueryType.REPORT:
            assigned = [AgentRole.REPORT_GENERATOR, AgentRole.DETECTION_ANALYST]
        elif state.query_type == QueryType.PREDICTION:
            assigned = [AgentRole.PREDICTIVE_ANALYST, AgentRole.REPORT_GENERATOR]
        else:  # GENERAL
            assigned = [AgentRole.COORDINATOR]

        state.assigned_agents = assigned
        logger.debug(f"Assigned agents: {[a.value for a in assigned]}")
        return state

    def _route_to_specialists(self, state: MultiAgentState) -> str:
        """
        Conditional routing function for LangGraph.

        Args:
            state: Current workflow state

        Returns:
            Name of next node to execute
        """
        if not state.assigned_agents:
            return "synthesize"

        # Return the first assigned agent's node
        next_agent = state.assigned_agents[0]
        return next_agent.value

    def _detection_analyst_node(self, state: MultiAgentState) -> MultiAgentState:
        """
        Detection Analyst agent - interprets CV data.

        Analyzes detection results, identifies patterns, and explains findings.

        Args:
            state: Current workflow state

        Returns:
            Updated state with agent response
        """
        system_prompt = """You are a Computer Vision Detection Analyst specializing in traffic surveillance.

Your expertise:
- Interpreting object detection results (vehicles, persons, objects)
- Analyzing detection confidence scores and accuracy
- Identifying detection patterns and anomalies
- Explaining what objects are present in the scene
- Assessing detection quality and coverage

When analyzing detections:
1. Identify all detected object types and counts
2. Note confidence scores and their implications
3. Highlight any unusual patterns or gaps
4. Assess overall scene coverage
5. Provide actionable insights about what's visible

Be precise and technical in your analysis."""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=self._prepare_detection_prompt(state)),
        ]

        try:
            response = self.agents[AgentRole.DETECTION_ANALYST].invoke(
                {"messages": messages}
            )
            analysis = response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            logger.error(f"Error in detection analyst: {e}")
            analysis = f"Error analyzing detections: {str(e)}"

        state.agent_responses[AgentRole.DETECTION_ANALYST] = analysis
        state.assigned_agents.pop(0)  # Remove processed agent
        return state

    def _incident_responder_node(self, state: MultiAgentState) -> MultiAgentState:
        """
        Incident Responder agent - focuses on incident analysis.

        Analyzes traffic incidents, assesses severity, and recommends responses.

        Args:
            state: Current workflow state

        Returns:
            Updated state with agent response
        """
        system_prompt = """You are a Traffic Incident Response Specialist.

Your expertise:
- Detecting and analyzing traffic incidents
- Assessing incident severity (low/medium/high/critical)
- Understanding incident causes and impacts
- Recommending response actions
- Prioritizing incidents for attention

When analyzing incidents:
1. Identify each incident type (collision, congestion, stopped vehicle, etc.)
2. Assess severity based on impact and safety risks
3. Determine affected areas and traffic flow
4. Recommend immediate response actions
5. Suggest long-term mitigation strategies

Be pragmatic and action-oriented in your analysis."""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=self._prepare_incident_prompt(state)),
        ]

        try:
            response = self.agents[AgentRole.INCIDENT_RESPONDER].invoke(
                {"messages": messages}
            )
            analysis = response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            logger.error(f"Error in incident responder: {e}")
            analysis = f"Error analyzing incidents: {str(e)}"

        state.agent_responses[AgentRole.INCIDENT_RESPONDER] = analysis
        if state.assigned_agents and state.assigned_agents[0] == AgentRole.INCIDENT_RESPONDER:
            state.assigned_agents.pop(0)
        return state

    def _report_generator_node(self, state: MultiAgentState) -> MultiAgentState:
        """
        Report Generator agent - creates structured reports.

        Generates summaries, statistics, and comprehensive reports with insights.

        Args:
            state: Current workflow state

        Returns:
            Updated state with agent response
        """
        system_prompt = """You are a Traffic Intelligence Report Generator.

Your expertise:
- Creating clear, structured reports
- Generating statistics and metrics
- Summarizing complex data concisely
- Visualizing trends and patterns
- Producing executive summaries

When generating reports:
1. Organize information hierarchically
2. Include key metrics and statistics
3. Highlight trends and anomalies
4. Provide visual/textual structure
5. Conclude with actionable recommendations

Format your responses clearly with sections, bullet points, and metrics."""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=self._prepare_report_prompt(state)),
        ]

        try:
            response = self.agents[AgentRole.REPORT_GENERATOR].invoke(
                {"messages": messages}
            )
            analysis = response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            logger.error(f"Error in report generator: {e}")
            analysis = f"Error generating report: {str(e)}"

        state.agent_responses[AgentRole.REPORT_GENERATOR] = analysis
        if state.assigned_agents and state.assigned_agents[0] == AgentRole.REPORT_GENERATOR:
            state.assigned_agents.pop(0)
        return state

    def _predictive_analyst_node(self, state: MultiAgentState) -> MultiAgentState:
        """
        Predictive Analyst agent - forecasts trends and patterns.

        Analyzes historical patterns, predicts future conditions, suggests optimizations.

        Args:
            state: Current workflow state

        Returns:
            Updated state with agent response
        """
        system_prompt = """You are a Traffic Predictive Analytics Specialist.

Your expertise:
- Analyzing traffic patterns and trends
- Predicting congestion and incident likelihood
- Identifying optimization opportunities
- Forecasting traffic behavior
- Recommending preventive measures

When making predictions:
1. Identify current patterns and trends
2. Project future conditions
3. Assess risk factors and probabilities
4. Suggest preventive strategies
5. Recommend optimizations to improve flow

Be data-driven and forward-looking in your analysis."""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=self._prepare_prediction_prompt(state)),
        ]

        try:
            response = self.agents[AgentRole.PREDICTIVE_ANALYST].invoke(
                {"messages": messages}
            )
            analysis = response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            logger.error(f"Error in predictive analyst: {e}")
            analysis = f"Error in predictive analysis: {str(e)}"

        state.agent_responses[AgentRole.PREDICTIVE_ANALYST] = analysis
        if state.assigned_agents and state.assigned_agents[0] == AgentRole.PREDICTIVE_ANALYST:
            state.assigned_agents.pop(0)
        return state

    def _synthesize_responses_node(self, state: MultiAgentState) -> MultiAgentState:
        """
        Synthesize specialist responses into a coherent final answer.

        Args:
            state: Current workflow state

        Returns:
            Updated state with final_response
        """
        if not state.agent_responses:
            state.final_response = "No specialist analysis available for this query."
            return state

        # Build synthesis prompt
        synthesis_prompt = self._build_synthesis_prompt(state)

        system_prompt = """You are the Coordinator in a multi-agent traffic intelligence system.

Your role:
- Synthesize responses from multiple specialists
- Ensure coherence and consistency
- Highlight key insights and recommendations
- Provide a unified, authoritative response

Guidelines:
- Lead with the most critical information
- Integrate specialist perspectives naturally
- Remove redundancies while preserving nuance
- Conclude with clear, actionable recommendations"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=synthesis_prompt),
        ]

        try:
            response = self.agents[AgentRole.COORDINATOR].invoke(
                {"messages": messages}
            )
            state.final_response = response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            logger.error(f"Error synthesizing responses: {e}")
            # Fallback: concatenate specialist responses
            responses_text = "\n\n".join(
                [f"**{role.value}:**\n{resp}" for role, resp in state.agent_responses.items()]
            )
            state.final_response = f"Specialist Analysis:\n\n{responses_text}"

        logger.debug("Responses synthesized successfully")
        return state

    def _prepare_detection_prompt(self, state: MultiAgentState) -> str:
        """Prepare context for detection analyst."""
        detection_info = "No detection data available."
        if state.detection_data:
            detection_info = json.dumps(state.detection_data, indent=2, default=str)

        return f"""Analyze the following detection data from traffic surveillance:

Detection Data:
{detection_info}

User Query: {state.query}

Provide a detailed analysis of what's detected in the scene."""

    def _prepare_incident_prompt(self, state: MultiAgentState) -> str:
        """Prepare context for incident responder."""
        incident_info = "No incident data available."
        if state.incident_data:
            incident_info = json.dumps(state.incident_data, indent=2, default=str)

        detection_info = ""
        if state.detection_data:
            detection_info = f"\n\nDetection Context:\n{json.dumps(state.detection_data, indent=2, default=str)}"

        return f"""Analyze the following traffic incidents:

Incident Data:
{incident_info}{detection_info}

User Query: {state.query}

Assess severity, impacts, and recommended responses."""

    def _prepare_report_prompt(self, state: MultiAgentState) -> str:
        """Prepare context for report generator."""
        all_data = {
            "detection": state.detection_data or [],
            "incidents": state.incident_data or [],
            "tracks": state.track_data or [],
            "context": state.context_data,
        }

        return f"""Generate a comprehensive report based on the following traffic data:

{json.dumps(all_data, indent=2, default=str)}

User Query: {state.query}

Create a well-structured report with key metrics and insights."""

    def _prepare_prediction_prompt(self, state: MultiAgentState) -> str:
        """Prepare context for predictive analyst."""
        historical_context = json.dumps(state.context_data, indent=2, default=str) if state.context_data else "{}"

        return f"""Analyze traffic patterns and make predictions:

Current Data:
- Detections: {len(state.detection_data or [])} objects
- Incidents: {len(state.incident_data or [])} active
- Tracks: {len(state.track_data or [])} vehicles tracked

Historical Context:
{historical_context}

User Query: {state.query}

Identify patterns, predict future conditions, and recommend optimizations."""

    def _build_synthesis_prompt(self, state: MultiAgentState) -> str:
        """Build synthesis prompt from specialist responses."""
        responses_text = ""
        for role, response in state.agent_responses.items():
            responses_text += f"\n**{role.value.replace('_', ' ').title()}:**\n{response}\n"

        return f"""Synthesize these specialist analyses into a cohesive response:

Original Query: {state.query}

Specialist Responses:
{responses_text}

Provide a unified response that integrates all perspectives."""

    async def process(
        self,
        query: str,
        detection_data: Optional[List[Dict[str, Any]]] = None,
        incident_data: Optional[List[Dict[str, Any]]] = None,
        track_data: Optional[List[Dict[str, Any]]] = None,
        context_data: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process a query through the multi-agent system.

        Args:
            query: User's natural language query
            detection_data: Current detection results
            incident_data: Current incident data
            track_data: Current tracking data
            context_data: Additional context (historical data, config, etc.)
            session_id: Session identifier for tracking

        Returns:
            Dictionary containing:
                - final_response: Synthesized response from all agents
                - query_type: Classified query type
                - agents_used: List of agents that processed the query
                - agent_responses: Individual responses from each agent
                - metadata: Additional metadata (session_id, timestamp, etc.)
        """
        # Initialize state
        state = MultiAgentState(
            query=query,
            detection_data=detection_data,
            incident_data=incident_data,
            track_data=track_data,
            context_data=context_data or {},
            session_id=session_id,
            timestamp=None,  # Would be set in real implementation
        )

        try:
            # Run the graph synchronously (convert to sync for LangGraph)
            # Note: For true async, would need async LangGraph support
            final_state = await asyncio.to_thread(self.graph.invoke, state.__dict__)

            # Convert result back to proper state
            if isinstance(final_state, dict):
                result_state = MultiAgentState(**final_state)
            else:
                result_state = final_state

            return {
                "final_response": result_state.final_response,
                "query_type": result_state.query_type.value,
                "agents_used": [a.value for a in result_state.assigned_agents],
                "agent_responses": {
                    k.value: v for k, v in result_state.agent_responses.items()
                },
                "metadata": {
                    "session_id": session_id,
                    "query_classified": True,
                    "synthesis_complete": True,
                },
            }

        except Exception as e:
            logger.error(f"Error processing query through multi-agent system: {e}")
            return {
                "final_response": f"Error processing query: {str(e)}",
                "query_type": "error",
                "agents_used": [],
                "agent_responses": {},
                "metadata": {
                    "session_id": session_id,
                    "error": str(e),
                },
            }

    def get_system_info(self) -> Dict[str, Any]:
        """
        Get information about the multi-agent system.

        Returns:
            Dictionary with system configuration and capabilities
        """
        return {
            "system_name": "Multimodal Traffic Intelligence Multi-Agent System",
            "version": "1.0.0",
            "agents": [
                {
                    "role": role.value,
                    "description": self._get_agent_description(role),
                    "temperature": 0.3 if role == AgentRole.COORDINATOR else 0.3,
                }
                for role in AgentRole
            ],
            "query_types": [qt.value for qt in QueryType],
            "capabilities": [
                "Real-time detection analysis",
                "Incident severity assessment",
                "Traffic pattern prediction",
                "Comprehensive report generation",
                "Multi-perspective synthesis",
            ],
        }

    @staticmethod
    def _get_agent_description(role: AgentRole) -> str:
        """Get description for an agent role."""
        descriptions = {
            AgentRole.COORDINATOR: "Routes queries and synthesizes specialist responses",
            AgentRole.DETECTION_ANALYST: "Analyzes object detection results and patterns",
            AgentRole.INCIDENT_RESPONDER: "Assesses incidents and recommends responses",
            AgentRole.REPORT_GENERATOR: "Creates structured reports with statistics",
            AgentRole.PREDICTIVE_ANALYST: "Forecasts trends and suggests optimizations",
        }
        return descriptions.get(role, "Specialized traffic intelligence agent")
