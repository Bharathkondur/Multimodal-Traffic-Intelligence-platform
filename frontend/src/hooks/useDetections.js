import { useState, useCallback, useEffect } from 'react'

export const useDetections = () => {
  const [detections, setDetections] = useState([])
  const [detectionHistory, setDetectionHistory] = useState([])
  const [incidents, setIncidents] = useState([])
  // Scene Intelligence state — captions (VLM narration) and rule-engine alerts
  const [captions, setCaptions] = useState([])
  const [alerts, setAlerts] = useState([])
  const [metrics, setMetrics] = useState({
    totalDetections: 0,
    vehicleCount: {
      car: 0,
      truck: 0,
      bus: 0,
      motorcycle: 0,
      bicycle: 0,
      pedestrian: 0
    },
    incidentCount: 0,
    avgConfidence: 0,
    activeTracks: 0,
    fps: 0,
    latency: 0
  })

  const updateDetections = useCallback((newDetections) => {
    const updatedDetections = Array.isArray(newDetections) ? newDetections : [newDetections]

    // Current frame: replace (not accumulate) so overlay shows only live detections
    setDetections(updatedDetections)

    // Accumulate history for timeline charts
    setDetectionHistory((prev) => [
      ...prev.slice(-99),
      { timestamp: new Date(), detections: updatedDetections }
    ])

    // Update metrics: totalDetections = current frame count, vehicleCount = cumulative
    setMetrics((prev) => {
      const vehicleCount = { ...prev.vehicleCount }
      let totalConfidence = 0

      updatedDetections.forEach((det) => {
        // Backend sends class_name / vehicle_type; overlay expects type
        const type = (det.type || det.class_name || det.vehicle_type || '').toLowerCase()
        if (vehicleCount.hasOwnProperty(type)) {
          vehicleCount[type] += 1
        }
        totalConfidence += det.confidence || 0
      })

      const frameConfidence = updatedDetections.length > 0
        ? (totalConfidence / updatedDetections.length * 100)
        : 0

      // Running average confidence weighted by object count
      const prevTotal = Object.values(prev.vehicleCount).reduce((a, b) => a + b, 0)
      const newTotal = prevTotal + updatedDetections.length
      const avgConfidence = newTotal > 0
        ? ((Number(prev.avgConfidence) * prevTotal + frameConfidence * updatedDetections.length) / newTotal).toFixed(1)
        : frameConfidence.toFixed(1)

      const activeTracks = new Set(
        updatedDetections.map(d => d.track_id).filter(Boolean)
      ).size || updatedDetections.length

      return {
        ...prev,
        vehicleCount,
        totalDetections: updatedDetections.length,
        avgConfidence,
        activeTracks
      }
    })
  }, [])

  const addIncident = useCallback((incident) => {
    setIncidents((prev) => [incident, ...prev.slice(0, 99)])
    setMetrics((prev) => ({
      ...prev,
      incidentCount: prev.incidentCount + 1
    }))
  }, [])

  const addCaption = useCallback((caption) => {
    // Captions arrive every ~2s; keep the last 40 so auto-scroll stays cheap.
    setCaptions((prev) => {
      const next = [...prev, caption]
      return next.length > 40 ? next.slice(-40) : next
    })
  }, [])

  const addAlert = useCallback((alert) => {
    // Dedupe by alert_id / id so live + history merges don't double-count.
    const key = alert.alert_id || alert.id
    setAlerts((prev) => {
      if (key && prev.some((a) => (a.alert_id || a.id) === key)) return prev
      return [alert, ...prev].slice(0, 200)
    })
  }, [])

  const updateMetrics = useCallback((newMetrics) => {
    setMetrics((prev) => {
      // totalDetections and activeTracks are live-only values managed by updateDetections.
      // Never let a batch stats load overwrite them with a cumulative/historical number.
      // eslint-disable-next-line no-unused-vars
      const { totalDetections: _a, activeTracks: _b, ...rest } = newMetrics
      return { ...prev, ...rest }
    })
  }, [])

  const clearDetections = useCallback(() => {
    setDetections([])
    setDetectionHistory([])
    setIncidents([])
    setCaptions([])
    setAlerts([])
    setMetrics({
      totalDetections: 0,
      vehicleCount: {
        car: 0,
        truck: 0,
        bus: 0,
        motorcycle: 0,
        bicycle: 0,
        pedestrian: 0
      },
      incidentCount: 0,
      avgConfidence: 0,
      activeTracks: 0,
      fps: 0,
      latency: 0
    })
  }, [])

  const getDetectionsByType = useCallback((type) => {
    return detections.filter((d) => d.type?.toLowerCase() === type.toLowerCase())
  }, [detections])

  const getDetectionsByConfidence = useCallback((minConfidence) => {
    return detections.filter((d) => d.confidence >= minConfidence)
  }, [detections])

  const getIncidentsByType = useCallback((type) => {
    return incidents.filter((i) => i.type === type)
  }, [incidents])

  const getIncidentsBySeverity = useCallback((severity) => {
    return incidents.filter((i) => i.severity === severity)
  }, [incidents])

  return {
    detections,
    detectionHistory,
    incidents,
    captions,
    alerts,
    metrics,
    updateDetections,
    addIncident,
    addCaption,
    addAlert,
    updateMetrics,
    clearDetections,
    getDetectionsByType,
    getDetectionsByConfidence,
    getIncidentsByType,
    getIncidentsBySeverity
  }
}
