import React, { useState, useEffect, useCallback } from 'react'
import { AlertCircle, Settings, Grid3x3, List, Navigate } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import VideoFeed from './VideoFeed'
import MetricsPanel from './MetricsPanel'
import ChatPanel from './ChatPanel'
import IncidentLog from './IncidentLog'
import DemoControls from './DemoControls'
import { useDetections } from '../hooks/useDetections'
import { useWebSocket } from '../hooks/useWebSocket'
import api from '../services/api'

const Dashboard = ({ sessionId = null }) => {
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState('live')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [layoutMode, setLayoutMode] = useState('grid')
  const [frameData, setFrameData] = useState(null)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [metricsHistory, setMetricsHistory] = useState([])

  const {
    detections,
    incidents,
    metrics,
    updateDetections,
    addIncident,
    updateMetrics,
    clearDetections
  } = useDetections()

  // WebSocket handler with proper channel parsing
  const handleWebSocketMessage = useCallback((message) => {
    if (message.type === 'detection') {
      updateDetections(message.data.detections || [])
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
    } else if (message.type === 'frame') {
      if (message.data.frame_data) {
        const img = new Image()
        img.src = 'data:image/jpeg;base64,' + message.data.frame_data
        img.onload = () => setFrameData(img)
      }
    }
  }, [updateDetections, addIncident, updateMetrics])

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
        api.getDetections(sessionId, 0, 100),
        api.getIncidents(sessionId),
        api.getStats(sessionId)
      ])

      if (responses[1].status === 'fulfilled' && responses[1].value.data) {
        const detectionData = responses[1].value.data
        updateDetections(Array.isArray(detectionData) ? detectionData : detectionData.detections || [])
      }

      if (responses[3].status === 'fulfilled' && responses[3].value.data) {
        updateMetrics(responses[3].value.data)
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
          <h1 className="text-2xl font-bold text-slate-100">Traffic Intelligence Dashboard</h1>
          <div className="flex items-center gap-4 mt-1 text-sm">
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${statusColor} animate-pulse`}></span>
              <span className="text-slate-400">{isConnected ? 'Connected' : 'Disconnected'}</span>
            </div>
            {sessionId && (
              <span className="text-slate-500 font-mono text-xs">Session: {sessionId.slice(0, 8)}...</span>
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
            onClick={() => navigate('/upload')}
            className="btn btn-secondary btn-sm"
            title="Upload video"
          >
            <Navigate className="w-4 h-4" />
          </button>
        </div>
      </div>

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
          // No session - show demo controls
          <div className="h-full flex items-center justify-center p-4">
            <div className="max-w-2xl w-full">
              <DemoControls onSessionCreated={(id) => window.location.href = `/?session=${id}`} />
            </div>
          </div>
        ) : layoutMode === 'grid' ? (
          // Grid layout: 2 columns, 2 rows
          <div className="h-full p-4 gap-4 overflow-auto" style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gridTemplateRows: '1fr 1fr', gridAutoFlow: 'dense' }}>
            {/* Top-left: Large Video Feed */}
            <div className="min-h-0 card p-0 row-span-2">
              <VideoFeed
                detections={detections}
                frameData={frameData}
                isLoading={isLoading}
                isFullscreen={isFullscreen}
                onFullscreenToggle={() => setIsFullscreen(!isFullscreen)}
              />
            </div>

            {/* Top-right: Metrics Panel */}
            <div className="min-h-0 card p-4 overflow-y-auto">
              <MetricsPanel metrics={metrics} history={metricsHistory} />
            </div>

            {/* Bottom-left: Chat Panel */}
            <div className="min-h-0 card p-0">
              <ChatPanel sessionId={sessionId} disabled={!isConnected} />
            </div>

            {/* Bottom-right: Incident Log */}
            <div className="min-h-0 card p-0">
              <IncidentLog incidents={incidents} />
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
