"""
LangGraph agent adapter for traffic analysis.

Provides a simplified interface to the TrafficAnalysisGraph for processing
user messages, maintaining conversation history, and handling LLM errors.
"""

import logging
import os
from typing import Optional, Dict, Any
from collections import defaultdict

try:
    from sqlalchemy.ext.asyncio import AsyncSession
except ImportError:
    AsyncSession = None

logger = logging.getLogger(__name__)

# In-memory conversation history per session (can be persisted to DB later)
_conversation_history = defaultdict(list)


async def _build_session_context(session_id: str) -> str:
    """Query the database and build a plain-text context for the LLM."""
    try:
        from database.queries import get_detection_summary, _get_db
        async with _get_db() as db:
            summary = await get_detection_summary(db, session_id)
            if not summary:
                return "No detections recorded for this session yet."

            parts = []
            total = summary.get("total_detections", 0)
            parts.append(f"Total detection events: {total}")

            vt = summary.get("vehicle_type_breakdown", {})
            if vt:
                breakdown = ", ".join(f"{k}: {v}" for k, v in vt.items() if v)
                parts.append(f"Vehicle type breakdown: {breakdown}")

            conf = summary.get("confidence_stats", {})
            if conf and conf.get("avg"):
                parts.append(f"Average detection confidence: {conf['avg']:.1%}")

            return "\n".join(parts)
    except Exception as e:
        logger.warning(f"Could not load session context from DB: {e}")
        return "Detection data not available (database query failed)."


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

        # Fetch real detection data from DB so the LLM can answer accurately
        context = await _build_session_context(session_id)

        # Build conversation history for multi-turn context (last 3 exchanges)
        history = _conversation_history[session_id][-6:]
        _conversation_history[session_id].append({"role": "user", "content": message})

        query_type = _determine_query_type(message)

        # Call Gemini directly with the real data — this is more reliable than
        # routing through the graph which has tools that lack session_id context.
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

            google_api_key = os.getenv("GOOGLE_API_KEY")
            if not google_api_key:
                raise ValueError("GOOGLE_API_KEY not set")

            llm = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                google_api_key=google_api_key,
                temperature=0.3,
            )

            system_content = f"""You are a traffic intelligence analyst. Answer questions about the traffic monitoring session.

SESSION DATA (session_id: {session_id}):
{context}

Rules:
- Answer based only on the data above.
- Be concise and specific — cite actual numbers.
- If the data shows 0 detections, say so clearly.
- Do not fabricate numbers or events not present in the data."""

            msgs = [SystemMessage(content=system_content)]
            for h in history:
                if h["role"] == "user":
                    msgs.append(HumanMessage(content=h["content"]))
                else:
                    msgs.append(AIMessage(content=h["content"]))
            msgs.append(HumanMessage(content=message))

            llm_response = await llm.ainvoke(msgs)
            response_text = llm_response.content

        except Exception as llm_error:
            logger.error(f"LLM call failed: {llm_error}", exc_info=True)
            # Plain-text fallback using only the DB context
            response_text = (
                f"Here is the raw session data (LLM unavailable: {llm_error}):\n\n{context}"
            )

        _conversation_history[session_id].append({"role": "assistant", "content": response_text})

        logger.info(f"Message processed successfully for session {session_id}")
        return {
            "response": response_text,
            "query_type": query_type,
            "data": {"context": context},
            "session_id": session_id,
            "conversation_turn": len(_conversation_history[session_id]),
        }

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
