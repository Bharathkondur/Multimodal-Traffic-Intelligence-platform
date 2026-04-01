"""
WebSocket Manager for real-time communication with traffic monitoring clients.

Handles connection lifecycle management, multi-channel broadcasting, rate limiting,
message serialization, and integration with the LangGraph agent for chat processing.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List, Set, Callable, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class Channel(str, Enum):
    """Available WebSocket channels for different types of messages."""
    DETECTIONS = "detections"
    INCIDENTS = "incidents"
    METRICS = "metrics"
    CHAT = "chat"


@dataclass
class BroadcastMessage:
    """Message to broadcast to connected clients."""
    channel: Channel
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    sender_id: Optional[str] = None

    def to_json(self) -> str:
        """Serialize message to JSON."""
        return json.dumps({
            "channel": self.channel.value,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "sender_id": self.sender_id,
        }, default=str)

    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary."""
        return {
            "channel": self.channel.value,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "sender_id": self.sender_id,
        }


@dataclass
class ClientConnection:
    """Represents a connected WebSocket client."""
    client_id: str
    websocket: Any
    subscribed_channels: Set[Channel] = field(default_factory=set)
    connected_at: datetime = field(default_factory=datetime.utcnow)
    last_message_at: datetime = field(default_factory=datetime.utcnow)
    message_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    async def send_json(self, data: Dict[str, Any]) -> bool:
        """
        Send JSON message to client.

        Args:
            data: Dictionary to send as JSON

        Returns:
            True if successful, False otherwise
        """
        try:
            message = json.dumps(data, default=str)
            await self.websocket.send_text(message)
            return True
        except Exception as e:
            logger.error(f"Error sending message to {self.client_id}: {e}")
            return False

    async def send_message(self, message: BroadcastMessage) -> bool:
        """
        Send broadcast message to client.

        Args:
            message: Broadcast message

        Returns:
            True if successful, False otherwise
        """
        return await self.send_json(message.to_dict())

    def is_subscribed_to(self, channel: Channel) -> bool:
        """Check if client is subscribed to a channel."""
        return channel in self.subscribed_channels

    def update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_message_at = datetime.utcnow()
        self.message_count += 1


@dataclass
class RateLimiter:
    """Rate limiter for channel broadcasts."""
    channel: Channel
    max_messages_per_second: int = 100
    _timestamps: List[float] = field(default_factory=list)
    _last_cleanup: float = field(default_factory=time.time)

    def is_allowed(self) -> bool:
        """Check if message is within rate limit."""
        current_time = time.time()

        # Clean old timestamps every second
        if current_time - self._last_cleanup > 1.0:
            cutoff = current_time - 1.0
            self._timestamps = [ts for ts in self._timestamps if ts > cutoff]
            self._last_cleanup = current_time

        if len(self._timestamps) >= self.max_messages_per_second:
            return False

        self._timestamps.append(current_time)
        return True


class ConnectionManager:
    """
    Manages WebSocket connections and multi-channel broadcasting.

    Handles client connection lifecycle, channel subscriptions, message broadcasting
    with rate limiting, and integration with traffic analysis systems.
    """

    def __init__(self, chat_agent_callback: Optional[Callable] = None) -> None:
        """
        Initialize the connection manager.

        Args:
            chat_agent_callback: Async callback for routing chat messages to LangGraph agent
        """
        # Client management
        self._clients: Dict[str, ClientConnection] = {}
        self._client_lock = asyncio.Lock()

        # Channel subscriptions
        self._channel_subscriptions: Dict[Channel, Set[str]] = {
            channel: set() for channel in Channel
        }

        # Rate limiters per channel
        self._rate_limiters: Dict[Channel, RateLimiter] = {
            Channel.DETECTIONS: RateLimiter(Channel.DETECTIONS, max_messages_per_second=1000),
            Channel.INCIDENTS: RateLimiter(Channel.INCIDENTS, max_messages_per_second=100),
            Channel.METRICS: RateLimiter(Channel.METRICS, max_messages_per_second=10),
            Channel.CHAT: RateLimiter(Channel.CHAT, max_messages_per_second=50),
        }

        # Message history for debugging
        self._message_history: Dict[Channel, List[BroadcastMessage]] = {
            channel: [] for channel in Channel
        }
        self._max_history_size = 100

        # Chat agent callback
        self.chat_agent_callback = chat_agent_callback

        # Statistics
        self._stats = {
            "total_connections": 0,
            "total_messages_sent": 0,
            "total_messages_dropped": 0,
            "start_time": datetime.utcnow(),
        }

        logger.info("ConnectionManager initialized")

    async def connect(
        self,
        client_id: str,
        websocket: Any,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Register a new WebSocket client connection.

        Args:
            client_id: Unique client identifier
            websocket: WebSocket connection object
            metadata: Optional client metadata (session_id, user_info, etc.)
        """
        async with self._client_lock:
            if client_id in self._clients:
                logger.warning(f"Client {client_id} already connected, replacing")
                await self.disconnect(client_id)

            client = ClientConnection(
                client_id=client_id,
                websocket=websocket,
                metadata=metadata or {}
            )
            self._clients[client_id] = client
            self._stats["total_connections"] += 1

            logger.info(
                f"Client {client_id} connected. "
                f"Total clients: {len(self._clients)}"
            )

            # Send welcome message
            await client.send_json({
                "type": "connection",
                "message": "Connected to traffic monitoring system",
                "client_id": client_id,
                "timestamp": datetime.utcnow().isoformat(),
            })

    async def disconnect(self, client_id: str) -> None:
        """
        Unregister a disconnected WebSocket client.

        Args:
            client_id: Client identifier to disconnect
        """
        async with self._client_lock:
            if client_id not in self._clients:
                return

            client = self._clients[client_id]

            # Unsubscribe from all channels
            for channel in list(client.subscribed_channels):
                self._channel_subscriptions[channel].discard(client_id)

            del self._clients[client_id]
            logger.info(f"Client {client_id} disconnected. Total clients: {len(self._clients)}")

    async def subscribe(self, client_id: str, channel: Channel) -> bool:
        """
        Subscribe client to a channel.

        Args:
            client_id: Client identifier
            channel: Channel to subscribe to

        Returns:
            True if successful, False if client not found
        """
        async with self._client_lock:
            if client_id not in self._clients:
                logger.warning(f"Client {client_id} not found for subscription")
                return False

            client = self._clients[client_id]
            client.subscribed_channels.add(channel)
            self._channel_subscriptions[channel].add(client_id)

            logger.info(
                f"Client {client_id} subscribed to {channel.value}. "
                f"Channel subscribers: {len(self._channel_subscriptions[channel])}"
            )

            # Send confirmation
            await client.send_json({
                "type": "subscription",
                "channel": channel.value,
                "message": f"Subscribed to {channel.value}",
                "timestamp": datetime.utcnow().isoformat(),
            })

            return True

    async def unsubscribe(self, client_id: str, channel: Channel) -> bool:
        """
        Unsubscribe client from a channel.

        Args:
            client_id: Client identifier
            channel: Channel to unsubscribe from

        Returns:
            True if successful
        """
        async with self._client_lock:
            if client_id not in self._clients:
                return False

            client = self._clients[client_id]
            client.subscribed_channels.discard(channel)
            self._channel_subscriptions[channel].discard(client_id)

            logger.info(f"Client {client_id} unsubscribed from {channel.value}")

            return True

    async def broadcast(self, message: BroadcastMessage) -> int:
        """
        Broadcast message to all subscribed clients on a channel.

        Args:
            message: Message to broadcast

        Returns:
            Number of messages sent
        """
        channel = message.channel

        # Rate limiting check
        if not self._rate_limiters[channel].is_allowed():
            self._stats["total_messages_dropped"] += 1
            logger.debug(f"Rate limit exceeded for {channel.value}")
            return 0

        # Store in history
        self._store_message_history(message)

        async with self._client_lock:
            subscriber_ids = list(self._channel_subscriptions[channel])

        if not subscriber_ids:
            logger.debug(f"No subscribers for {channel.value}")
            return 0

        # Send to all subscribers
        sent_count = 0
        failed_clients = []

        for client_id in subscriber_ids:
            async with self._client_lock:
                if client_id not in self._clients:
                    continue
                client = self._clients[client_id]

            success = await client.send_message(message)
            if success:
                sent_count += 1
                client.update_activity()
            else:
                failed_clients.append(client_id)

        # Remove failed clients
        for client_id in failed_clients:
            await self.disconnect(client_id)

        self._stats["total_messages_sent"] += sent_count
        logger.debug(f"Broadcast to {channel.value}: {sent_count}/{len(subscriber_ids)} sent")

        return sent_count

    async def broadcast_detections(
        self,
        frame_data: Dict[str, Any],
        detections: List[Dict[str, Any]]
    ) -> int:
        """
        Broadcast detection results to clients.

        Args:
            frame_data: Frame metadata
            detections: List of detected objects

        Returns:
            Number of messages sent
        """
        if not detections:
            return 0

        message = BroadcastMessage(
            channel=Channel.DETECTIONS,
            data={
                "frame_id": frame_data.get("frame_id"),
                "timestamp": frame_data.get("timestamp", datetime.utcnow()).isoformat(),
                "detections": detections,
                "detection_count": len(detections),
                "session_id": frame_data.get("session_id"),
            }
        )

        return await self.broadcast(message)

    async def broadcast_incident(self, incident_data: Dict[str, Any]) -> int:
        """
        Broadcast incident alert to clients.

        Args:
            incident_data: Incident details

        Returns:
            Number of messages sent
        """
        message = BroadcastMessage(
            channel=Channel.INCIDENTS,
            data={
                "incident_id": incident_data.get("incident_id"),
                "type": incident_data.get("type"),
                "severity": incident_data.get("severity"),
                "location": incident_data.get("location"),
                "description": incident_data.get("description"),
                "timestamp": incident_data.get("timestamp", datetime.utcnow()).isoformat(),
                "affected_vehicles": incident_data.get("affected_vehicles", []),
                "session_id": incident_data.get("session_id"),
            }
        )

        return await self.broadcast(message)

    async def broadcast_metrics(self, metrics: Any) -> int:
        """
        Broadcast performance metrics to clients.

        Args:
            metrics: Processing metrics object with to_dict() method

        Returns:
            Number of messages sent
        """
        message = BroadcastMessage(
            channel=Channel.METRICS,
            data=metrics.to_dict() if hasattr(metrics, 'to_dict') else metrics
        )

        return await self.broadcast(message)

    async def send_to_client(
        self,
        client_id: str,
        channel: Channel,
        data: Dict[str, Any]
    ) -> bool:
        """
        Send message directly to a specific client.

        Args:
            client_id: Target client identifier
            channel: Message channel
            data: Message data

        Returns:
            True if successful
        """
        async with self._client_lock:
            if client_id not in self._clients:
                logger.warning(f"Client {client_id} not found")
                return False
            client = self._clients[client_id]

        message = BroadcastMessage(channel=channel, data=data, sender_id=client_id)
        success = await client.send_message(message)

        if success:
            client.update_activity()
            self._stats["total_messages_sent"] += 1

        return success

    async def handle_chat_message(
        self,
        client_id: str,
        message: str,
        session_id: Optional[str] = None
    ) -> bool:
        """
        Handle incoming chat message and route to LangGraph agent.

        Args:
            client_id: Client identifier
            message: Chat message text
            session_id: Optional traffic session ID

        Returns:
            True if processed successfully
        """
        async with self._client_lock:
            if client_id not in self._clients:
                logger.warning(f"Client {client_id} not found for chat")
                return False
            client = self._clients[client_id]

        try:
            # Store the message
            self._store_message_history(
                BroadcastMessage(
                    channel=Channel.CHAT,
                    data={
                        "client_id": client_id,
                        "message": message,
                        "session_id": session_id,
                    },
                    sender_id=client_id
                )
            )

            # Route to agent if callback provided
            if self.chat_agent_callback:
                response = await self.chat_agent_callback(
                    client_id=client_id,
                    message=message,
                    session_id=session_id,
                    client_metadata=client.metadata
                )

                # Send agent response back to client
                if response:
                    await self.send_to_client(
                        client_id,
                        Channel.CHAT,
                        {
                            "sender": "agent",
                            "message": response,
                            "session_id": session_id,
                        }
                    )

            client.update_activity()
            return True

        except Exception as e:
            logger.error(f"Error handling chat message from {client_id}: {e}")
            return False

    def _store_message_history(self, message: BroadcastMessage) -> None:
        """Store message in history for debugging/analysis."""
        channel = message.channel
        self._message_history[channel].append(message)

        # Trim history to max size
        if len(self._message_history[channel]) > self._max_history_size:
            self._message_history[channel] = self._message_history[channel][-self._max_history_size:]

    def get_message_history(self, channel: Channel, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent message history for a channel.

        Args:
            channel: Channel to get history for
            limit: Maximum number of messages to return

        Returns:
            List of messages
        """
        messages = self._message_history[channel][-limit:]
        return [msg.to_dict() for msg in messages]

    async def get_connection_info(self, client_id: str) -> Optional[Dict[str, Any]]:
        """
        Get connection information for a client.

        Args:
            client_id: Client identifier

        Returns:
            Connection info or None if not connected
        """
        async with self._client_lock:
            if client_id not in self._clients:
                return None

            client = self._clients[client_id]
            return {
                "client_id": client_id,
                "connected_at": client.connected_at.isoformat(),
                "subscribed_channels": [ch.value for ch in client.subscribed_channels],
                "message_count": client.message_count,
                "metadata": client.metadata,
            }

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get connection manager statistics.

        Returns:
            Statistics dictionary
        """
        uptime = datetime.utcnow() - self._stats["start_time"]
        return {
            **self._stats,
            "active_clients": len(self._clients),
            "uptime_seconds": uptime.total_seconds(),
            "channels": {
                channel.value: len(self._channel_subscriptions[channel])
                for channel in Channel
            },
        }

    async def broadcast_system_message(self, message: str, severity: str = "info") -> int:
        """
        Broadcast a system message to all connected clients.

        Args:
            message: Message text
            severity: Message severity (info, warning, error)

        Returns:
            Number of recipients
        """
        async with self._client_lock:
            all_client_ids = list(self._clients.keys())

        sent_count = 0
        for client_id in all_client_ids:
            success = await self.send_to_client(
                client_id,
                Channel.METRICS,  # Use metrics channel for system messages
                {
                    "type": "system_message",
                    "severity": severity,
                    "message": message,
                }
            )
            if success:
                sent_count += 1

        return sent_count

    async def close_all_connections(self) -> None:
        """Close all active client connections gracefully."""
        async with self._client_lock:
            client_ids = list(self._clients.keys())

        logger.info(f"Closing all {len(client_ids)} client connections")

        for client_id in client_ids:
            try:
                await self.disconnect(client_id)
            except Exception as e:
                logger.error(f"Error disconnecting {client_id}: {e}")

        logger.info("All connections closed")
