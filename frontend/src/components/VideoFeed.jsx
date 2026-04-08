import React, { useRef, useEffect, useState } from 'react'
import { Maximize2, Minimize2, AlertCircle } from 'lucide-react'
import DetectionOverlay from './DetectionOverlay'

const VideoFeed = ({
  detections = [],
  frameData = null,
  isLoading = false,
  isFullscreen = false,
  onFullscreenToggle = null
}) => {
  const canvasRef = useRef(null)

  // Keep the current frame in a ref so the RAF loop always reads the latest value
  // without needing to restart itself when frameData changes.
  const frameDataRef = useRef(null)
  const fpsRef = useRef(0)
  const frameCountRef = useRef(0)
  const lastFpsTimeRef = useRef(Date.now())

  const [fps, setFps] = useState(0)

  // Sync prop → ref (doesn't trigger effect restarts)
  useEffect(() => {
    frameDataRef.current = frameData
  }, [frameData])

  // Single RAF render loop — starts once on mount, never restarts.
  // Reading frameDataRef.current ensures we always draw the latest frame.
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let rafId

    const renderFrame = () => {
      const fd = frameDataRef.current

      // Clear canvas
      ctx.fillStyle = '#000000'
      ctx.fillRect(0, 0, canvas.width, canvas.height)

      if (fd) {
        try {
          ctx.drawImage(fd, 0, 0, canvas.width, canvas.height)
        } catch (_) {
          // image not decoded yet — skip this tick
        }

        // FPS calculation
        frameCountRef.current += 1
        const now = Date.now()
        if (now - lastFpsTimeRef.current >= 1000) {
          fpsRef.current = frameCountRef.current
          setFps(frameCountRef.current)
          frameCountRef.current = 0
          lastFpsTimeRef.current = now
        }

        // FPS badge
        ctx.fillStyle = 'rgba(0,0,0,0.55)'
        ctx.fillRect(6, 6, 84, 26)
        ctx.fillStyle = '#22c55e'
        ctx.font = 'bold 13px monospace'
        ctx.fillText(`FPS: ${fpsRef.current}`, 12, 24)
      }

      rafId = requestAnimationFrame(renderFrame)
    }

    rafId = requestAnimationFrame(renderFrame)

    // Cancel on unmount — prevents memory leaks and zombie loops
    return () => cancelAnimationFrame(rafId)
  }, []) // ← empty deps: one loop for the lifetime of this component

  const containerClass = isFullscreen ? 'fixed inset-0 z-50 bg-black' : 'video-container'

  return (
    <div className={containerClass}>
      <div className="relative w-full h-full">
        {/* Video canvas */}
        <canvas
          ref={canvasRef}
          className="w-full h-full bg-black"
          width={1280}
          height={720}
        />

        {/* Detection bounding-box overlay */}
        <DetectionOverlay
          detections={detections}
          width={1280}
          height={720}
        />

        {/* Loading spinner */}
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-black bg-opacity-50">
            <div className="text-center">
              <div className="w-12 h-12 rounded-full border-4 border-blue-500 border-t-transparent animate-spin mx-auto mb-4" />
              <p className="text-white">Processing video...</p>
            </div>
          </div>
        )}

        {/* No-input placeholder */}
        {!frameData && !isLoading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-gradient-to-br from-slate-900 to-slate-950 gap-4">
            <AlertCircle className="w-16 h-16 text-slate-500" />
            <p className="text-slate-400 text-lg">Waiting for video stream…</p>
            <p className="text-slate-500 text-sm">Upload a video to see live detections</p>
          </div>
        )}

        {/* Fullscreen toggle */}
        <div className="absolute bottom-4 right-4">
          <button
            onClick={onFullscreenToggle}
            className="btn btn-secondary btn-sm"
            title={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
          >
            {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
        </div>

        {/* Object count badge */}
        {detections.length > 0 && (
          <div className="absolute top-4 right-4 bg-slate-900 bg-opacity-90 px-3 py-2 rounded border border-slate-700">
            <p className="text-sm text-blue-400 font-mono">
              Objects: {detections.length}
            </p>
          </div>
        )}

        {/* Incident alert */}
        {detections.some(d => d.is_incident) && (
          <div className="absolute top-14 right-4 animate-pulse">
            <div className="bg-red-900 border-2 border-red-500 rounded-lg px-4 py-2 text-red-100 font-semibold flex items-center gap-2">
              <span className="w-2 h-2 bg-red-500 rounded-full animate-pulse" />
              INCIDENT DETECTED
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default VideoFeed
