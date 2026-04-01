# FastAPI Backend - Quick Start Guide

## Installation

```bash
# Navigate to backend directory
cd backend/

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

Create a `.env` file in the backend directory:

```env
# Database
DATABASE_URL=postgresql+asyncpg://traffic_user:password@localhost/traffic_db

# Redis
REDIS_URL=redis://localhost:6379/0

# OpenAI
OPENAI_API_KEY=sk-your-key-here

# Models
MODEL_PATH=yolov8l.pt
EASYOCR_MODEL_PATH=~/.EasyOCR/model

# Detection
DETECTION_CONFIDENCE_THRESHOLD=0.5
MAX_DETECTIONS_PER_FRAME=100

# Upload
UPLOAD_DIR=/tmp/traffic_uploads
MAX_UPLOAD_SIZE=5368709120

# Environment
DEBUG=false
LOG_LEVEL=INFO

# CORS
CORS_ORIGINS=["http://localhost:3000","http://localhost:8000"]
```

## Running the Server

```bash
# Development mode with auto-reload
python main.py

# Or with Uvicorn directly
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production mode
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

The API will be available at:
- API: http://localhost:8000
- Swagger Docs: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc

## API Overview

### Session Management

**Upload a video:**
```bash
curl -X POST "http://localhost:8000/api/sessions/upload" \
  -F "file=@traffic_video.mp4" \
  -F "name=Highway A1"
```

**Start a stream:**
```bash
curl -X POST "http://localhost:8000/api/sessions/stream" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Main Intersection",
    "stream_url": "rtsp://camera.example.com/stream",
    "fps": 30
  }'
```

**Get session info:**
```bash
curl "http://localhost:8000/api/sessions/{session_id}"
```

### Detection & Analytics

**Get detections:**
```bash
curl "http://localhost:8000/api/sessions/{session_id}/detections?page=1&min_confidence=0.8"
```

**Get incidents:**
```bash
curl "http://localhost:8000/api/sessions/{session_id}/incidents?severity=high"
```

**Get statistics:**
```bash
curl "http://localhost:8000/api/sessions/{session_id}/stats"
```

**Get vehicle counts:**
```bash
curl "http://localhost:8000/api/sessions/{session_id}/vehicle-counts"
```

### Chat with AI Agent

```bash
curl -X POST "http://localhost:8000/api/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "{session_id}",
    "message": "What was the peak traffic time?",
    "include_context": true
  }'
```

### Reports

**Generate report:**
```bash
curl -X POST "http://localhost:8000/api/reports/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "{session_id}",
    "report_type": "detailed",
    "include_detections": true,
    "include_incidents": true,
    "include_charts": true
  }'
```

**Download report:**
```bash
curl "http://localhost:8000/api/reports/{report_id}/download" -o report.pdf
```

### System

**Health check:**
```bash
curl "http://localhost:8000/api/health"
```

**Get version:**
```bash
curl "http://localhost:8000/api/version"
```

## WebSocket Usage

Connect to real-time updates:

```javascript
const sessionId = 'sess_abc123';
const ws = new WebSocket(`ws://localhost:8000/ws/${sessionId}`);

// Connection established
ws.onopen = () => {
  // Subscribe to channels
  ws.send(JSON.stringify({
    type: 'subscribe',
    channels: ['detections', 'incidents', 'status']
  }));
};

// Receive messages
ws.onmessage = (event) => {
  const message = JSON.parse(event.data);

  if (message.type === 'detection') {
    console.log('New detection:', message.data);
  } else if (message.type === 'incident') {
    console.log('New incident:', message.data);
  } else if (message.type === 'status') {
    console.log('Status update:', message.data);
  }
};

// Send chat message
ws.send(JSON.stringify({
  type: 'chat',
  message: 'What vehicles were detected?'
}));

// Handle errors
ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

// Cleanup
ws.onclose = () => {
  console.log('Disconnected');
};
```

## Database Setup

Before running, ensure PostgreSQL is running:

```bash
# Create database
createdb traffic_db

# Create user
createuser traffic_user --password

# Run migrations (if using Alembic)
alembic upgrade head
```

## Redis Setup

For caching (optional but recommended):

```bash
# Start Redis
redis-server

# Or with Docker
docker run -d -p 6379:6379 redis:latest
```

## Docker Deployment

```bash
# Build image
docker build -t traffic-api:latest .

# Run container
docker run -p 8000:8000 \
  -e DATABASE_URL=postgresql+asyncpg://... \
  -e OPENAI_API_KEY=sk-... \
  traffic-api:latest
```

## File Structure

```
backend/
├── main.py                    # Application entry point
├── config.py                  # Configuration management
├── requirements.txt           # Dependencies
├── QUICKSTART.md             # This file
├── IMPLEMENTATION_SUMMARY.md # Detailed documentation
├── api/
│   ├── __init__.py          # Module exports
│   ├── schemas.py           # Pydantic models (13 models)
│   ├── routes.py            # REST endpoints (12+ routes)
│   └── websocket_routes.py  # WebSocket endpoint
├── database/                # Database layer
├── detection/               # YOLOv8 detection pipeline
├── agents/                  # LangGraph AI agent
├── stream/                  # Video streaming
└── models/                  # ML models
```

## Key Features

- **REST API**: 12+ endpoints with full OpenAPI documentation
- **WebSocket**: Real-time detection and incident streaming
- **Chat Interface**: AI agent integration with context awareness
- **Pagination**: Built-in pagination for large result sets
- **Error Handling**: Comprehensive error handling and validation
- **Health Checks**: Component health monitoring
- **Async**: Full async/await support for high performance
- **Type Safety**: 100% type hints for IDE support

## Common Issues

### ModuleNotFoundError: No module named 'database'
- Ensure you're running from the backend directory
- Check that supporting modules (database, detection, etc.) are installed

### CORS errors
- Update `CORS_ORIGINS` in config.py or .env file
- Add your frontend URL to the allowed origins list

### Database connection error
- Verify PostgreSQL is running
- Check DATABASE_URL in .env file
- Ensure database exists and user has permissions

### Model loading fails
- Download YOLOv8 model: `yolo detect predict model=yolov8l.pt source=test.mp4`
- Or specify correct MODEL_PATH in config

## Performance Tips

1. **Enable Redis caching**: Improves session lookups
2. **Use PostgreSQL connection pooling**: Set max_size in connection string
3. **Configure uvicorn workers**: Use `--workers 4` for production
4. **Batch detections**: Process multiple frames together
5. **Monitor health**: Check `/api/health` regularly

## Support

For detailed API documentation, visit:
- Swagger UI: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc

For implementation details, see `IMPLEMENTATION_SUMMARY.md`
