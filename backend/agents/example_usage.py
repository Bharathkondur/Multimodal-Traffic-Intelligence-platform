"""
Example usage of the Traffic Intelligence Agent.

Demonstrates:
- Initializing the agent with different LLM backends
- Submitting queries
- Using RAG for semantic search
- Streaming responses
- Working with different query types
"""

import asyncio
import logging
from datetime import datetime, timedelta

from agents.graph import TrafficAnalysisGraph, LLMBackend
from agents.rag import DetectionRAG

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def example_basic_usage():
    """Basic usage example with OpenAI backend."""
    logger.info("=== Basic Usage Example (OpenAI) ===")

    # Initialize agent with OpenAI GPT-4o
    agent = TrafficAnalysisGraph(
        llm_backend=LLMBackend.OPENAI,
        llm_model="gpt-4o",
        temperature=0.7,
    )

    # Get graph schema
    schema = agent.get_graph_schema()
    logger.info(f"Agent graph schema: {schema}")

    # Example query
    query = "What's the current traffic situation on Main Street?"

    try:
        result = await agent.invoke(query)
        logger.info(f"Agent response: {result}")
    except Exception as e:
        logger.error(f"Error: {e}")


async def example_ollama_backend():
    """Example using local Ollama backend."""
    logger.info("=== Using Ollama Backend Example ===")

    try:
        # Initialize with Ollama (requires local Ollama instance running)
        agent = TrafficAnalysisGraph(
            llm_backend=LLMBackend.OLLAMA,
            llm_model="llama3",
            temperature=0.7,
        )

        query = "Generate a shift report for today"

        result = await agent.invoke(query)
        logger.info(f"Agent response: {result}")

    except ValueError as e:
        logger.warning(f"Ollama not available: {e}")
        logger.info("To use Ollama, install langchain-ollama and run local Ollama instance")


async def example_rag_system():
    """Demonstrate RAG system for semantic search."""
    logger.info("=== RAG System Example ===")

    # Initialize RAG
    rag = DetectionRAG(embedding_dim=384)

    # Add sample detection events
    now = datetime.now()

    detections = [
        {
            "detection_type": "vehicle",
            "content": "Heavy truck detected at Main Street intersection, causing congestion",
            "timestamp": (now - timedelta(minutes=5)).isoformat(),
            "location": "Main St & 5th Ave",
            "metadata": {"vehicle_type": "truck", "confidence": 0.95},
        },
        {
            "detection_type": "incident",
            "content": "Minor accident reported: two cars collided at North entrance",
            "timestamp": (now - timedelta(minutes=15)).isoformat(),
            "location": "North Entrance",
            "metadata": {"severity": "low", "resolved": True},
        },
        {
            "detection_type": "vehicle",
            "content": "Motorcycle speeding in residential zone near parking lot",
            "timestamp": (now - timedelta(minutes=20)).isoformat(),
            "location": "Parking Lot Zone",
            "metadata": {"vehicle_type": "motorcycle", "violation": "speeding"},
        },
        {
            "detection_type": "incident",
            "content": "Traffic congestion at peak hours: 150+ vehicles waiting at main junction",
            "timestamp": (now - timedelta(hours=1)).isoformat(),
            "location": "Main Junction",
            "metadata": {"severity": "medium", "duration_minutes": 45},
        },
    ]

    # Add detections in batch
    doc_ids = rag.add_batch(detections)
    logger.info(f"Added {len(doc_ids)} detection documents")

    # Semantic search examples
    queries = [
        "trucks causing traffic",
        "accidents in the area",
        "motorcycles",
        "congestion at main areas",
    ]

    for query in queries:
        results = rag.retrieve(query, k=3)
        logger.info(f"\nQuery: '{query}'")
        logger.info(f"Found {len(results)} results:")
        for result in results:
            logger.info(
                f"  - [{result['type']}] {result['location']}: "
                f"{result['content'][:80]}... (relevance: {result['relevance_score']:.2%})"
            )

    # Time-aware retrieval
    logger.info("\n=== Recent Incidents (last 30 minutes) ===")
    recent_incidents = rag.retrieve_incidents(hours=0.5)
    for incident in recent_incidents:
        logger.info(f"  - {incident['location']}: {incident['content'][:80]}...")

    # Location-based retrieval
    logger.info("\n=== Detections at Main Junction ===")
    location_results = rag.retrieve_by_location("Main Junction", hours=24)
    for result in location_results:
        logger.info(f"  - {result['content'][:80]}...")

    # Get statistics
    stats = rag.get_statistics()
    logger.info(f"\nRAG Statistics: {stats}")

    # Get formatted context for LLM
    context = rag.get_context("traffic incidents and congestion", k=5)
    logger.info(f"\nFormatted context for LLM:\n{context}")


async def example_query_types():
    """Demonstrate different query types."""
    logger.info("=== Different Query Types Example ===")

    agent = TrafficAnalysisGraph(
        llm_backend=LLMBackend.OPENAI,
        enable_streaming=False,
    )

    test_queries = [
        ("What's the current traffic situation?", "QUESTION"),
        ("Generate a shift report for today", "REPORT"),
        ("Alert: Is there an accident on Main Street?", "ALERT"),
        ("What's happening right now in the monitored area?", "SCENE"),
        ("Compare today's traffic with yesterday", "ANALYSIS"),
    ]

    for query, expected_type in test_queries:
        logger.info(f"\nQuery: {query}")
        logger.info(f"Expected type: {expected_type}")

        # The agent will classify the query
        query_type = agent._classify_query(query)
        logger.info(f"Detected type: {query_type.value}")


async def example_streaming():
    """Demonstrate streaming responses."""
    logger.info("=== Streaming Example ===")

    agent = TrafficAnalysisGraph(
        llm_backend=LLMBackend.OPENAI,
        enable_streaming=True,
    )

    query = "What are the current traffic conditions?"

    logger.info(f"Query: {query}\n")
    logger.info("Streaming response:")

    # Stream response
    full_response = ""
    try:
        async for chunk in agent.stream(query):
            print(chunk, end="", flush=True)
            full_response += chunk

        print("\n")
        logger.info(f"Streaming complete. Total length: {len(full_response)} chars")

    except Exception as e:
        logger.error(f"Streaming error: {e}")


async def example_with_rag_integration():
    """Demonstrate agent with RAG integration."""
    logger.info("=== Agent with RAG Integration Example ===")

    # Create agent with RAG enabled
    agent = TrafficAnalysisGraph(
        llm_backend=LLMBackend.OPENAI,
        rag_enabled=True,
    )

    # Populate RAG with sample data
    now = datetime.now()

    sample_detections = [
        {
            "detection_type": "vehicle",
            "content": "Heavy traffic with multiple trucks queued at Main Street",
            "timestamp": (now - timedelta(minutes=5)).isoformat(),
            "location": "Main Street",
        },
        {
            "detection_type": "incident",
            "content": "Fender bender at intersection, minor damage, vehicles moved to shoulder",
            "timestamp": (now - timedelta(minutes=20)).isoformat(),
            "location": "5th Avenue",
        },
    ]

    if agent.rag:
        agent.rag.add_batch(sample_detections)
        logger.info("RAG populated with sample detections")

        # Query with RAG context
        query = "Tell me about traffic incidents"
        try:
            result = await agent.invoke(query)
            logger.info(f"Result with RAG:\n{result}")
        except Exception as e:
            logger.error(f"Error: {e}")


async def main():
    """Run all examples."""
    logger.info("Starting Traffic Intelligence Agent Examples\n")

    # Note: Uncomment the examples you want to run
    # Some require API keys or local services

    # Basic usage (requires OPENAI_API_KEY)
    # await example_basic_usage()

    # Ollama usage (requires local Ollama instance)
    # await example_ollama_backend()

    # RAG system
    await example_rag_system()

    # Query type classification
    await example_query_types()

    # Streaming (requires OPENAI_API_KEY)
    # await example_streaming()

    # Agent with RAG (requires OPENAI_API_KEY)
    # await example_with_rag_integration()

    logger.info("\nExamples complete!")


if __name__ == "__main__":
    asyncio.run(main())
