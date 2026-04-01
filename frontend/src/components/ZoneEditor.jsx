import React, { useState, useRef, useEffect } from 'react'
import { Trash2, Plus, Save } from 'lucide-react'
import api from '../services/api'

const ZoneEditor = ({ sessionId, canvasWidth = 1280, canvasHeight = 720, onError = null }) => {
  const canvasRef = useRef(null)
  const [zones, setZones] = useState([])
  const [currentZone, setCurrentZone] = useState(null)
  const [isDrawing, setIsDrawing] = useState(false)
  const [zoneName, setZoneName] = useState('')
  const [zoneType, setZoneType] = useState('counting')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)

  // Load zones on mount
  useEffect(() => {
    loadZones()
  }, [sessionId])

  const loadZones = async () => {
    try {
      const response = await api.getZones()
      if (response.data && response.data.zones) {
        setZones(response.data.zones)
      }
    } catch (err) {
      console.error('Failed to load zones:', err)
    }
  }

  // Draw zones on canvas
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    // Draw background
    ctx.fillStyle = 'rgba(30, 41, 59, 0.3)'
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    // Draw zones
    zones.forEach((zone) => {
      drawZone(ctx, zone)
    })

    // Draw current zone being created
    if (currentZone && currentZone.vertices.length > 0) {
      ctx.strokeStyle = '#3b82f6'
      ctx.fillStyle = 'rgba(59, 130, 246, 0.1)'
      ctx.lineWidth = 2

      // Draw lines between vertices
      ctx.beginPath()
      ctx.moveTo(currentZone.vertices[0].x, currentZone.vertices[0].y)
      for (let i = 1; i < currentZone.vertices.length; i++) {
        ctx.lineTo(currentZone.vertices[i].x, currentZone.vertices[i].y)
      }
      ctx.stroke()

      // Draw vertices
      currentZone.vertices.forEach((vertex) => {
        ctx.fillStyle = '#3b82f6'
        ctx.beginPath()
        ctx.arc(vertex.x, vertex.y, 5, 0, Math.PI * 2)
        ctx.fill()
      })
    }
  }, [zones, currentZone])

  const drawZone = (ctx, zone) => {
    if (!zone.vertices || zone.vertices.length < 2) return

    const colors = {
      counting: '#10b981',
      speed_trap: '#f59e0b',
      restricted: '#ef4444',
      parking: '#8b5cf6'
    }

    const color = colors[zone.type] || '#3b82f6'

    // Draw polygon
    ctx.strokeStyle = color
    ctx.fillStyle = `${color}20`
    ctx.lineWidth = 2

    ctx.beginPath()
    ctx.moveTo(zone.vertices[0].x, zone.vertices[0].y)
    for (let i = 1; i < zone.vertices.length; i++) {
      ctx.lineTo(zone.vertices[i].x, zone.vertices[i].y)
    }
    ctx.closePath()
    ctx.fill()
    ctx.stroke()

    // Draw label
    const centroid = calculateCentroid(zone.vertices)
    ctx.fillStyle = color
    ctx.font = 'bold 12px sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText(zone.name, centroid.x, centroid.y)
  }

  const calculateCentroid = (vertices) => {
    let x = 0, y = 0
    vertices.forEach((v) => {
      x += v.x
      y += v.y
    })
    return { x: x / vertices.length, y: y / vertices.length }
  }

  const handleCanvasClick = (e) => {
    if (!isDrawing) return

    const rect = canvasRef.current.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top

    setCurrentZone((prev) => ({
      ...prev,
      vertices: [...(prev?.vertices || []), { x, y }]
    }))
  }

  const handleCanvasDoubleClick = (e) => {
    if (!currentZone || currentZone.vertices.length < 3) return

    saveZone()
  }

  const saveZone = async () => {
    if (!currentZone || currentZone.vertices.length < 3 || !zoneName.trim()) {
      setError('Zone must have at least 3 vertices and a name')
      return
    }

    setIsLoading(true)
    setError(null)

    try {
      const zoneData = {
        name: zoneName,
        type: zoneType,
        vertices: currentZone.vertices
      }

      const response = await api.createZone(zoneData)
      setZones((prev) => [...prev, response.data])
      setCurrentZone(null)
      setZoneName('')
      setZoneType('counting')
      setIsDrawing(false)
    } catch (err) {
      const errorMsg = 'Failed to save zone'
      setError(errorMsg)
      if (onError) onError(errorMsg)
      console.error('Zone save error:', err)
    } finally {
      setIsLoading(false)
    }
  }

  const deleteZone = async (zoneId) => {
    if (!window.confirm('Delete this zone?')) return

    try {
      await api.deleteZone(zoneId)
      setZones((prev) => prev.filter((z) => z.id !== zoneId))
    } catch (err) {
      const errorMsg = 'Failed to delete zone'
      setError(errorMsg)
      if (onError) onError(errorMsg)
    }
  }

  const cancelDrawing = () => {
    setCurrentZone(null)
    setZoneName('')
    setZoneType('counting')
    setIsDrawing(false)
  }

  return (
    <div className="space-y-4">
      {/* Error */}
      {error && (
        <div className="card bg-red-900 border border-red-700">
          <p className="text-sm text-red-200">{error}</p>
        </div>
      )}

      {/* Canvas Area */}
      <div className="card p-0">
        <div className="card-header">
          <h3 className="card-title">Zone Drawing</h3>
          <div className="ml-auto text-xs text-slate-400">
            {isDrawing ? 'Click to add vertices, double-click to finish' : 'Click "New Zone" to start drawing'}
          </div>
        </div>
        <canvas
          ref={canvasRef}
          width={canvasWidth}
          height={canvasHeight}
          onClick={handleCanvasClick}
          onDoubleClick={handleCanvasDoubleClick}
          className="w-full bg-slate-900 cursor-crosshair border-b border-slate-700"
          style={{ maxHeight: '400px' }}
        />
      </div>

      {/* Zone Configuration */}
      {isDrawing && (
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Zone Configuration</h3>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">Zone Name</label>
              <input
                type="text"
                value={zoneName}
                onChange={(e) => setZoneName(e.target.value)}
                placeholder="e.g., Main Intersection"
                className="input w-full"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">Zone Type</label>
              <select value={zoneType} onChange={(e) => setZoneType(e.target.value)} className="input w-full">
                <option value="counting">Vehicle Counting</option>
                <option value="speed_trap">Speed Trap</option>
                <option value="restricted">Restricted Area</option>
                <option value="parking">Parking Zone</option>
              </select>
            </div>

            <div className="flex gap-2">
              <button
                onClick={saveZone}
                disabled={isLoading || !zoneName.trim() || !currentZone || currentZone.vertices.length < 3}
                className="btn btn-primary flex-1 flex items-center justify-center gap-2"
              >
                <Save className="w-4 h-4" />
                Save Zone
              </button>
              <button onClick={cancelDrawing} className="btn btn-secondary flex-1">
                Cancel
              </button>
            </div>

            {currentZone && (
              <p className="text-xs text-slate-400">
                Vertices: {currentZone.vertices.length} (minimum 3 required)
              </p>
            )}
          </div>
        </div>
      )}

      {/* Start New Zone Button */}
      {!isDrawing && (
        <button onClick={() => setIsDrawing(true)} className="btn btn-primary w-full flex items-center justify-center gap-2">
          <Plus className="w-4 h-4" />
          New Zone
        </button>
      )}

      {/* Zones List */}
      {zones.length > 0 && (
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Created Zones ({zones.length})</h3>
          </div>

          <div className="space-y-2 max-h-64 overflow-y-auto">
            {zones.map((zone) => (
              <div key={zone.id} className="p-3 bg-slate-800 rounded border border-slate-700">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1">
                    <p className="font-semibold text-slate-200">{zone.name}</p>
                    <p className="text-xs text-slate-400 capitalize">{zone.type.replace('_', ' ')}</p>
                    {zone.stats && (
                      <p className="text-xs text-slate-500 mt-1">
                        {zone.type === 'counting'
                          ? `Vehicles: ${zone.stats.vehicle_count || 0}`
                          : zone.type === 'speed_trap'
                          ? `Avg Speed: ${zone.stats.average_speed || 0} km/h`
                          : `Occupancy: ${zone.stats.occupancy || 0}%`}
                      </p>
                    )}
                  </div>
                  <button
                    onClick={() => deleteZone(zone.id)}
                    className="btn btn-danger btn-sm"
                    title="Delete zone"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default ZoneEditor
