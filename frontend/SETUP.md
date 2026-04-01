# Frontend Setup Guide

## Prerequisites

- Node.js 16+ and npm 8+
- A running FastAPI backend on localhost:8000

## Quick Start

1. **Install dependencies**:
```bash
npm install
```

2. **Start development server**:
```bash
npm run dev
```

3. **Open browser**:
Visit http://localhost:5173

## Configuration

The frontend automatically connects to the backend via proxy. If your backend is on a different host/port, create a `.env.local` file:

```bash
cp .env.example .env.local
```

Edit `.env.local`:
```
VITE_API_URL=http://your-backend-host:8000/api
VITE_WS_URL=ws://your-backend-host:8000/ws
```

## Development Workflow

### File Structure
```
src/
├── components/          # React components
│   ├── Dashboard.jsx   # Main dashboard layout
│   ├── VideoFeed.jsx   # Video player
│   ├── MetricsPanel.jsx
│   ├── ChatPanel.jsx
│   ├── IncidentLog.jsx
│   ├── UploadPanel.jsx
│   ├── Sidebar.jsx
│   ├── ReportView.jsx
│   └── DetectionOverlay.jsx
├── hooks/              # Custom React hooks
│   ├── useWebSocket.js # WebSocket management
│   └── useDetections.js # State management
├── services/           # API integration
│   └── api.js         # Axios configuration
├── App.jsx            # Main app component
├── index.jsx          # Entry point
└── index.css          # Tailwind styles
```

### Adding New Features

1. **New Component**:
Create a file in `src/components/` and export as default:
```jsx
const NewComponent = ({ prop1, prop2 }) => {
  return <div>Content</div>
}
export default NewComponent
```

2. **New API Endpoint**:
Add to `src/services/api.js`:
```js
newEndpoint: (params) =>
  apiClient.get('/new-endpoint', { params })
```

3. **New Hook**:
Create file in `src/hooks/` with `use` prefix:
```jsx
export const useNewHook = () => {
  // Hook logic
  return { state, actions }
}
```

## Component Documentation

### VideoFeed
Displays video with detection overlays.
```jsx
<VideoFeed
  detections={[]}        // Array of detection objects
  frameData={image}      // HTML Image element
  isLoading={false}      // Loading state
  isFullscreen={false}   // Fullscreen mode
  onFullscreenToggle={handleToggle}
/>
```

### MetricsPanel
Shows real-time metrics and charts.
```jsx
<MetricsPanel
  metrics={{
    vehicleCount: { car: 5, truck: 3 },
    totalDetections: 8,
    avgConfidence: 0.95,
    activeTracks: 8,
    fps: 30,
    latency: 45
  }}
  history={[]}
/>
```

### ChatPanel
AI chat interface.
```jsx
<ChatPanel
  sessionId="session-id"
  disabled={false}
/>
```

### IncidentLog
Incident feed.
```jsx
<IncidentLog
  incidents={[]}
  onIncidentClick={handleClick}
/>
```

## WebSocket Integration

The `useWebSocket` hook manages real-time connections:

```jsx
const { isConnected, send, subscribe } = useWebSocket(
  sessionId,
  (message) => {
    // Handle message
    if (message.type === 'detection') {
      updateDetections(message.data)
    }
  }
)

// Subscribe to channel
subscribe('detections')

// Send message
send({ type: 'request', data: {} })
```

Expected WebSocket messages from backend:

```json
{
  "type": "detection",
  "data": {
    "detections": [
      {
        "bbox": [x1, y1, x2, y2],
        "type": "car",
        "confidence": 0.95,
        "track_id": "track-123",
        "is_incident": false,
        "trajectory": [[x, y], [x, y]]
      }
    ],
    "metrics": {
      "fps": 30,
      "latency": 45
    }
  }
}
```

## Styling

### Tailwind CSS
Utility-first CSS framework. Edit `tailwind.config.js` to customize theme:

```js
theme: {
  colors: {
    primary: '#0066cc',
    // ... more colors
  }
}
```

### Custom Styles
Add to `src/index.css`. Key CSS classes:
- `.card` - Standard card container
- `.btn` - Button styles (btn-primary, btn-secondary, btn-danger)
- `.badge` - Badge styles (badge-success, badge-warning, etc)
- `.input` - Form input styles

### Dark Mode
Already enabled by default. Toggle with:
```jsx
document.documentElement.classList.add('dark')
```

## Performance Optimization

1. **Code Splitting**:
React Router automatically code-splits routes
```jsx
<Route path="/reports" element={<ReportView />} />
```

2. **Lazy Loading Charts**:
Charts load only when visible
```jsx
<ResponsiveContainer width="100%" height={200}>
  <LineChart data={data}>...</LineChart>
</ResponsiveContainer>
```

3. **WebSocket Efficiency**:
- Only subscribe to needed channels
- Unsubscribe when component unmounts
- Batch updates when possible

4. **Image Optimization**:
- Video frames sent as base64
- Implement image compression on backend
- Use canvas rendering for efficiency

## Testing

Add test files next to components:
```
src/components/
├── VideoFeed.jsx
├── VideoFeed.test.jsx
```

Run tests:
```bash
npm run test
```

## Build & Deployment

### Production Build
```bash
npm run build
```

Creates optimized bundle in `dist/` directory.

### Preview Production Build
```bash
npm run preview
```

### Deployment Options

1. **Static Hosting** (Vercel, Netlify):
```bash
npm run build
# Upload dist/ folder
```

2. **Docker**:
```dockerfile
FROM node:18 AS build
WORKDIR /app
COPY . .
RUN npm install && npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
```

3. **Backend Integration**:
Serve from FastAPI:
```python
from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory="frontend/dist", html=True))
```

## Troubleshooting

### Port Already in Use
Change port in vite.config.js:
```js
server: {
  port: 3000
}
```

### CORS Issues
Backend must have CORS enabled:
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)
```

### WebSocket Connection Failed
- Check backend WebSocket endpoint is running
- Verify firewall allows WebSocket traffic
- Check browser console for detailed errors
- Use `wss://` for HTTPS

### Video Not Displaying
- Verify backend sends frame data
- Check image format is valid
- Monitor network requests in DevTools
- Ensure video source is accessible

### Charts Not Showing
- Verify metrics data structure matches schema
- Check console for Recharts errors
- Ensure ResponsiveContainer has parent height

## Browser DevTools

### React DevTools
Install React DevTools browser extension for component inspection.

### Network Tab
Monitor API and WebSocket traffic:
- API calls should complete quickly
- WebSocket should show persistent connection
- Frame data should stream continuously

### Console
Check for errors and warnings. Enable debug output:
```js
localStorage.setItem('debug', '*')
```

## Environment Variables

Available in component code via `import.meta.env`:

```js
const apiUrl = import.meta.env.VITE_API_URL
const wsUrl = import.meta.env.VITE_WS_URL
```

Custom variables must start with `VITE_` prefix.

## Next Steps

1. Start the development server
2. Open http://localhost:5173
3. Upload a video or connect RTSP stream
4. Watch real-time detections and metrics
5. Ask questions in AI chat
6. Generate reports

## Support

For issues or questions:
1. Check browser console for errors
2. Verify backend is running
3. Check network requests in DevTools
4. Review component props and state
