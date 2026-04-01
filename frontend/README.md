# Traffic Intelligence Platform - Frontend

A professional React-based dashboard for real-time traffic monitoring and analysis with AI-powered insights.

## Features

- **Real-time Video Analysis**: Stream video from files, RTSP sources, or webcam
- **Detection Visualization**: Color-coded bounding boxes with vehicle type, confidence, and track IDs
- **Live Metrics**: Vehicle counts by type, traffic flow graphs, FPS monitoring
- **Incident Tracking**: Real-time incident alerts with severity levels and location tracking
- **AI Chat Interface**: Ask questions about traffic patterns and conditions
- **WebSocket Integration**: Real-time updates via bidirectional WebSocket connection
- **Responsive Design**: Works on desktop, tablet, and mobile devices
- **Dark Theme**: Professional control room aesthetic
- **Report Generation**: Generate and download analysis reports

## Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── VideoFeed.jsx           # Video player with overlay
│   │   ├── DetectionOverlay.jsx    # SVG overlay for detections
│   │   ├── ChatPanel.jsx           # AI chat interface
│   │   ├── MetricsPanel.jsx        # Real-time metrics and charts
│   │   ├── IncidentLog.jsx         # Incident feed and alerts
│   │   ├── UploadPanel.jsx         # Video upload interface
│   │   ├── Dashboard.jsx           # Main dashboard layout
│   │   ├── Sidebar.jsx             # Navigation sidebar
│   │   └── ReportView.jsx          # Report display and export
│   ├── hooks/
│   │   ├── useWebSocket.js         # WebSocket connection hook
│   │   └── useDetections.js        # Detection state management
│   ├── services/
│   │   └── api.js                  # API service with axios
│   ├── App.jsx                     # Main app component with routing
│   ├── index.jsx                   # Entry point
│   └── index.css                   # Tailwind styles + custom CSS
├── vite.config.js                  # Vite configuration with proxy
├── tailwind.config.js              # Tailwind CSS configuration
├── postcss.config.js               # PostCSS configuration
├── package.json                    # Dependencies
└── index.html                      # HTML entry point
```

## Installation

1. Install dependencies:
```bash
npm install
```

2. Create a `.env.local` file (optional):
```
VITE_API_URL=http://localhost:8000/api
VITE_WS_URL=ws://localhost:8000/ws
```

## Development

Start the development server:
```bash
npm run dev
```

The app will be available at `http://localhost:5173` with hot module reloading.

## Building

Build for production:
```bash
npm run build
```

Preview the production build:
```bash
npm run preview
```

## Configuration

### Vite Config
- Proxies `/api` requests to `http://localhost:8000`
- Proxies `/ws` WebSocket connections to `ws://localhost:8000`
- Source maps enabled in production

### Tailwind CSS
- Dark mode enabled by default
- Custom colors: primary, secondary, accent, success, warning, danger
- Animations: pulse, blink for real-time indicators

## Components

### VideoFeed
Displays video frames with detection overlays and controls.
- Canvas-based rendering for performance
- FPS counter overlay
- Fullscreen toggle
- Loading indicators

### DetectionOverlay
SVG overlay showing:
- Bounding boxes with color-coded vehicle types
- Track IDs and confidence scores
- Trajectory trails
- Incident highlighting with pulsing effect
- Color legend

### MetricsPanel
Real-time metrics visualization:
- Vehicle count bar chart
- Detection timeline line chart
- Confidence distribution pie chart
- KPI cards (total objects, active tracks, avg confidence, latency)

### ChatPanel
AI-powered chat interface:
- Message history with user/AI distinction
- Suggested queries
- Streaming response support
- Markdown rendering

### IncidentLog
Incident feed with:
- Severity-based color coding
- Real-time filtering
- Expandable details
- Summary statistics

### UploadPanel
Media source selection:
- Drag & drop video upload
- RTSP/RTMP URL input
- Webcam selection
- Upload progress tracking

## API Integration

The frontend connects to a FastAPI backend via:

1. **REST API** - Data queries, reports, configuration
2. **WebSocket** - Real-time detections, metrics, incidents

Key endpoints:
- `POST /api/sessions` - Create new session
- `GET /api/sessions/{id}` - Get session details
- `POST /api/sessions/{id}/upload` - Upload video
- `GET /api/sessions/{id}/detections` - Get detections
- `GET /api/sessions/{id}/incidents` - Get incidents
- `POST /api/sessions/{id}/chat` - Send chat message
- `WS /ws/{session_id}` - WebSocket connection

## WebSocket Messages

Message types received from backend:
- `detection` - Vehicle detections with bounding boxes
- `incident` - Incident alert
- `metrics` - Performance metrics (FPS, latency)
- `frame` - Video frame data (base64 encoded)

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+

## Performance

- Optimized rendering with canvas and SVG
- Lazy-loaded charts with Recharts
- WebSocket auto-reconnect with exponential backoff
- Efficient state management with React hooks
- CSS animations using GPU-accelerated transforms

## Customization

### Theme Colors
Edit `tailwind.config.js` to customize:
- Primary/secondary colors
- Vehicle type colors (in DetectionOverlay)
- Severity level colors

### Chart Configuration
Modify Recharts components in `MetricsPanel.jsx` to change:
- Chart dimensions
- Data keys
- Tooltips
- Legends

### WebSocket Configuration
In `useWebSocket.js`, adjust:
- Max reconnection attempts
- Base reconnection delay (exponential backoff)
- Message retry logic

## Troubleshooting

**WebSocket connection fails**
- Ensure backend is running on configured URL
- Check CORS settings if different origin
- Verify firewall allows WebSocket traffic

**Video feed not displaying**
- Check that backend is sending frame data
- Verify video source is accessible
- Check browser console for errors

**Charts not showing**
- Ensure metrics data is being received
- Check that Recharts is properly installed
- Verify data format matches chart expectations

## Dependencies

- **React 18** - UI framework
- **React Router** - Client-side routing
- **Recharts** - Chart visualization
- **Lucide React** - Icon library
- **Axios** - HTTP client
- **Tailwind CSS** - Utility CSS framework
- **Vite** - Build tool
- **PostCSS** - CSS processing

## License

Part of the Multimodal Traffic Intelligence Platform
