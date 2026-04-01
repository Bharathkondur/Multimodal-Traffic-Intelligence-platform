# Traffic Intelligence Agent System

A production-grade LangGraph-based AI agent system for analyzing traffic data, incidents, and generating insights and reports for the Multimodal Traffic Intelligence Platform.

## Features

### Core Agent Capabilities
- **Multi-node Graph Architecture**: Query analysis → Data retrieval → Reasoning → Response generation
- **Query Classification**: Automatically classifies queries as questions, reports, alerts, scene descriptions, or analyses
- **Flexible LLM Backends**: Support for OpenAI GPT-4o and local Ollama/Llama 3
- **Streaming Responses**: Real-time token streaming for responsive UX
- **Async-first Design**: Built on async/await for high concurrency

### Specialized Tools
- **Detection Queries**: Natural language search over detection database
- **Vehicle Counting**: Aggregated vehicle statistics by type and time
- **Incident Reporting**: Detailed incident information and resolution tracking
- **Traffic Flow Analysis**: Speed, density, and congestion metrics
- **Shift Reports**: Comprehensive summaries with recommendations
- **Period Comparison**: Time-series analysis and trend detection
- **Scene Snapshots**: Real-time traffic condition descriptions

### RAG System
- **Semantic Search**: Vector-based search over detection events
- **Time-aware Retrieval**: Filter results by time ranges
- **Location Filtering**: Geographic context preservation
- **Batch Indexing**: Efficient document ingestion
- **Token Management**: Automatic context window management

### Domain-Specific Prompts
- **Traffic Analyst**: General analysis and insight generation
- **Report Generator**: Structured report creation
- **Incident Analyzer**: Specialized incident analysis
- **Scene Describer**: Real-time scene interpretation

## Installation

### Prerequisites
- Python 3.10+
- pip package manager

### Basic Installation

```bash
# Clone or navigate to the agents directory
cd backend/agents

# Install dependencies
pip install -r requirements.txt

# For OpenAI support
pip install langchain-openai

# For Ollama support (requires local Ollama instance)
pip install langchain-ollama
```

### Environment Setup

Create a `.env` file in the agents directory:

```bash
# OpenAI API key (if using GPT-4o)
OPENAI_API_KEY=sk-...

# Ollama configuration (if using local Ollama)
OLLAMA_BASE_URL=http://localhost:11434
```

## Quick Start

### Basic Usage with OpenAI

```python
import asyncio
from agents.graph import TrafficAnalysisGraph, LLMBackend

async def main():
    # Initialize agent
    agent = TrafficAnalysisGraph(
        llm_backend=LLMBackend.OPENAI,
        llm_model="gpt-4o",
        temperature=0.7,
    )

    # Submit query
    result = await agent.invoke("What's the current traffic situation?")
    print(result["response"])

asyncio.run(main())
```

### Using Local Ollama

```python
from agents.graph import TrafficAnalysisGraph, LLMBackend

agent = TrafficAnalysisGraph(
    llm_backend=LLMBackend.OLLAMA,
    llm_model="llama3",
)

# Use same invoke() or stream() methods
```

### Streaming Responses

```python
async def stream_response():
    agent = TrafficAnalysisGraph(
        llm_backend=LLMBackend.OPENAI,
        enable_streaming=True,
    )

    query = "Generate a shift report for today"

    async for chunk in agent.stream(query):
        print(chunk, end="", flush=True)

asyncio.run(stream_response())
```

### Using RAG for Semantic Search

```python
from agents.rag import DetectionRAG
from datetime import datetime

# Initialize RAG
rag = DetectionRAG()

# Add detection events
rag.add_detection(
    detection_type="vehicle",
    content="Heavy truck detected at Main Street",
    timestamp=datetime.now(),
    location="Main St & 5th Ave",
)

# Semantic search
results = rag.retrieve("trucks causing congestion", k=5)

# Time-aware retrieval
recent = rag.retrieve_recent(hours=1, detection_type="incident")

# Location-based search
location_results = rag.retrieve_by_location("Main Street", hours=24)
```

## Architecture

### State Schema

```python
@dataclass
class TrafficAgentState:
    messages: list[BaseMessage]           # Conversation history
    user_query: str                       # Current query
    query_type: QueryType                 # Classified query type
    context: str                          # RAG context
    retrieved_data: dict[str, Any]        # Retrieved metrics/data
    detections: list[dict[str, Any]]      # Detection events
    reasoning: str                        # Intermediate reasoning
    analysis_results: dict[str, Any]      # Analysis outputs
    response: str                         # Final response
```

### Graph Nodes

1. **analyze_query**: Classifies query and prepares for processing
2. **retrieve_data**: Fetches relevant data based on query type
3. **reason**: Performs analysis using LLM
4. **generate_response**: Creates final user-facing response

### Conditional Routing

Automatically routes to appropriate tool chains based on query classification:
- **QUESTION** → Data retrieval + analysis
- **REPORT** → Shift/period aggregation
- **ALERT** → Incident analysis
- **SCENE** → Current state description
- **ANALYSIS** → Deep pattern analysis

## Tool Reference

### query_detections(query, time_range, location_filter, limit)
Search detection database with natural language.

```python
result = await query_detections(
    query="motorcycles in intersection A",
    time_range="last_hour",
    limit=20
)
```

### get_vehicle_count(vehicle_type, time_range, location)
Count vehicles by type and period.

```python
result = await get_vehicle_count(
    vehicle_type=VehicleType.TRUCK,
    time_range="today",
    location="main_street"
)
```

### get_incident_report(incident_id, include_details)
Get detailed incident information.

```python
result = await get_incident_report("INC20240331001")
```

### get_traffic_flow(location, time_range, include_historical)
Analyze traffic patterns and speed.

```python
result = await get_traffic_flow(
    location="main_corridor",
    time_range="today",
    include_historical=True
)
```

### generate_shift_report(shift_time, date, include_recommendations)
Create comprehensive shift summaries.

```python
result = await generate_shift_report(
    shift_time="08:00-16:00",
    date="2024-03-31",
    include_recommendations=True
)
```

### compare_periods(period_1, period_2, metric, location)
Compare metrics across time periods.

```python
result = await compare_periods(
    period_1="today",
    period_2="yesterday",
    metric="vehicle_count"
)
```

### get_current_scene(location, detail_level)
Get real-time scene description.

```python
result = await get_current_scene(
    location="main_corridor",
    detail_level="detailed"
)
```

## RAG System Guide

### Adding Detection Events

```python
rag = DetectionRAG()

# Single detection
rag.add_detection(
    detection_type="vehicle",
    content="Heavy traffic observed",
    timestamp=datetime.now(),
    location="Main St",
    metadata={"vehicle_count": 150}
)

# Batch import
detections = [
    {
        "detection_type": "incident",
        "content": "Accident reported",
        "timestamp": datetime.now(),
        "location": "5th Ave",
    },
    # ... more detections
]
rag.add_batch(detections)
```

### Semantic Search

```python
# General query
results = rag.retrieve("traffic congestion", k=10)

# With time range
from datetime import datetime, timedelta
start = datetime.now() - timedelta(hours=1)
end = datetime.now()
results = rag.retrieve(
    "incidents",
    time_range=(start, end)
)

# With location filter
results = rag.retrieve(
    "accidents",
    location_filter="Main Street"
)
```

### Specialized Retrieval

```python
# Recent detections
recent = rag.retrieve_recent(hours=1)

# By location
location_data = rag.retrieve_by_location("5th Ave", hours=24)

# Incidents only
incidents = rag.retrieve_incidents(hours=2)

# Get formatted context for LLM
context = rag.get_context("your query", k=5)

# Statistics
stats = rag.get_statistics()
```

## Configuration

### LLM Backend Selection

```python
# OpenAI GPT-4o
agent = TrafficAnalysisGraph(
    llm_backend=LLMBackend.OPENAI,
    llm_model="gpt-4o",  # or "gpt-4-turbo", "gpt-3.5-turbo"
    temperature=0.7,
)

# Local Ollama
agent = TrafficAnalysisGraph(
    llm_backend=LLMBackend.OLLAMA,
    llm_model="llama3",  # or "mistral", "neural-chat", etc.
    temperature=0.5,
)
```

### Advanced Configuration

```python
agent = TrafficAnalysisGraph(
    llm_backend=LLMBackend.OPENAI,
    llm_model="gpt-4o",
    temperature=0.7,           # Model creativity (0-1)
    enable_streaming=True,     # Stream tokens
    rag_enabled=True,          # Enable semantic search
)

# Get graph schema
schema = agent.get_graph_schema()
```

## Production Deployment

### Logging Configuration

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('agent.log'),
        logging.StreamHandler()
    ]
)
```

### Error Handling

The agent includes comprehensive error handling:
- Graceful degradation when LLM unavailable
- Fallback responses for retrieval failures
- Detailed error logging
- Automatic retry mechanisms (can be enhanced)

### Performance Optimization

```python
# For high-traffic scenarios
agent = TrafficAnalysisGraph(
    llm_backend=LLMBackend.OPENAI,
    temperature=0.5,      # Lower for deterministic responses
    rag_enabled=True,     # Leverage cached context
)

# Use batch processing for multiple queries
results = await asyncio.gather(
    agent.invoke(query1),
    agent.invoke(query2),
    agent.invoke(query3),
)
```

## Examples

Complete examples are provided in `example_usage.py`:

```bash
python example_usage.py
```

Examples include:
- Basic query handling
- RAG system usage
- Query type classification
- Streaming responses
- Integration patterns

## Testing

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
pytest tests/

# With coverage
pytest --cov=agents tests/
```

## Monitoring & Debugging

### Agent Graph Schema

```python
schema = agent.get_graph_schema()
# Returns:
# {
#     "nodes": ["analyze_query", "retrieve_data", "reason", "generate_response"],
#     "edges": [...],
#     "query_types": ["question", "report", "alert", "scene", "analysis"],
#     "llm_backend": "openai",
#     "rag_enabled": true
# }
```

### RAG Statistics

```python
stats = agent.rag.get_statistics()
# Returns document counts, types, locations, time range
```

### Message History

All agent executions maintain conversation history:

```python
result = await agent.invoke(query)
# result["messages"] contains full conversation
```

## Extending the System

### Adding Custom Tools

```python
from langchain_core.tools import tool
from pydantic import BaseModel, Field

class CustomToolInput(BaseModel):
    param: str = Field(description="Parameter description")

@tool("custom_tool", args_schema=CustomToolInput)
async def custom_tool(param: str) -> dict:
    """Custom tool implementation."""
    return {"result": "value"}

# Bind to agent
agent.tools.append(custom_tool)
agent.llm_with_tools = agent.llm.bind_tools(agent.tools)
```

### Custom Prompts

```python
from agents.prompts import TRAFFIC_ANALYST_SYSTEM

CUSTOM_PROMPT = """You are a custom traffic analyst...
[Your prompt here]"""

# Use in graph or nodes
```

## Troubleshooting

### OpenAI API Issues
- Verify `OPENAI_API_KEY` is set correctly
- Check API quota and rate limits
- Ensure network connectivity

### Ollama Connection
- Verify Ollama is running: `http://localhost:11434`
- Check model availability: `ollama list`
- Pull model if needed: `ollama pull llama3`

### RAG Performance
- For large datasets, consider using actual FAISS
- Monitor embedding dimensionality
- Implement periodic index cleanup

### Memory Usage
- Implement context window limits
- Use streaming for large responses
- Clear old detections periodically

## Best Practices

1. **Always use async**: Agent methods are async-first
2. **Stream for UX**: Use streaming for real-time responsiveness
3. **Error handling**: Wrap invoke() in try-catch
4. **Monitor tokens**: Track token usage with OpenAI
5. **Cache context**: Reuse RAG context when possible
6. **Log activity**: Enable logging for debugging

## API Reference

See docstrings in source files for complete API documentation:
- `graph.py`: Main agent class
- `tools.py`: Tool implementations
- `rag.py`: RAG system
- `prompts.py`: System prompts

## License

Part of the Multimodal Traffic Intelligence Platform

## Support

For issues or questions:
1. Check example_usage.py for usage patterns
2. Review docstrings in source files
3. Enable DEBUG logging for detailed trace
4. Check error messages and logs

---

**Last Updated**: March 2024
**Python Version**: 3.10+
**LangGraph Version**: 0.0.1+
