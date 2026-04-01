import React, { useState, useEffect, useRef } from 'react'
import { RefreshCw, Eye, EyeOff } from 'lucide-react'
import api from '../services/api'

const HeatmapOverlay = ({ sessionId, enabled = true, onError = null }) => {
  const [heatmapData, setHeatmapData] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [opacity, setOpacity] = useState(0.5)
  const [refreshInterval, setRefreshInterval] = useState(5) // seconds
  const [isVisible, setIsVisible] = useState(true)
  const refreshIntervalRef = useRef(null)
  const canvasRef = useRef(null)

  // Fetch heatmap data
  const fetchHeatmap = async () => {
    if (!sessionId || !enabled) return

    setIsLoading(true)
    setError(null)

    try {
      const response = await api.getHeatmap(sessionId)
      if (response.data && response.data.heatmap) {
        setHeatmapData(response.data.heatmap)
      }
    } catch (err) {
      const errorMsg = 'Failed to load heatmap'
      setError(errorMsg)
      if (onError) onError(errorMsg)
      console.error('Heatmap error:', err)
    } finally {
      setIsLoading(false)
    }
  }

  // Set up auto-refresh
  useEffect(() => {
    if (!enabled || !sessionId) return

    fetchHeatmap() // Initial fetch

    refreshIntervalRef.current = setInterval(() => {
      fetchHeatmap()
    }, refreshInterval * 1000)

    return () => {
      if (refreshIntervalRef.current) {
        clearInterval(refreshIntervalRef.current)
      }
    }
  }, [sessionId, enabled, refreshInterval])

  // Render heatmap on canvas
  useEffect(() => {
    if (!heatmapData || !canvasRef.current || !isVisible) return

    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')

    // Decode base64 heatmap image
    const img = new Image()
    img.onload = () => {
      ctx.globalAlpha = opacity
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
      ctx.globalAlpha = 1
    }
    img.src = `data:image/png;base64,${heatmapData}`
  }, [heatmapData, opacity, isVisible])

  return (
    <div className="card">
      <div className="card-header flex justify-between items-center">
        <h3 className="card-title">Traffic Heatmap</h3>
        <div className="flex gap-2">
          <button
            onClick={() => setIsVisible(!isVisible)}
            className="btn btn-secondary btn-sm"
            title={isVisible ? 'Hide heatmap' : 'Show heatmap'}
          >
            {isVisible ? (
              <Eye className="w-4 h-4" />
            ) : (
              <EyeOff className="w-4 h-4" />
            )}
          </button>
          <button
            onClick={fetchHeatmap}
            disabled={isLoading}
            className="btn btn-secondary btn-sm"
            title="Refresh heatmap"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="p-4 bg-red-900 border-b border-red-700">
          <p className="text-sm text-red-200">{error}</p>
        </div>
      )}

      {/* Heatmap Canvas */}
      {isVisible && (
        <div className="p-4 space-y-4">
          <canvas
            ref={canvasRef}
            className="w-full h-64 bg-slate-800 rounded border border-slate-700"
            width={640}
            height={480}
          />

          {/* Controls */}
          <div className="space-y-3">
            {/* Opacity Slider */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <label className="text-sm font-medium text-slate-300">Opacity</label>
                <span className="text-xs text-slate-400">{Math.round(opacity * 100)}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="1"
                step="0.1"
                value={opacity}
                onChange={(e) => setOpacity(parseFloat(e.target.value))}
                className="w-full"
              />
            </div>

            {/* Refresh Interval */}
            <div>
              <label className="text-sm font-medium text-slate-300 block mb-2">
                Refresh Interval
              </label>
              <select
                value={refreshInterval}
                onChange={(e) => setRefreshInterval(parseInt(e.target.value))}
                className="input w-full text-sm"
              >
                <option value={1}>1 second</option>
                <option value={5}>5 seconds</option>
                <option value={10}>10 seconds</option>
                <option value={30}>30 seconds</option>
              </select>
            </div>
          </div>

          {/* Info */}
          {heatmapData && (
            <div className="text-xs text-slate-400 bg-slate-900 p-2 rounded">
              <p>Darker red areas indicate high traffic concentration</p>
            </div>
          )}
        </div>
      )}

      {!isVisible && (
        <div className="p-4 text-center">
          <p className="text-slate-400 text-sm">Heatmap hidden</p>
        </div>
      )}
    </div>
  )
}

export default HeatmapOverlay
