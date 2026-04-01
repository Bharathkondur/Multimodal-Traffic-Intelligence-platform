"""
WebSocket routes for real-time communication with traffic intelligence system.

Provides real-time detection streaming, incident alerts, and chat interactions.
"""

import logging
import json
from typing import Dict, Set
from datetime import datetime

from fastapi import APIRouter, WebSocketException, status
from fastapi.websockets import WebSocket

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

# Connection management
active_connections: Dict[str, Set[WebSocket]] = {}


class ConnectionManager:
    """
    Manages WebSocket connections and message broadcasting.

    Handles subscription to detection and incident channels,
    routing messages to connected clients.
    """

    def __init__(self):
        """Initialize connection manager."""
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        """
        Register a new WebSocket connection.

        Args:
            session_id: Session identifier
            websocket: WebSocket connection
        """
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = set()
        self.active_connections[session_id].add(websocket)
        logger.info(f"Client connected to session {session_id}")

    def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        """
        Unregister a WebSocket connection.

        Args:
            session_id: Session identifier
            websocket: WebSocket connection
        """
        if session_id in self.active_connections:
            self.active_connections[session_id].discard(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
        logger.info(f"Client disconnected from session {session_id}")

    async def broadcast_detection(self, session_id: str, detection_data: Dict) -> None:
        """
        Broadcast detection to all connected clients of a session.

        Args:
            session_id: Session identifier
            detection_data: Detection information
        """
        if session_id not in self.active_connections:
            return

        message = {
            "type": "detection",
            "data": detection_data,
            "timestamp": datetime.utcnow().isoformat(),
        }

        disconnected = set()
        for connection in self.active_connections[session_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Broadcast error: {e}")
                disconnected.add(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(session_id, conn)

    async def broadcast_incident(self, session_id: str, incident_data: Dict) -> None:
        """
        Broadcast incident alert to all connected clients.

        Args:
            session_id: Session identifier
            incident_data: Incident information
        """
        if session_id not in self.active_connections:
            return

        message = {
            "type": "incident",
            "data": incident_data,
            "timestamp": datetime.utcnow().isoformat(),
        }

        disconnected = set()
        for connection in self.active_connections[session_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Broadcast error: {e}")
                disconnected.add(connection)

        for conn in disconnected:
            self.disconnect(session_id, conn)

    async def broadcast_status(self, session_id: str, status_data: Dict) -> None:
        """
        Broadcast status update to all connected clients.

        Args:
            session_id: Session identifier
            status_data: Status information
        """
        if session_id not in self.active_connections:
            return

        message = {
            "type": "status",
            "data": status_data,
            "timestamp": datetime.utcnow().isoformat(),
        }

        disconnected = set()
        for connection in self.active_connections[session_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Broadcast error: {e}")
                disconnected.add(connection)

        for conn in disconnected:
            self.disconnect(session_id, conn)


# Global connection manager
manager = ConnectionManager()


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    """
    WebSocket endpoint for real-time traffic intelligence data.

    Provides:
        - Real-time detection streaming
        - Incident alerts
        - Processing status updates
        - Chat message routing

    Connection Protocol:
        Client messages:
            {
                "type": "subscribe",
                "channels": ["detections", "incidents", "status"]
            }
            {
                "type": "chat",
                "message": "What is the traffic level?"
            }

        Server messages:
            {
                "type": "detection",
                "data": {...},
                "timestamp": "2026-03-31T10:30:45.123Z"
            }
            {
                "type": "incident",
                "data": {...},
                "timestamp": "2026-03-31T10:30:45.123Z"
            }
            {
                "type": "status",
                "data": {...},
                "timestamp": "2026-03-31T10:30:45.123Z"
            }
            {
                "type": "chat_response",
                "message": "...",
                "timestamp": "2026-03-31T10:30:45.123Z"
            }

    Args:
        websocket: WebSocket connection
        session_id: Session identifier

    Raises:
        WebSocketException: On connection errors
    """
    try:
        from database import get_session as db_get_session
        from agents.langgraph_agent import process_message

        # Verify session exists
        session = await db_get_session(session_id)
        if not session:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            logger.warning(f"Attempted connection to non-existent session {session_id}")
            return

        # Connect client
        await manager.connect(session_id, websocket)

        # Send connection success
        await websocket.send_json(
            {
                "type": "connected",
                "session_id": session_id,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

        # Handle incoming messages
        while True:
            try:
                data = await websocket.receive_json()
                message_type = data.get("type")

                if message_type == "subscribe":
                    """Subscribe to channels."""
                    channels = data.get("channels", [])
                    await websocket.send_json(
                        {
                            "type": "subscribed",
                            "channels": channels,
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )
                    logger.info(
                        f"Client subscribed to {channels} for session {session_id}"
                    )

                elif message_type == "chat":
                    """Route chat message to agent."""
                    user_message = data.get("message", "")
                    if not user_message:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": "Empty message",
                                "timestamp": datetime.utcnow().isoformat(),
                            }
                        )
                        continue

                    try:
                        # Process through agent
                        response = await process_message(
                            session_id=session_id,
                            user_message=user_message,
                            include_context=True,
                        )

                        await websocket.send_json(
                            {
                                "type": "chat_response",
                                "message": response.get("message", ""),
                                "sources": response.get("sources", []),
                                "confidence": response.get("confidence", 1.0),
                                "timestamp": datetime.utcnow().isoformat(),
                            }
                        )
                    except Exception as e:
                        logger.error(f"Chat processing error: {e}")
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": "Chat processing failed",
                                "timestamp": datetime.utcnow().isoformat(),
                            }
                        )

                elif message_type == "ping":
                    """Respond to ping."""
                    await websocket.send_json(
                        {
                            "type": "pong",
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )

                else:
                    logger.warning(f"Unknown message type: {message_type}")
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": f"Unknown message type: {message_type}",
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )

            except json.JSONDecodeError:
                logger.error("Invalid JSON received")
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Invalid JSON",
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )
            except Exception as e:
                logger.error(f"Message processing error: {e}")
                break

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        raise WebSocketException(code=status.WS_1011_SERVER_ERROR)

    finally:
        manager.disconnect(session_id, websocket)
        logger.info(f"WebSocket connection closed for session {session_id}")


async def broadcast_detection(session_id: str, detection: Dict) -> None:
    """
    Broadcast detection to all connected clients of a session.

    Called by detection pipeline after detecting objects.

    Args:
        session_id: Session identifier
        detection: Detection data dictionary
    """
    await manager.broadcast_detection(session_id, detection)


async def broadcast_incident(session_id: str, incident: Dict) -> None:
    """
    Broadcast incident alert to all connected clients.

    Called by incident detection pipeline.

    Args:
        session_id: Session identifier
        incident: Incident data dictionary
    """
    await manager.broadcast_incident(session_id, incident)


async def broadcast_status(session_id: str, status_update: Dict) -> None:
    """
    Broadcast processing status to all connected clients.

    Args:
        session_id: Session identifier
        status_update: Status data dictionary
    """
    await manager.broadcast_status(session_id, status_update)
