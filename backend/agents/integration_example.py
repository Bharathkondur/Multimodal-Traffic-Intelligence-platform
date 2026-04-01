"""
Production Integration Example for Traffic Intelligence Agent.

Demonstrates:
- Full system initialization with configuration
- Real-world usage patterns
- Error handling
- Logging setup
- Multi-query handling
"""

import asyncio
import logging
from datetime import datetime

from agents.graph import TrafficAnalysisGraph, LLMBackend
from agents.rag import DetectionRAG
from agents.config import load_config


def setup_logging():
    """Configure logging for production."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('traffic_agent.log'),
        ]
    )


async def initialize_agent(config_path: str = ".env") -> TrafficAnalysisGraph:
    """
    Initialize Traffic Intelligence Agent with configuration.

    Args:
        config_path: Path to configuration file

    Returns:
        Initialized agent
    """
    logger = logging.getLogger(__name__)

    # Load configuration
    config = load_config(config_path)

    # Print configuration summary
    config.print_summary()

    # Validate configuration
    is_valid, errors = config.validate()
    if not is_valid:
        logger.error("Configuration validation failed:")
        for error in errors:
            logger.error(f"  - {error}")
        raise ValueError("Invalid configuration")

    # Initialize agent
    logger.info("Initializing Traffic Intelligence Agent...")

    agent = TrafficAnalysisGraph(
        llm_backend=config.agent.llm_backend,
        llm_model=(
            config.openai.model
            if config.agent.llm_backend == LLMBackend.OPENAI
            else config.ollama.model
        ),
        temperature=config.agent.temperature,
        enable_streaming=config.agent.enable_streaming,
        rag_enabled=config.rag.enabled,
    )

    logger.info("Agent initialized successfully")
    return agent


async def populate_rag(agent: TrafficAnalysisGraph) -> None:
    """
    Populate RAG system with sample traffic data.

    Args:
        agent: Traffic agent instance
    """
    if not agent.rag:
        return

    logger = logging.getLogger(__name__)
    logger.info("Populating RAG with sample detection data...")

    now = datetime.now()

    # Sample detection events
    sample_detections = [
        {
            "detection_type": "vehicle",
            "content": "High volume of commercial trucks detected at Main Street corridor",
            "timestamp": (now.replace(hour=8, minute=0)).isoformat(),
            "location": "Main Street",
            "metadata": {
                "vehicle_count": 45,
                "truck_percentage": 0.85,
            },
        },
        {
            "detection_type": "incident",
            "content": "Fender bender accident at 5th and Main intersection, minimal damage",
            "timestamp": (now.replace(hour=9, minute=15)).isoformat(),
            "location": "5th Avenue & Main Street",
            "metadata": {
                "severity": "low",
                "duration_minutes": 12,
                "traffic_impact": "minor",
            },
        },
        {
            "detection_type": "vehicle",
            "content": "Moderate traffic congestion during morning rush hour",
            "timestamp": (now.replace(hour=8, minute=30)).isoformat(),
            "location": "Main Corridor",
            "metadata": {
                "congestion_level": "moderate",
                "vehicle_count": 280,
            },
        },
        {
            "detection_type": "incident",
            "content": "Traffic violation: vehicle speeding in residential zone",
            "timestamp": (now.replace(hour=10, minute=5)).isoformat(),
            "location": "Residential Zone A",
            "metadata": {
                "violation_type": "speeding",
                "vehicle_type": "motorcycle",
            },
        },
        {
            "detection_type": "vehicle",
            "content": "Heavy evening rush hour traffic, all lanes congested",
            "timestamp": (now.replace(hour=17, minute=30)).isoformat(),
            "location": "All Major Corridors",
            "metadata": {
                "peak_traffic": True,
                "vehicle_count": 850,
            },
        },
    ]

    agent.rag.add_batch(sample_detections)
    logger.info(f"Populated RAG with {len(sample_detections)} detection events")

    # Print RAG statistics
    stats = agent.rag.get_statistics()
    logger.info(f"RAG Statistics: {stats}")


async def process_queries(agent: TrafficAnalysisGraph) -> None:
    """
    Process multiple traffic queries.

    Args:
        agent: Traffic agent instance
    """
    logger = logging.getLogger(__name__)

    # Test queries of different types
    queries = [
        "What's the current traffic situation on Main Street?",
        "Generate a shift report for today",
        "Is there any accident or incident reported?",
        "What's happening right now in the monitored area?",
        "Compare today's traffic with yesterday in terms of vehicle count",
    ]

    logger.info(f"Processing {len(queries)} test queries...")

    for i, query in enumerate(queries, 1):
        logger.info(f"\n[Query {i}/{len(queries)}] {query}")

        try:
            result = await agent.invoke(query)

            logger.info(f"Query Type: {result['query_type']}")
            logger.info(f"Response Preview: {result['response'][:200]}...")
            logger.info(f"Context Used: {result['context_used']}")
            logger.info(f"Detections Retrieved: {result['detections_retrieved']}")

        except Exception as e:
            logger.error(f"Error processing query: {e}")


async def demonstrate_rag_search(agent: TrafficAnalysisGraph) -> None:
    """
    Demonstrate RAG semantic search capabilities.

    Args:
        agent: Traffic agent instance
    """
    if not agent.rag:
        return

    logger = logging.getLogger(__name__)
    logger.info("\n=== RAG Semantic Search Demonstration ===")

    search_queries = [
        "commercial vehicles and trucks",
        "accidents and incidents",
        "congestion and traffic delays",
        "safety violations",
    ]

    for search_query in search_queries:
        logger.info(f"\nSearching for: '{search_query}'")
        results = agent.rag.retrieve(search_query, k=3)

        if results:
            logger.info(f"Found {len(results)} relevant events:")
            for j, result in enumerate(results, 1):
                logger.info(
                    f"  {j}. [{result['type']}] {result['location']}: "
                    f"{result['content'][:60]}... "
                    f"(relevance: {result['relevance_score']:.2%})"
                )
        else:
            logger.info("No relevant events found")


async def streaming_example(agent: TrafficAnalysisGraph) -> None:
    """
    Demonstrate streaming response capability.

    Args:
        agent: Traffic agent instance
    """
    if not agent.enable_streaming:
        return

    logger = logging.getLogger(__name__)
    logger.info("\n=== Streaming Response Example ===")

    query = "Generate a comprehensive shift report for today with recommendations"
    logger.info(f"Query: {query}\n")

    try:
        logger.info("Streaming response:")
        async for chunk in agent.stream(query):
            print(chunk, end="", flush=True)

        print("\n")
        logger.info("Streaming complete")

    except Exception as e:
        logger.error(f"Error in streaming: {e}")


async def main():
    """Main execution."""
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("=" * 70)
    logger.info("Traffic Intelligence Agent - Production Integration Example")
    logger.info("=" * 70)

    try:
        # Initialize agent
        agent = await initialize_agent(".env")

        # Populate RAG with sample data
        await populate_rag(agent)

        # Demonstrate RAG semantic search
        await demonstrate_rag_search(agent)

        # Process multiple queries
        await process_queries(agent)

        # Demonstrate streaming (if enabled)
        await streaming_example(agent)

        logger.info("\n" + "=" * 70)
        logger.info("Integration example completed successfully!")
        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
