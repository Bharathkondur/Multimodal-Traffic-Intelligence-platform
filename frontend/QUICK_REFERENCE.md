# Quick Reference Guide

## Installation & Running

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

## Project Structure

```
frontend/
├── src/
│   ├── components/        # 9 React components
│   ├── hooks/             # 2 custom hooks
│   ├── services/          # API service
│   ├── App.jsx            # Main app
│   ├── index.jsx          # Entry point
│   └── index.css          # Styles
├── package.json
├── vite.config.js
├── tailwind.config.js
├── index.html
└── README.md
```

## Component Reference

### Dashboard
Main container - manages layout, session state, WebSocket connection.

### VideoFeed
Displays video with canvas overlay, FPS counter, fullscreen toggle.

### DetectionOverlay
SVG overlay showing bounding boxes, tracks, trails, incident zones.

### MetricsPanel
Real-time metrics with Recharts:
- Bar chart (vehicle count)
- Line chart (detection timeline)
- Pie chart (confidence distribution)
- KPI cards

### ChatPanel
AI chat with suggested queries, message history, streaming responses.

### IncidentLog
Incident feed with severity filtering (critical/high/medium/low).

### UploadPanel
Upload video, RTSP URL, or select webcam with progress tracking.

### Sidebar
Navigation (Dashboard, Reports, Settings), theme toggle, logout.

### ReportView
Generate, view, download, print analysis reports.

## API Service Usage

```javascript
import api from './services/api'

// Create session
const response = await api.createSession({ source_type: 'file' })

// Get detections
const detections = await api.getDetections(sessionId)

// Send chat message
const reply = await api.sendMessage(sessionId, 'How many cars?')

// Upload video
const result = await api.uploadVideo(file, (progress) => {
  console.log(progress + '%')
})

// Generate report
const report = await api.generateReport(sessionId)
```

## WebSocket Hook Usage

```javascript
import { useWebSocket } from './hooks/useWebSocket'

const { isConnected, send, subscribe } = useWebSocket(
  sessionId,
  (message) => {
    if (message.type === 'detection') {
      updateDetections(message.data)
    }
  }
)

// Subscribe to channel
subscribe('detections')

// Send data
send({ type: 'request', data: {} })
```

## Detection State Hook Usage

```javascript
import { useDetections } from './hooks/useDetections'

const {
  detections,
  incidents,
  metrics,
  updateDetections,
  addIncident,
  updateMetrics,
  getDetectionsByType
} = useDetections()

// Get cars only
const cars = getDetectionsByType('car')
```

## Environment Variables

Create `.env.local`:
```
VITE_API_URL=http://localhost:8000/api
VITE_WS_URL=ws://localhost:8000/ws
```

## WebSocket Message Format

### Detection Message
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
        "trajectory": [[x, y], ...]
      }
    ],
    "metrics": {
      "fps": 30,
      "latency": 45
    }
  }
}
```

### Incident Message
```json
{
  "type": "incident",
  "data": {
    "id": "incident-123",
    "type": "collision",
    "severity": "high",
    "description": "Vehicle collision detected",
    "timestamp": "2024-01-15T10:30:00Z",
    "location": "intersection-5",
    "confidence": 0.92
  }
}
```

## Tailwind Classes

### Cards & Layout
- `.card` - Main card container
- `.card-header` - Header section
- `.card-title` - Title styling
- `.grid-responsive` - Responsive grid

### Buttons
- `.btn` - Base button
- `.btn-primary` - Blue button
- `.btn-secondary` - Gray button
- `.btn-danger` - Red button
- `.btn-sm` - Small button

### Status & Badges
- `.badge-success` - Green badge
- `.badge-warning` - Yellow badge
- `.badge-danger` - Red badge
- `.status-indicator` - Status container
- `.status-dot` - Animated dot

### Colors
- `.text-slate-100` - Light text
- `.text-slate-400` - Muted text
- `.bg-slate-900` - Dark background
- `.border-slate-800` - Dark border

## Common Patterns

### Fetching Data
```jsx
const [isLoading, setIsLoading] = useState(false)
const [error, setError] = useState(null)

useEffect(() => {
  const loadData = async () => {
    setIsLoading(true)
    try {
      const res = await api.getDetections(sessionId)
      updateDetections(res.data)
    } catch (err) {
      setError(err.message)
    } finally {
      setIsLoading(false)
    }
  }
  loadData()
}, [sessionId])
```

### Conditional Rendering
```jsx
{isLoading && <Loader className="animate-spin" />}
{error && <div className="bg-red-900">{error}</div>}
{data && <Component data={data} />}
```

### Form Input
```jsx
const [value, setValue] = useState('')

<input
  type="text"
  value={value}
  onChange={(e) => setValue(e.target.value)}
  className="input"
  placeholder="Enter text..."
/>
```

## Detection Object Structure

```javascript
{
  bbox: [x1, y1, x2, y2],              // Bounding box coordinates
  type: 'car',                         // Vehicle type
  confidence: 0.95,                    // Detection confidence 0-1
  track_id: 'track-123',               // Unique track ID
  is_incident: false,                  // Incident flag
  trajectory: [[x, y], [x, y], ...],   // Past positions
  vehicle_color: 'red',                // Optional: vehicle color
  speed: 45,                           // Optional: estimated speed
  direction: 90                        // Optional: heading degrees
}
```

## Incident Object Structure

```javascript
{
  id: 'incident-123',
  type: 'collision',
  severity: 'high',                    // critical/high/medium/low
  description: 'Vehicle collision',
  timestamp: '2024-01-15T10:30:00Z',
  location: 'intersection-5',
  confidence: 0.92,
  track_id: 'track-123',               // Related track
  vehicle_type: 'car',
  zone_id: 'zone-1',
  details: 'Additional information...'
}
```

## Metrics Object Structure

```javascript
{
  totalDetections: 42,
  vehicleCount: {
    car: 25,
    truck: 10,
    bus: 5,
    motorcycle: 2,
    bicycle: 0,
    pedestrian: 0
  },
  incidentCount: 2,
  avgConfidence: 0.92,                 // 0-1
  activeTracks: 15,
  fps: 30,
  latency: 45                          // milliseconds
}
```

## Keyboard Shortcuts

- `Enter` in chat - Send message
- `Shift+Enter` in chat - New line
- `Cmd/Ctrl+K` - Focus search (if implemented)
- `Esc` - Close modals/fullscreen

## Browser Console Commands

```javascript
// Check WebSocket status
console.log(document.querySelector('canvas'))

// Get session ID
const sessionId = new URLSearchParams(window.location.search).get('session')

// Clear localStorage
localStorage.clear()

// Check last session
console.log(localStorage.getItem('lastSessionId'))
```

## Performance Tips

1. **Limit detections array** - Keep to last 100 detections
2. **Batch updates** - Combine multiple state updates
3. **Lazy load charts** - Only render visible charts
4. **Optimize images** - Compress video frames
5. **Unsubscribe channels** - Cleanup on unmount
6. **Debounce inputs** - Reduce API calls

## Debugging

### Check Console
```javascript
// Enable debug logging
localStorage.setItem('debug', '*')

// Disable debug
localStorage.removeItem('debug')
```

### Network Tab
- Monitor API calls in DevTools
- Check WebSocket frames
- Verify frame data transfers

### React DevTools
- Inspect component props
- Track state changes
- Profile performance

## Common Issues

| Issue | Solution |
|-------|----------|
| WebSocket won't connect | Check backend is running on correct port |
| API calls fail | Verify CORS enabled on backend |
| Video not displaying | Ensure frame data is being sent |
| Charts empty | Check data structure matches schema |
| Styles not loading | Run `npm install`, check tailwind config |
| Hot reload not working | Restart dev server |

## File Size Reference

- Bundle size: ~500KB (uncompressed)
- After gzip: ~150KB
- Typical frame data: 100-200KB
- Detection payload: 1-5KB
- Chat message: <1KB

## Production Checklist

- [ ] Build passes without errors
- [ ] Test all components
- [ ] Check responsive design
- [ ] Verify API endpoints
- [ ] Test WebSocket connection
- [ ] Configure environment variables
- [ ] Enable CORS on backend
- [ ] Test file upload
- [ ] Verify error handling
- [ ] Check browser compatibility

## Resources

- React Docs: https://react.dev
- Tailwind CSS: https://tailwindcss.com
- Recharts: https://recharts.org
- Lucide Icons: https://lucide.dev
- Vite: https://vitejs.dev

## Support

For detailed info, see:
- `README.md` - Project overview
- `SETUP.md` - Installation guide
- `FILE_STRUCTURE.txt` - Complete structure
