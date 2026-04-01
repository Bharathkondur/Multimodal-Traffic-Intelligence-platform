import React, { useRef, useEffect, useState } from 'react'
import { Maximize2, Minimize2, AlertCircle } from 'lucide-react'
import DetectionOverlay from './DetectionOverlay'

const VideoFeed = ({ detections = [], frameData = null, isLoading = false, isFullscreen = false, onFullscreenToggle = null }) => {
  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const [fps, setFps] = useState(0)
  const [latency, setLatency] = useState(0)
  const fpsRef = useRef(0)
  const frameCountRef = useRef(0)
  const lastTimeRef = useRef(Date.now())

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // Handle frame rendering
    const renderFrame = () => {
      // Clear canvas
      ctx.fillStyle = '#000000'
      ctx.fillRect(0, 0, canvas.width, canvas.height)

      // Draw frame data if available
      if (frameData) {
        ctx.drawImage(frameData, 0, 0, canvas.width, canvas.height)

        // Calculate FPS
        frameCountRef.current += 1
        const now = Date.now()
        const elapsed = now - lastTimeRef.current

        if (elapsed >= 1000) {
          fpsRef.current = frameCountRef.current
          setFps(frameCountRef.current)
          frameCountRef.current = 0
          lastTimeRef.current = now
        }

        // Draw FPS counter
        ctx.fillStyle = '#22c55e'
        ctx.strokeStyle = '#16a34a'
        ctx.lineWidth = 2
        ctx.font = 'bold 14px monospace'
        const fpsText = `FPS: ${fpsRef.current}`
        ctx.strokeRect(8, 8, 80, 28)
        ctx.fillText(fpsText, 14, 28)

        // Draw latency
        ctx.fillStyle = '#3b82f6'
        ctx.strokeStyle = '#1e40af'
        const latencyText = `${latency}ms`
        ctx.font = '12px monospace'
        ctx.fillText(latencyText, 14, 50)
      }

      requestAnimationFrame(renderFrame)
    }

    renderFrame()
  }, [frameData, latency])

  const containerClass = isFullscreen
    ? 'fixed inset-0 z-50 bg-black'
    : 'video-container'

  const toggleFullscreen = () => {
    if (onFullscreenToggle) {
      onFullscreenToggle()
    }
  }

  return (
    <div className={containerClass}>
      <div className={isFullscreen ? 'relative w-full h-full' : 'relative w-full h-full'}>
        {/* Video Canvas */}
        <canvas
          ref={canvasRef}
          className="w-full h-full bg-black"
          width={1280}
          height={720}
        />

        {/* Detection Overlay */}
        <DetectionOverlay
          detections={detections}
          width={1280}
          height={720}
        />

        {/* Loading Indicator */}
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-black bg-opacity-50">
            <div className="text-center">
              <div className="w-12 h-12 rounded-full border-4 border-blue-500 border-t-transparent animate-spin mx-auto mb-4"></div>
              <p className="text-white">Loading stream...</p>
            </div>
          </div>
        )}

        {/* No Input Indicator */}
        {!frameData && !isLoading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-gradient-to-br from-slate-900 to-slate-950 gap-4">
            <AlertCircle className="w-16 h-16 text-slate-500" />
            <p className="text-slate-400 text-lg">No video source selected</p>
            <p className="text-slate-500 text-sm">Upload a video, enter RTSP URL, or select webcam to begin</p>
          </div>
        )}

        {/* Controls */}
        <div className="absolute bottom-4 right-4 flex gap-2">
          <button
            onClick={toggleFullscreen}
            className="btn btn-secondary btn-sm"
            title={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
          >
            {isFullscreen ? (
              <Minimize2 className="w-4 h-4" />
            ) : (
              <Maximize2 className="w-4 h-4" />
            )}
          </button>
        </div>

        {/* Detections Counter */}
        {detections.length > 0 && (
          <div className="absolute top-4 right-4 bg-slate-900 bg-opacity-90 px-3 py-2 rounded border border-slate-700">
            <p className="text-sm text-blue-400 font-mono">
              Objects: {detections.length}
            </p>
          </div>
        )}

        {/* Critical Incident Alert */}
        {detections.some(d => d.is_incident) && (
          <div className="absolute top-20 right-4 animate-pulse">
            <div className="bg-red-900 border-2 border-red-500 rounded-lg px-4 py-2 text-red-100 font-semibold flex items-center gap-2">
              <span className="w-2 h-2 bg-red-500 rounded-full animate-pulse"></span>
              INCIDENT DETECTED
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default VideoFeed
