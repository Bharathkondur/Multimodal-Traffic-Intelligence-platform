"""
LangGraph agent adapter for traffic analysis.

Provides a simplified interface to the TrafficAnalysisGraph for processing
user messages, maintaining conversation history, and handling LLM errors.
"""

import logging
from typing import Optional, Dict, Any
from collections import defaultdict

try:
    from sqlalchemy.ext.asyncio import AsyncSession
except ImportError:
    AsyncSession = None

logger = logging.getLogger(__name__)

# In-memory conversation history per session (can be persisted to DB later)
_conversation_history = defaultdict(list)


async def process_message(
    session_id: str,
    message: str,
    db_session: Optional[object] = None,
) -> Dict[str, Any]:
    """
    Process a user message through the LangGraph traffic analysis agent.

    Routes the message through the TrafficAnalysisGraph, maintains conversation
    history, and returns structured response with query type and data.

    Args:
        session_id: Unique identifier for the traffic session/conversation
        message: User message or query
        db_session: SQLAlchemy AsyncSession for database queries (optional)

    Returns:
        Dictionary containing:
            {
                "response": str,           # Generated response text
                "query_type": str,         # Query type (question, report, alert, etc.)
                "data": dict,              # Query results and analysis data
                "session_id": str,         # Session identifier
                "conversation_turn": int,  # Turn number in conversation
            }

    Raises:
        Exception: Logs errors and returns fallback response

    Processing:
        1. Adds message to conversation history
        2. Identifies query type
        3. Routes through appropriate agent node
        4. Retrieves detection data if needed
        5. Calls LLM for analysis
        6. Returns structured response

    Example:
        >>> response = await process_message(
        ...     session_id="session_123",
        ...     message="What's the traffic situation?",
        ... )
        >>> print(response["response"])
        >>> print(response["query_type"])
    """
    try:
        logger.info(f"Processing message for session {session_id}: {message[:100]}")

        # Import LangGraph agent
        try:
            from agents.graph import TrafficAnalysisGraph, QueryType
        except ImportError:
            logger.error("Failed to import TrafficAnalysisGraph")
            return _fallback_response(
                session_id,
                "Failed to initialize agent",
            )

        # Initialize LangGraph agent
        try:
            logger.debug("Initializing TrafficAnalysisGraph")
            agent = TrafficAnalysisGraph(db_session=db_session)
        except Exception as e:
            logger.error(f"Failed to initialize agent: {e}")
            return _fallback_response(session_id, f"Agent initialization error: {e}")

        # Add message to conversation history
        _conversation_history[session_id].append({
            "role": "user",
            "content": message,
        })

        # Determine query type
        query_type = _determine_query_type(message)
        logger.debug(f"Detected query type: {query_type}")

        # Prepare input for agent
        agent_input = {
            "user_query": message,
            "query_type": query_type,
            "session_id": session_id,
            "messages": [],
        }

        # Process through agent
        try:
            logger.debug("Running agent graph")
            output = await agent.arun(agent_input)

            # Extract response
            if isinstance(output, dict):
                response_text = output.get(
                    "response",
                    output.get("final_response", "Analysis complete"),
                )
                analysis_data = output.get("data", {})
            else:
                response_text = str(output)
                analysis_data = {}

        except Exception as agent_error:
            logger.error(f"Agent execution error: {agent_error}", exc_info=True)
            response_text = f"Error during analysis: {agent_error}"
            analysis_data = {}

        # Add response to conversation history
        _conversation_history[session_id].append({
            "role": "assistant",
            "content": response_text,
        })

        # Build response
        response = {
            "response": response_text,
            "query_type": query_type,
            "data": analysis_data,
            "session_id": session_id,
            "conversation_turn": len(_conversation_history[session_id]),
        }

        logger.info(f"Message processed successfully for session {session_id}")
        return response

    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        return _fallback_response(session_id, f"Processing error: {e}")


def _determine_query_type(message: str) -> str:
    """
    Determine the type of query from the message.

    Args:
        message: User message

    Returns:
        Query type string

    Types:
        - "report": Message requests a report (shift, incident, summary)
        - "alert": Message relates to alerts or incidents
        - "scene": Message asks about current scene or situation
        - "analysis": Message requests data analysis
        - "question": General question about traffic data
        - "unknown": Query type cannot be determined
    """
    message_lower = message.lower()

    # Check for report keywords
    if any(
        keyword in message_lower
        for keyword in ["report", "summary", "analysis", "statistics"]
    ):
        return "report"

    # Check for alert keywords
    if any(
        keyword in message_lower
        for keyword in ["alert", "incident", "accident", "collision", "emergency"]
    ):
        return "alert"

    # Check for scene keywords
    if any(
        keyword in message_lower
        for keyword in ["scene", "what's happening", "current", "now", "status"]
    ):
        return "scene"

    # Check for analysis keywords
    if any(
        keyword in message_lower
        for keyword in ["analyze", "compare", "trend", "pattern", "count"]
    ):
        return "analysis"

    # Default to question
    return "question"


def _fallback_response(
    session_id: str,
    error_message: str,
) -> Dict[str, Any]:
    """
    Generate a fallback response when agent fails.

    Args:
        session_id: Session identifier
        error_message: Error description

    Returns:
        Fallback response dictionary
    """
    response = {
        "response": f"I encountered an issue processing your request: {error_message}. "
                    "Please try again or contact support.",
        "query_type": "unknown",
        "data": {"error": error_message},
        "session_id": session_id,
        "conversation_turn": len(_conversation_history[session_id]) + 1,
    }
    return response


def get_conversation_history(session_id: str) -> list:
    """
    Get conversation history for a session.

    Args:
        session_id: Session identifier

    Returns:
        List of conversation messages
    """
    return _conversation_history.get(session_id, [])


def clear_conversation_history(session_id: str) -> None:
    """
    Clear conversation history for a session.

    Args:
        session_id: Session identifier
    """
    if session_id in _conversation_history:
        del _conversation_history[session_id]
        logger.debug(f"Cleared conversation history for session {session_id}")


def get_all_active_sessions() -> list[str]:
    """
    Get list of sessions with active conversations.

    Returns:
        List of session IDs
    """
    return list(_conversation_history.keys())
