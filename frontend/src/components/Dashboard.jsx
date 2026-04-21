import React, { useState, useEffect, useCallback } from 'react'
import { AlertCircle, Grid3x3, List, Upload, X, Eye, MessageSquare } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import VideoFeed from './VideoFeed'
import MetricsPanel from './MetricsPanel'
import ChatPanel from './ChatPanel'
import IncidentLog from './IncidentLog'
import UploadPanel from './UploadPanel'
import LiveTranscript from './LiveTranscript'
import WatchlistPanel from './WatchlistPanel'
import AlertHistoryPanel from './AlertHistoryPanel'
import { useDetections } from '../hooks/useDetections'
import { useWebSocket } from '../hooks/useWebSocket'
import api from '../services/api'

const Dashboard = ({ sessionId: initialSessionId = null, onSessionChange = null }) => {
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState('live')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [layoutMode, setLayoutMode] = useState('grid')
  const [frameData, setFrameData] = useState(null)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [showUpload, setShowUpload] = useState(false)
  const [sessionId, setSessionId] = useState(initialSessionId)
  const [metricsHistory, setMetricsHistory] = useState([])
  // Scene Intelligence: toggle between the incident log (legacy) and
  // the three new panels (watchlist / live transcript / alert history).
  const [sceneSidebar, setSceneSidebar] = useState('scene')

  const {
    detections,
    incidents,
    captions,
    alerts,
    metrics,
    updateDetections,
    addIncident,
    addCaption,
    addAlert,
    updateMetrics,
    clearDetections
  } = useDetections()

  // WebSocket handler with proper channel parsing
  const handleWebSocketMessage = useCallback((message) => {
    if (message.type === 'detection') {
      const frameDetections = message.data.detections || []
      // Normalise type field: backend may send class_name / vehicle_type
      const normalised = frameDetections.map(d => ({
        ...d,
        type: d.type || d.class_name || d.vehicle_type || 'car'
      }))
      updateDetections(normalised)
      if (message.data.frame_data) {
        const img = new Image()
        img.src = 'data:image/jpeg;base64,' + message.data.frame_data
        img.onload = () => setFrameData(img)
      }
      if (message.data.metrics) {
        updateMetrics(message.data.metrics)
      }
    } else if (message.type === 'incident') {
      addIncident(message.data)
    } else if (message.type === 'metrics') {
      updateMetrics(message.data)
      setMetricsHistory((prev) => [...prev.slice(-99), { timestamp: new Date(), ...message.data }])
    } else if (message.type === 'heatmap') {
      // Handle heatmap data if needed
      console.log('Heatmap update received')
    } else if (message.type === 'caption') {
      // Scene Intelligence: VLM narration (arrives every ~2s)
      addCaption(message.data)
    } else if (message.type === 'alert') {
      // Scene Intelligence: rule-engine alerts
      addAlert(message.data)
    } else if (message.type === 'frame') {
      if (message.data.frame_data) {
        const img = new Image()
        img.src = 'data:image/jpeg;base64,' + message.data.frame_data
        img.onload = () => setFrameData(img)
      }
    }
  }, [updateDetections, addIncident, addCaption, addAlert, updateMetrics])

  // Sync when parent passes a new sessionId (e.g. from URL param)
  useEffect(() => {
    if (initialSessionId && initialSessionId !== sessionId) {
      setSessionId(initialSessionId)
      clearDetections()
      setFrameData(null)
    }
  }, [initialSessionId])

  const { isConnected, error: wsError, send, subscribe } = useWebSocket(
    sessionId,
    handleWebSocketMessage,
    { maxReconnectAttempts: 10, baseReconnectDelay: 1000, maxDelay: 8000 }
  )

  // Subscribe to channels when connected
  useEffect(() => {
    if (isConnected && sessionId) {
      subscribe('detections')
      subscribe('incidents')
      subscribe('metrics')
      subscribe('captions')
      subscribe('alerts')
    }
  }, [isConnected, sessionId, subscribe])

  // Load initial data
  useEffect(() => {
    if (sessionId) {
      loadSessionData()
    }
  }, [sessionId])

  const loadSessionData = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const responses = await Promise.allSettled([
        api.getSession(sessionId),
        api.getIncidents(sessionId),
        api.getStats(sessionId)
      ])

      // Load historical incidents
      if (responses[1].status === 'fulfilled' && responses[1].value.data) {
        const incidentData = responses[1].value.data
        const list = Array.isArray(incidentData) ? incidentData : incidentData.incidents || []
        list.forEach(inc => addIncident(inc))
      }

      // Load aggregate session stats for charts (vehicle counts, confidence, etc.)
      // Do NOT pass raw detection records to updateDetections — that sets "Total Objects"
      // to the batch size (100). totalDetections is reserved for the live per-frame count.
      if (responses[2].status === 'fulfilled' && responses[2].value.data) {
        const stats = responses[2].value.data
        updateMetrics({
          vehicleCount: stats.vehicleCount || stats.vehicle_count || {},
          avgConfidence: stats.avgConfidence ?? stats.avg_confidence ?? 0,
          fps: stats.fps ?? 0,
          latency: stats.latency ?? 0,
          // totalDetections is intentionally NOT set here — it shows the live frame count
        })
      }
    } catch (err) {
      setError('Failed to load session data')
      console.error('Load error:', err)
    } finally {
      setIsLoading(false)
    }
  }

  const statusColor = isConnected ? 'text-green-500' : 'text-red-500'

  return (
    <div className="w-full h-full flex flex-col bg-slate-950">
      {/* Header */}
      <div className="bg-slate-900 border-b border-slate-800 px-4 py-3 flex items-center justify-between flex-shrink-0">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Scene Intelligence Dashboard</h1>
          <div className="flex items-center gap-4 mt-1 text-sm">
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${statusColor} animate-pulse`}></span>
              <span className="text-slate-400">{isConnected ? 'Connected' : 'Disconnected'}</span>
            </div>
            {sessionId && (
              <span className="text-slate-500 font-mono text-xs">Session: {sessionId.slice(0, 8)}...</span>
            )}
            {captions.length > 0 && (
              <span className="text-cyan-400 font-mono text-xs flex items-center gap-1">
                <MessageSquare className="w-3 h-3" /> {captions.length} captions
              </span>
            )}
            {alerts.length > 0 && (
              <span className="text-red-400 font-mono text-xs flex items-center gap-1">
                <Eye className="w-3 h-3" /> {alerts.length} alerts
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setLayoutMode(layoutMode === 'grid' ? 'fullscreen' : 'grid')}
            className="btn btn-secondary btn-sm"
            title="Toggle layout"
          >
            {layoutMode === 'grid' ? (
              <Grid3x3 className="w-4 h-4" />
            ) : (
              <List className="w-4 h-4" />
            )}
          </button>
          <button
            onClick={() => setShowUpload(!showUpload)}
            className={`btn btn-sm ${showUpload ? 'btn-primary' : 'btn-secondary'}`}
            title="Upload video"
          >
            {showUpload ? <X className="w-4 h-4" /> : <Upload className="w-4 h-4" />}
            <span className="ml-1 text-xs">{showUpload ? 'Close' : 'Upload'}</span>
          </button>
        </div>
      </div>

      {/* Upload Slide-down Panel */}
      {showUpload && (
        <div className="bg-slate-900 border-b border-slate-700 px-4 py-4 flex-shrink-0">
          <UploadPanel
            onUploadComplete={(result) => {
              if (result.sessionId) {
                setSessionId(result.sessionId)
                clearDetections()
                setFrameData(null)
                if (onSessionChange) onSessionChange(result.sessionId)
                navigate(`/?session=${result.sessionId}`)
              }
              setShowUpload(false)
            }}
          />
        </div>
      )}

      {/* Error Banner */}
      {error && (
        <div className="bg-red-900 border-b border-red-700 px-4 py-2 flex items-center gap-2 flex-shrink-0">
          <AlertCircle className="w-5 h-5 text-red-400" />
          <p className="text-sm text-red-200">{error}</p>
          <button
            onClick={() => setError(null)}
            className="ml-auto text-red-400 hover:text-red-300"
          >
            ✕
          </button>
        </div>
      )}

      {/* Main Content */}
      <div className="flex-1 overflow-hidden">
        {!sessionId ? (
          // No session — show upload prompt
          <div className="h-full flex items-center justify-center p-4">
            <div className="text-center space-y-4">
              <Upload className="w-16 h-16 text-slate-600 mx-auto" />
              <p className="text-slate-400 text-lg">No active session</p>
              <p className="text-slate-500 text-sm">Click the Upload button in the header to start analysing a video</p>
              <button
                onClick={() => setShowUpload(true)}
                className="btn btn-primary"
              >
                <Upload className="w-4 h-4 mr-2" />
                Upload Video
              </button>
            </div>
          </div>
        ) : layoutMode === 'grid' ? (
          // Scene Intelligence grid: video (2 cols tall) · metrics · watchlist/alerts tabs
          //                                               · transcript · chat
          <div
            className="h-full p-4 gap-4 overflow-auto"
            style={{
              display: 'grid',
              gridTemplateColumns: '1.6fr 1fr 1fr',
              gridTemplateRows: '1fr 1fr',
              gridAutoFlow: 'dense',
            }}
          >
            {/* Col 1: Large Video Feed — spans both rows */}
            <div className="min-h-0 card p-0 row-span-2">
              <VideoFeed
                detections={detections}
                frameData={frameData}
                isLoading={isLoading}
                isFullscreen={isFullscreen}
                onFullscreenToggle={() => setIsFullscreen(!isFullscreen)}
              />
            </div>

            {/* Col 2 top: Metrics */}
            <div className="min-h-0 card p-4 overflow-y-auto">
              <MetricsPanel metrics={metrics} history={metricsHistory} />
            </div>

            {/* Col 3 top: Watchlist OR Incidents (togglable) */}
            <div className="min-h-0 flex flex-col gap-2">
              <div className="flex items-center gap-1 text-xs">
                <button
                  onClick={() => setSceneSidebar('scene')}
                  className={`px-2.5 py-1 rounded font-mono tracking-wide transition-colors ${
                    sceneSidebar === 'scene'
                      ? 'bg-cyan-700 text-white'
                      : 'bg-slate-800 text-slate-400 hover:text-slate-200'
                  }`}
                >
                  watchlist
                </button>
                <button
                  onClick={() => setSceneSidebar('legacy')}
                  className={`px-2.5 py-1 rounded font-mono tracking-wide transition-colors ${
                    sceneSidebar === 'legacy'
                      ? 'bg-cyan-700 text-white'
                      : 'bg-slate-800 text-slate-400 hover:text-slate-200'
                  }`}
                >
                  incidents
                </button>
              </div>
              <div className="flex-1 min-h-0">
                {sceneSidebar === 'scene' ? (
                  <WatchlistPanel sessionId={sessionId} disabled={!isConnected} />
                ) : (
                  <div className="h-full card p-0">
                    <IncidentLog incidents={incidents} />
                  </div>
                )}
              </div>
            </div>

            {/* Col 2 bottom: Live Transcript */}
            <div className="min-h-0">
              <LiveTranscript captions={captions} />
            </div>

            {/* Col 3 bottom: Alert History OR Chat */}
            <div className="min-h-0">
              {sceneSidebar === 'scene' ? (
                <AlertHistoryPanel sessionId={sessionId} liveAlerts={alerts} />
              ) : (
                <div className="h-full card p-0">
                  <ChatPanel sessionId={sessionId} disabled={!isConnected} />
                </div>
              )}
            </div>
          </div>
        ) : (
          // Fullscreen video layout
          <div className="h-full flex flex-col gap-4 p-4">
            <div className="flex-1 card p-0">
              <VideoFeed
                detections={detections}
                frameData={frameData}
                isLoading={isLoading}
                isFullscreen={isFullscreen}
                onFullscreenToggle={() => setIsFullscreen(!isFullscreen)}
              />
            </div>

            <div className="grid grid-cols-3 gap-4 h-48">
              <div className="card p-0">
                <ChatPanel sessionId={sessionId} disabled={!isConnected} />
              </div>
              <div className="col-span-2 card p-0">
                <IncidentLog incidents={incidents} />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Mobile Bottom Navigation */}
      <div className="lg:hidden border-t border-slate-800 bg-slate-900 px-4 py-2 flex gap-2 overflow-x-auto flex-shrink-0">
        {['live', 'metrics', 'incidents', 'chat'].map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 rounded text-sm font-medium whitespace-nowrap transition-colors ${
              activeTab === tab
                ? 'bg-blue-600 text-white'
                : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
            }`}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>
    </div>
  )
}

export default Dashboard
