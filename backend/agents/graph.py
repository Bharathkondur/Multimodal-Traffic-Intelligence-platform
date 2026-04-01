"""
LangGraph-based Traffic Intelligence Agent.

Implements the main agent graph with state management, node definitions,
and conditional routing for different query types.
"""

import logging
from typing import Any, Optional, AsyncGenerator
from enum import Enum
from dataclasses import dataclass, field

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.language_model import BaseLLM
from langgraph.graph import StateGraph, START, END
from langgraph.types import StreamWriter

try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None

try:
    from langchain_ollama import ChatOllama
except ImportError:
    ChatOllama = None

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    ChatGoogleGenerativeAI = None

from agents.tools import (
    query_detections,
    get_vehicle_count,
    get_incident_report,
    get_traffic_flow,
    generate_shift_report,
    compare_periods,
    get_current_scene,
)
from agents.prompts import (
    TRAFFIC_ANALYST_SYSTEM,
    REPORT_GENERATOR,
    INCIDENT_ANALYZER,
    SCENE_DESCRIBER,
)
from agents.rag import DetectionRAG

logger = logging.getLogger(__name__)


class QueryType(str, Enum):
    """Types of queries the agent can handle."""
    QUESTION = "question"
    REPORT = "report"
    ALERT = "alert"
    SCENE = "scene"
    ANALYSIS = "analysis"
    UNKNOWN = "unknown"


class LLMBackend(str, Enum):
    """Supported LLM backends."""
    OPENAI = "openai"
    OLLAMA = "ollama"
    GEMINI = "gemini"


@dataclass
class TrafficAgentState:
    """State schema for the traffic analysis graph."""
    # Core message history
    messages: list[BaseMessage] = field(default_factory=list)

    # Current query and metadata
    user_query: str = ""
    query_type: QueryType = QueryType.UNKNOWN

    # Retrieved context and data
    context: str = ""
    retrieved_data: dict[str, Any] = field(default_factory=dict)
    detections: list[dict[str, Any]] = field(default_factory=list)

    # Analysis results
    reasoning: str = ""
    analysis_results: dict[str, Any] = field(default_factory=dict)

    # Final response
    response: str = ""
    is_streaming: bool = False


class LLMFactory:
    """Factory for creating LLM instances."""

    @staticmethod
    def create_llm(
        backend: LLMBackend = LLMBackend.OPENAI,
        model: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs,
    ) -> BaseLLM:
        """
        Create LLM instance.

        Args:
            backend: LLM backend (openai or ollama)
            model: Model name (e.g., "gpt-4o" or "llama3")
            temperature: Generation temperature
            **kwargs: Additional model arguments

        Returns:
            LLM instance

        Raises:
            ValueError: If backend not available or invalid
        """
        if backend == LLMBackend.OPENAI:
            if ChatOpenAI is None:
                raise ValueError(
                    "OpenAI backend requested but langchain-openai not installed. "
                    "Install with: pip install langchain-openai"
                )
            return ChatOpenAI(
                model=model or "gpt-4o",
                temperature=temperature,
                **kwargs,
            )

        elif backend == LLMBackend.OLLAMA:
            if ChatOllama is None:
                raise ValueError(
                    "Ollama backend requested but langchain-ollama not installed. "
                    "Install with: pip install langchain-ollama"
                )
            return ChatOllama(
                model=model or "llama3",
                temperature=temperature,
                **kwargs,
            )

        elif backend == LLMBackend.GEMINI:
            if ChatGoogleGenerativeAI is None:
                raise ValueError(
                    "Gemini backend requested but langchain-google-genai not installed. "
                    "Install with: pip install langchain-google-genai"
                )
            import os
            api_key = kwargs.pop("google_api_key", None) or os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise ValueError(
                    "Gemini backend requires GOOGLE_API_KEY environment variable. "
                    "Get a free key at https://aistudio.google.com/apikey"
                )
            return ChatGoogleGenerativeAI(
                model=model or "gemini-2.0-flash",
                temperature=temperature,
                google_api_key=api_key,
                **kwargs,
            )

        else:
            raise ValueError(f"Unknown LLM backend: {backend}")


class TrafficAnalysisGraph:
    """
    LangGraph-based Traffic Intelligence Agent.

    Orchestrates traffic analysis through a multi-node graph with:
    - Query analysis and classification
    - Data retrieval and context building
    - Reasoning and analysis
    - Response generation with streaming support

    Supports both OpenAI GPT-4o and Ollama/local LLMs via configuration.
    """

    def __init__(
        self,
        llm_backend: LLMBackend = LLMBackend.OPENAI,
        llm_model: Optional[str] = None,
        temperature: float = 0.7,
        enable_streaming: bool = False,
        rag_enabled: bool = True,
    ):
        """
        Initialize Traffic Analysis Graph.

        Args:
            llm_backend: LLM backend (openai or ollama)
            llm_model: Model name (defaults based on backend)
            temperature: LLM temperature
            enable_streaming: Enable streaming responses
            rag_enabled: Enable RAG for semantic search
        """
        self.llm_backend = llm_backend
        self.llm_model = llm_model
        self.temperature = temperature
        self.enable_streaming = enable_streaming

        # Initialize LLM
        try:
            self.llm = LLMFactory.create_llm(
                backend=llm_backend,
                model=llm_model,
                temperature=temperature,
            )
            logger.info(
                f"Initialized LLM: backend={llm_backend.value}, "
                f"model={llm_model or 'default'}"
            )
        except ValueError as e:
            logger.warning(f"Failed to initialize LLM: {e}")
            self.llm = None

        # Initialize RAG
        self.rag = DetectionRAG() if rag_enabled else None

        # Bind tools to LLM
        self.tools = [
            query_detections,
            get_vehicle_count,
            get_incident_report,
            get_traffic_flow,
            generate_shift_report,
            compare_periods,
            get_current_scene,
        ]

        self.llm_with_tools = self.llm.bind_tools(self.tools) if self.llm else None

        # Build graph
        self.graph = self._build_graph()

        logger.info("Initialized TrafficAnalysisGraph")

    def _build_graph(self) -> StateGraph:
        """
        Build LangGraph StateGraph.

        Creates the agent graph with nodes and conditional edges.
        """
        graph = StateGraph(TrafficAgentState)

        # Add nodes
        graph.add_node("analyze_query", self._analyze_query)
        graph.add_node("retrieve_data", self._retrieve_data)
        graph.add_node("reason", self._reason)
        graph.add_node("generate_response", self._generate_response)

        # Add edges
        graph.add_edge(START, "analyze_query")
        graph.add_conditional_edges(
            "analyze_query",
            self._route_after_analysis,
            {
                "question": "retrieve_data",
                "report": "retrieve_data",
                "alert": "retrieve_data",
                "scene": "retrieve_data",
                "analysis": "retrieve_data",
            },
        )
        graph.add_edge("retrieve_data", "reason")
        graph.add_edge("reason", "generate_response")
        graph.add_edge("generate_response", END)

        return graph

    async def _analyze_query(
        self,
        state: TrafficAgentState,
    ) -> dict[str, Any]:
        """
        Analyze user query and determine query type.

        Classifies the query as question, report, alert, scene, or analysis.

        Args:
            state: Current agent state

        Returns:
            Updated state dict
        """
        logger.info(f"Analyzing query: {state.user_query}")

        # Classify query type
        query_type = self._classify_query(state.user_query)
        logger.debug(f"Classified query as: {query_type}")

        # Add user message to history
        messages = state.messages + [HumanMessage(content=state.user_query)]

        return {
            "query_type": query_type,
            "messages": messages,
        }

    async def _retrieve_data(
        self,
        state: TrafficAgentState,
    ) -> dict[str, Any]:
        """
        Retrieve relevant data based on query type.

        Fetches detection events, context, and relevant metrics.

        Args:
            state: Current agent state

        Returns:
            Updated state with retrieved data
        """
        logger.info(f"Retrieving data for {state.query_type.value} query")

        context = ""
        retrieved_data = {}
        detections = []

        try:
            # Use RAG to retrieve relevant detections
            if self.rag:
                context = self.rag.get_context(state.user_query, k=5)
                retrieved_data["rag_context"] = context

            # Retrieve data based on query type
            if state.query_type == QueryType.SCENE:
                retrieved_data["scene"] = await get_current_scene(detail_level="detailed")

            elif state.query_type == QueryType.ALERT:
                retrieved_data["recent_incidents"] = self.rag.retrieve_incidents(
                    hours=1
                ) if self.rag else []

            elif state.query_type == QueryType.REPORT:
                retrieved_data["vehicle_counts"] = await get_vehicle_count(
                    time_range="today"
                )
                retrieved_data["flow_analysis"] = await get_traffic_flow(
                    time_range="today"
                )

            elif state.query_type == QueryType.ANALYSIS:
                retrieved_data["detections"] = self.rag.retrieve(
                    state.user_query, k=10
                ) if self.rag else []
                detections = retrieved_data.get("detections", [])

            logger.debug(
                f"Retrieved data: context_len={len(context)}, "
                f"data_keys={list(retrieved_data.keys())}"
            )

        except Exception as e:
            logger.error(f"Error retrieving data: {e}")

        return {
            "context": context,
            "retrieved_data": retrieved_data,
            "detections": detections,
        }

    async def _reason(
        self,
        state: TrafficAgentState,
    ) -> dict[str, Any]:
        """
        Perform reasoning over retrieved data.

        Analyzes context and data to form insights and conclusions.

        Args:
            state: Current agent state

        Returns:
            Updated state with reasoning
        """
        logger.info("Performing reasoning")

        if not self.llm_with_tools:
            return {
                "reasoning": "LLM not available",
                "analysis_results": {},
            }

        try:
            # Build reasoning prompt
            reasoning_prompt = self._build_reasoning_prompt(state)

            # Call LLM for reasoning
            messages = state.messages + [HumanMessage(content=reasoning_prompt)]
            response = await self.llm_with_tools.ainvoke({"messages": messages})

            reasoning = response.content if hasattr(response, "content") else str(response)

            logger.debug(f"Reasoning complete: {len(reasoning)} chars")

            return {
                "reasoning": reasoning,
                "analysis_results": {
                    "reasoning": reasoning,
                },
            }

        except Exception as e:
            logger.error(f"Error during reasoning: {e}")
            return {
                "reasoning": f"Error during reasoning: {e}",
                "analysis_results": {},
            }

    async def _generate_response(
        self,
        state: TrafficAgentState,
    ) -> dict[str, Any]:
        """
        Generate final response to user query.

        Creates the final response based on analysis and reasoning.

        Args:
            state: Current agent state

        Returns:
            Updated state with response
        """
        logger.info("Generating response")

        if not self.llm:
            return {
                "response": "LLM not available",
            }

        try:
            # Build response prompt
            response_prompt = self._build_response_prompt(state)

            # Get system prompt based on query type
            system_prompt = self._get_system_prompt(state.query_type)

            # Generate response
            messages = state.messages + [HumanMessage(content=response_prompt)]
            response = await self.llm.ainvoke(messages)

            final_response = response.content if hasattr(response, "content") else str(response)

            # Add response to message history
            updated_messages = messages + [AIMessage(content=final_response)]

            logger.info("Response generated successfully")

            return {
                "response": final_response,
                "messages": updated_messages,
            }

        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return {
                "response": f"Error generating response: {e}",
            }

    # ==================== Routing & Classification ====================

    def _classify_query(self, query: str) -> QueryType:
        """
        Classify query type.

        Args:
            query: User query

        Returns:
            QueryType enum value
        """
        query_lower = query.lower()

        # Check for keywords
        if any(word in query_lower for word in ["report", "shift", "summary"]):
            return QueryType.REPORT

        if any(word in query_lower for word in ["alert", "incident", "accident"]):
            return QueryType.ALERT

        if any(word in query_lower for word in ["current", "now", "scene", "happening"]):
            return QueryType.SCENE

        if any(word in query_lower for word in ["analyze", "compare", "trend", "pattern"]):
            return QueryType.ANALYSIS

        if any(word in query_lower for word in ["how", "what", "where", "when", "why"]):
            return QueryType.QUESTION

        return QueryType.QUESTION

    def _route_after_analysis(self, state: TrafficAgentState) -> str:
        """Route to appropriate node after query analysis."""
        return state.query_type.value

    def _get_system_prompt(self, query_type: QueryType) -> str:
        """Get system prompt based on query type."""
        if query_type == QueryType.REPORT:
            return REPORT_GENERATOR
        elif query_type == QueryType.ALERT:
            return INCIDENT_ANALYZER
        elif query_type == QueryType.SCENE:
            return SCENE_DESCRIBER
        else:
            return TRAFFIC_ANALYST_SYSTEM

    # ==================== Prompt Building ====================

    def _build_reasoning_prompt(self, state: TrafficAgentState) -> str:
        """Build prompt for reasoning phase."""
        prompt = f"""Analyze the following traffic query and data:

QUERY: {state.user_query}

CONTEXT:
{state.context}

RETRIEVED DATA:
"""
        for key, value in state.retrieved_data.items():
            prompt += f"\n{key}:\n{value}\n"

        prompt += """
Please analyze this information and provide:
1. Key observations
2. Relevant patterns
3. Important metrics
4. Potential issues or concerns
"""
        return prompt

    def _build_response_prompt(self, state: TrafficAgentState) -> str:
        """Build prompt for response generation."""
        prompt = f"""Based on the following analysis, provide a comprehensive response:

ORIGINAL QUERY: {state.user_query}

REASONING:
{state.reasoning}

RETRIEVED DETECTIONS: {len(state.detections)}

Please provide a clear, professional response to the user's query that:
1. Directly addresses their question or request
2. Includes specific data points and metrics
3. Provides actionable insights
4. Highlights any concerns or anomalies
"""
        return prompt

    # ==================== Streaming Support ====================

    async def stream(
        self,
        query: str,
    ) -> AsyncGenerator[str, None]:
        """
        Stream response from agent.

        Yields response tokens as they're generated.

        Args:
            query: User query

        Yields:
            Response tokens
        """
        logger.info(f"Starting stream for query: {query}")

        initial_state = TrafficAgentState(
            user_query=query,
            is_streaming=True,
            messages=[],
        )

        # Create stream writer for output
        output = []

        def write_output(value: str) -> None:
            output.append(value)

        try:
            # Execute graph (would stream in actual LangGraph implementation)
            final_state = await self._execute_graph(initial_state)

            # Yield response in chunks
            response = final_state.response
            chunk_size = 50

            for i in range(0, len(response), chunk_size):
                chunk = response[i:i + chunk_size]
                yield chunk

        except Exception as e:
            logger.error(f"Error during streaming: {e}")
            yield f"Error: {e}"

    # ==================== Graph Execution ====================

    async def _execute_graph(
        self,
        initial_state: TrafficAgentState,
    ) -> TrafficAgentState:
        """
        Execute the graph with given initial state.

        Args:
            initial_state: Initial state

        Returns:
            Final state after graph execution
        """
        state = initial_state

        # Execute nodes in sequence
        state_update = await self._analyze_query(state)
        state = TrafficAgentState(**{**state.__dict__, **state_update})

        state_update = await self._retrieve_data(state)
        state = TrafficAgentState(**{**state.__dict__, **state_update})

        state_update = await self._reason(state)
        state = TrafficAgentState(**{**state.__dict__, **state_update})

        state_update = await self._generate_response(state)
        state = TrafficAgentState(**{**state.__dict__, **state_update})

        return state

    async def invoke(
        self,
        query: str,
    ) -> dict[str, Any]:
        """
        Invoke agent with query.

        Args:
            query: User query

        Returns:
            Final state dictionary
        """
        logger.info(f"Invoking agent with query: {query}")

        initial_state = TrafficAgentState(
            user_query=query,
            messages=[],
        )

        final_state = await self._execute_graph(initial_state)

        return {
            "query": query,
            "query_type": final_state.query_type.value,
            "response": final_state.response,
            "context_used": len(final_state.context) > 0,
            "detections_retrieved": len(final_state.detections),
            "messages": len(final_state.messages),
        }

    def get_graph_schema(self) -> dict[str, Any]:
        """Get schema of the graph."""
        return {
            "nodes": ["analyze_query", "retrieve_data", "reason", "generate_response"],
            "edges": [
                ("start", "analyze_query"),
                ("analyze_query", "retrieve_data"),
                ("retrieve_data", "reason"),
                ("reason", "generate_response"),
                ("generate_response", "end"),
            ],
            "query_types": [qt.value for qt in QueryType],
            "llm_backend": self.llm_backend.value,
            "rag_enabled": self.rag is not None,
        }
