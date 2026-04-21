# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Commands

### Docker (primary workflow)
```bash
docker compose up --build          # Start all services (backend :8000, frontend :3000, postgres, redis, grafana :3001)
docker compose down                # Stop all services
docker compose logs backend -f     # Stream backend logs
docker compose logs frontend -f    # Stream frontend logs
```

### Backend (local dev)
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend (local dev)
```bash
cd frontend
npm install
npm run dev        # Vite dev server on :5173
npm run build      # Production build
npm run lint       # ESLint check
```

### Database migrations
```bash
cd backend
alembic upgrade head               # Apply migrations
alembic revision --autogenerate -m "description"   # Generate new migration
```

## Architecture

### Data flow
```
Upload video → POST /api/upload → start_detection_pipeline() (background task)
    ↓
StreamProcessor (backend/stream/processor.py) — 6 concurrent asyncio stages:
  1. Frame extraction  (OpenCV VideoCapture)
  2. Detection         (YOLOv8 via VehicleDetector + EasyOCR for plates)
  3. Tracking          (DeepSORT)
  4. Incident detection
  5. Metrics broadcast (every 1 s)
  6. Batch DB writes   (every 5 s)
    ↓
WebSocket broadcast → frontend useWebSocket hook → useDetections state → React components
```

### Key files

| File | Purpose |
|------|---------|
| `backend/main.py` | FastAPI app, lifespan (loads YOLO + OCR models into AppState) |
| `backend/processing/detection.py` | Pipeline entry point; wires detector, OCR, callbacks, StreamProcessor |
| `backend/stream/processor.py` | Core async pipeline; JPEG frame encoding for live streaming |
| `backend/api/websocket_routes.py` | WS endpoint `/ws/{session_id}`, ConnectionManager, broadcast helpers |
| `backend/detection/detector.py` | VehicleDetector wrapping YOLOv8 |
| `backend/models/ocr.py` | EasyOCR singleton loader |
| `frontend/src/hooks/useWebSocket.js` | WS connection with exponential-backoff reconnect |
| `frontend/src/hooks/useDetections.js` | Detection state: current frame for overlay, history for charts |
| `frontend/src/components/Dashboard.jsx` | Wires WS messages → state → VideoFeed / MetricsPanel |
| `frontend/src/components/DetectionOverlay.jsx` | SVG bounding boxes + plate number labels |
| `frontend/src/components/VideoFeed.jsx` | Canvas frame rendering + DetectionOverlay |

### WebSocket message types
- `detection` — `{detections: [...], frame_data: "<base64-jpeg>", frame_id, timestamp}`
- `incident` — incident alert
- `metrics` — FPS, latency, counts
- `frame` — (legacy; frames now come inside `detection` messages)

Detection objects sent to the frontend have:
```json
{
  "type": "car",           // vehicle type (colour-coded in overlay)
  "class_name": "car",
  "vehicle_type": "car",
  "confidence": 0.87,
  "bbox": [x1, y1, x2, y2],   // scaled to 1280×720 stream resolution
  "plate_number": "ABC123",    // present when OCR confidence > 0.3
  "plate_confidence": 0.82
}
```

### Metric semantics
- **Total Objects** — vehicles detected in the *current frame* (not a cumulative count)
- **Active Tracks** — unique `track_id` values in the current frame
- **Vehicle Count by Type** — cumulative count across the session (bar chart)
- **Avg Confidence** — running weighted average across the session

### AI / LLM
`process_message()` in `backend/agents/langgraph_agent.py` calls the DB first to build real detection context, then calls Gemini directly (bypassing the LangGraph graph which has a session_id problem in its retrieval tools). The graph (`agents/graph.py`) exists but is not used for the primary chat path.
- `GOOGLE_API_KEY` — required for Gemini `gemini-2.5-flash`

### Environment variables
Copy `.env.example` to `.env`. Required:
- `DATABASE_URL` — postgres async URL
- `REDIS_URL`
- `MODEL_PATH` — path to YOLOv8 weights (downloaded at Docker build time)
- One of the LLM API keys above

### Performance notes
- OCR runs every 3rd frame per detection to avoid latency spikes
- JPEG frames are resized to 1280×720 at quality 60 before WebSocket broadcast
- DB writes are batched every 5 s (`batch_write_interval`) into groups of 50
- The detection queue has a back-pressure cap of 100 frames; frames are dropped when full
