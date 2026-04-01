"""
Integration example for the Multi-Agent Traffic Intelligence System.

This module demonstrates how to:
1. Initialize the StreamProcessor with real components
2. Set up the MultiAgentSystem
3. Integrate them together for complete traffic analysis
"""

import asyncio
import logging
from typing import Optional, Dict, Any

from langchain_google_genai import ChatGoogleGenerativeAI

from multi_agent import TrafficMultiAgentSystem, MultiAgentState
from ..stream.processor import StreamProcessor, StreamSource, StreamSourceType, ProcessingConfig
from ..detection.detector import VehicleDetector
from ..detection.tracker import ObjectTracker
from ..detection.incident_detector import IncidentDetector
from ..analytics.heatmap import TrafficHeatmap
from ..analytics.speed import SpeedEstimator
from ..analytics.zones import ZoneAnalytics
from ..database.connection import AsyncSessionFactory

logger = logging.getLogger(__name__)


class IntegratedTrafficIntelligenceSystem:
    """
    Integrated system combining stream processing and multi-agent analysis.

    This system:
    1. Processes video streams in real-time
    2. Detects, tracks, and analyzes incidents
    3. Uses multi-agent system for intelligent insights
    4. Provides unified traffic intelligence platform
    """

    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        database_url: Optional[str] = None,
        yolo_model_path: str = "yolov8m.pt",
    ):
        """
        Initialize the integrated system.

        Args:
            gemini_api_key: API key for Google Gemini (for multi-agent system)
            database_url: PostgreSQL connection URL for data persistence
            yolo_model_path: Path to YOLO model for detection
        """
        self.gemini_api_key = gemini_api_key
        self.database_url = database_url
        self.yolo_model_path = yolo_model_path

        # Components
        self.detector: Optional[VehicleDetector] = None
        self.tracker: Optional[ObjectTracker] = None
        self.incident_detector: Optional[IncidentDetector] = None
        self.heatmap: Optional[TrafficHeatmap] = None
        self.speed_estimator: Optional[SpeedEstimator] = None
        self.zone_analytics: Optional[ZoneAnalytics] = None
        self.db_factory: Optional[AsyncSessionFactory] = None

        # Stream processors (can have multiple)
        self.processors: Dict[str, StreamProcessor] = {}

        # Multi-agent system
        self.multi_agent_system: Optional[TrafficMultiAgentSystem] = None

        logger.info("IntegratedTrafficIntelligenceSystem initialized")

    async def initialize(self) -> None:
        """Initialize all components of the system."""
        logger.info("Initializing system components...")

        # Initialize detection components
        try:
            self.detector = VehicleDetector(
                model_path=self.yolo_model_path,
                confidence_threshold=0.45,
                device="cuda" if self._cuda_available() else "cpu",
            )
            logger.info("VehicleDetector initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize detector: {e}")

        # Initialize tracker
        try:
            self.tracker = ObjectTracker()
            logger.info("ObjectTracker initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize tracker: {e}")

        # Initialize incident detector
        try:
            self.incident_detector = IncidentDetector()
            logger.info("IncidentDetector initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize incident detector: {e}")

        # Initialize analytics components
        try:
            self.heatmap = TrafficHeatmap(width=1920, height=1080, cell_size=20)
            self.speed_estimator = SpeedEstimator(pixels_per_meter=10.0)
            self.zone_analytics = ZoneAnalytics()
            logger.info("Analytics components initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize analytics: {e}")

        # Initialize database connection
        if self.database_url:
            try:
                self.db_factory = AsyncSessionFactory(self.database_url)
                logger.info("Database connection initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize database: {e}")

        # Initialize multi-agent system
        try:
            if self.gemini_api_key:
                llm = ChatGoogleGenerativeAI(
                    model="gemini-2.0-flash",
                    google_api_key=self.gemini_api_key,
                    temperature=0.3,
                )
                self.multi_agent_system = TrafficMultiAgentSystem(llm=llm)
                logger.info("Multi-agent system initialized with Gemini 2.0 Flash")
            else:
                logger.warning("Gemini API key not provided, multi-agent system skipped")
        except Exception as e:
            logger.warning(f"Failed to initialize multi-agent system: {e}")

        logger.info("System initialization complete")

    def _cuda_available(self) -> bool:
        """Check if CUDA is available."""
        try:
            import torch
            return torch.cuda.is_available()
        except (ImportError, AttributeError):
            return False

    async def create_stream_processor(
        self,
        stream_name: str,
        stream_type: StreamSourceType,
        stream_source: str,
        config: Optional[ProcessingConfig] = None,
    ) -> str:
        """
        Create and start a stream processor.

        Args:
            stream_name: Name for this stream
            stream_type: Type of stream source
            stream_source: Stream source (file path, RTSP URL, etc.)
            config: Processing configuration

        Returns:
            Stream ID
        """
        try:
            source = StreamSource(
                type=stream_type,
                source=stream_source,
                name=stream_name,
            )

            processor = StreamProcessor(
                stream_source=source,
                config=config or ProcessingConfig(),
                on_detection=self._handle_detection,
                on_incident=self._handle_incident,
                on_metrics=self._handle_metrics,
                detector=self.detector,
                tracker=self.tracker,
                incident_detector=self.incident_detector,
                heatmap=self.heatmap,
                speed_estimator=self.speed_estimator,
                zone_analytics=self.zone_analytics,
                db_factory=self.db_factory,
            )

            stream_id = await processor.start()
            self.processors[stream_id] = processor

            logger.info(f"Created stream processor: {stream_id}")
            return stream_id

        except Exception as e:
            logger.error(f"Failed to create stream processor: {e}")
            raise

    async def stop_stream_processor(self, stream_id: str) -> None:
        """Stop a stream processor."""
        if stream_id in self.processors:
            await self.processors[stream_id].stop()
            del self.processors[stream_id]
            logger.info(f"Stopped stream processor: {stream_id}")

    async def _handle_detection(
        self,
        frame_data: Dict[str, Any],
        detections: list,
    ) -> None:
        """
        Handle detection results from stream processor.

        Args:
            frame_data: Frame metadata
            detections: List of detection results
        """
        logger.debug(f"Received {len(detections)} detections from frame {frame_data.get('frame_id')}")

        # Could emit WebSocket messages, log, or process further
        if self.multi_agent_system and len(detections) > 10:
            # Trigger analysis if many objects detected
            await self._analyze_with_agents(
                query=f"Analyze {len(detections)} detections in frame {frame_data.get('frame_id')}",
                detection_data=detections,
            )

    async def _handle_incident(self, incident: Dict[str, Any]) -> None:
        """
        Handle incident detection from stream processor.

        Args:
            incident: Incident data
        """
        logger.warning(f"Incident detected: {incident.get('incident_type')} - {incident.get('severity')}")

        # Trigger detailed analysis for incidents
        if self.multi_agent_system:
            await self._analyze_with_agents(
                query=f"Analyze {incident.get('incident_type')} incident with severity {incident.get('severity')}",
                incident_data=[incident],
            )

    async def _handle_metrics(self, metrics) -> None:
        """
        Handle metrics updates from stream processor.

        Args:
            metrics: ProcessingMetrics object
        """
        logger.debug(
            f"FPS: {metrics.current_fps:.1f}, "
            f"Detections: {metrics.total_detections}, "
            f"Incidents: {metrics.total_incidents}"
        )

    async def _analyze_with_agents(
        self,
        query: str,
        detection_data: Optional[list] = None,
        incident_data: Optional[list] = None,
        track_data: Optional[list] = None,
    ) -> Dict[str, Any]:
        """
        Analyze data using the multi-agent system.

        Args:
            query: Query to analyze
            detection_data: Detection results
            incident_data: Incident data
            track_data: Tracking data

        Returns:
            Analysis results from multi-agent system
        """
        if not self.multi_agent_system:
            logger.warning("Multi-agent system not initialized")
            return {}

        try:
            result = await self.multi_agent_system.process(
                query=query,
                detection_data=detection_data,
                incident_data=incident_data,
                track_data=track_data,
            )

            logger.info(f"Multi-agent analysis complete: {result.get('query_type')}")
            return result

        except Exception as e:
            logger.error(f"Error in multi-agent analysis: {e}")
            return {}

    async def query_traffic_intelligence(
        self,
        query: str,
        stream_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Query the traffic intelligence system using natural language.

        Args:
            query: Natural language query
            stream_id: Optional specific stream to query

        Returns:
            Analysis and insights from multi-agent system
        """
        if not self.multi_agent_system:
            return {"error": "Multi-agent system not initialized"}

        try:
            # Gather context from specified or all streams
            context_data = {}
            if stream_id and stream_id in self.processors:
                metrics = self.processors[stream_id].get_metrics()
                context_data["stream_id"] = stream_id
                context_data["metrics"] = metrics.to_dict()
            else:
                # Aggregate metrics from all streams
                for sid, processor in self.processors.items():
                    metrics = processor.get_metrics()
                    context_data[sid] = metrics.to_dict()

            # Process through multi-agent system
            result = await self.multi_agent_system.process(
                query=query,
                context_data=context_data,
            )

            return result

        except Exception as e:
            logger.error(f"Error querying system: {e}")
            return {"error": str(e)}

    async def get_system_status(self) -> Dict[str, Any]:
        """Get current system status."""
        status = {
            "initialized": all([
                self.detector,
                self.tracker,
                self.incident_detector,
                self.multi_agent_system,
            ]),
            "components": {
                "detector": self.detector is not None,
                "tracker": self.tracker is not None,
                "incident_detector": self.incident_detector is not None,
                "heatmap": self.heatmap is not None,
                "speed_estimator": self.speed_estimator is not None,
                "zone_analytics": self.zone_analytics is not None,
                "database": self.db_factory is not None,
                "multi_agent": self.multi_agent_system is not None,
            },
            "active_streams": len(self.processors),
            "stream_metrics": {
                stream_id: processor.get_metrics().to_dict()
                for stream_id, processor in self.processors.items()
            },
        }

        if self.multi_agent_system:
            status["multi_agent_info"] = self.multi_agent_system.get_system_info()

        return status

    async def shutdown(self) -> None:
        """Shutdown the entire system gracefully."""
        logger.info("Shutting down integrated system...")

        # Stop all stream processors
        for stream_id in list(self.processors.keys()):
            await self.stop_stream_processor(stream_id)

        # Close database connections
        if self.db_factory:
            await self.db_factory.dispose()

        logger.info("System shutdown complete")


# Example usage
async def main():
    """Example of how to use the integrated system."""
    import os

    # Initialize system
    system = IntegratedTrafficIntelligenceSystem(
        gemini_api_key=os.getenv("GOOGLE_API_KEY"),
        database_url=os.getenv("DATABASE_URL"),
    )

    await system.initialize()

    # Create a stream processor
    try:
        stream_id = await system.create_stream_processor(
            stream_name="Main Intersection",
            stream_type=StreamSourceType.RTSP_STREAM,
            stream_source="rtsp://example.com/stream",
        )
        logger.info(f"Stream processor created: {stream_id}")

        # Query the system
        result = await system.query_traffic_intelligence(
            query="What traffic incidents are currently happening?",
            stream_id=stream_id,
        )
        logger.info(f"Analysis result: {result.get('final_response')}")

        # Get system status
        status = await system.get_system_status()
        logger.info(f"System status: {status}")

    finally:
        # Cleanup
        await system.shutdown()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
