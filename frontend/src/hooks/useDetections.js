import { useState, useCallback, useEffect } from 'react'

export const useDetections = () => {
  const [detections, setDetections] = useState([])
  const [detectionHistory, setDetectionHistory] = useState([])
  const [incidents, setIncidents] = useState([])
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
    // Maintain rolling window of last 100 detections
    const updatedDetections = Array.isArray(newDetections) ? newDetections : [newDetections]
    setDetections((prev) => {
      const combined = [...prev, ...updatedDetections]
      return combined.slice(-100)
    })

    // Aggregate metrics from current window
    setDetections((currentDetections) => {
      const vehicleCount = {
        car: 0,
        truck: 0,
        bus: 0,
        motorcycle: 0,
        bicycle: 0,
        pedestrian: 0
      }

      let totalConfidence = 0

      currentDetections.forEach((det) => {
        const type = det.type?.toLowerCase() || 'car'
        if (vehicleCount.hasOwnProperty(type)) {
          vehicleCount[type] += 1
        }
        totalConfidence += det.confidence || 0
      })

      const avgConfidence = currentDetections.length > 0
        ? (totalConfidence / currentDetections.length * 100).toFixed(1)
        : 0

      const activeTracks = new Set(currentDetections.map(d => d.track_id)).size

      setMetrics((prev) => ({
        ...prev,
        vehicleCount,
        totalDetections: currentDetections.length,
        avgConfidence,
        activeTracks
      }))

      return currentDetections
    })

    // Keep history (last 100 snapshots)
    setDetectionHistory((prev) => [
      ...prev.slice(-99),
      { timestamp: new Date(), detections: updatedDetections }
    ])
  }, [])

  const addIncident = useCallback((incident) => {
    setIncidents((prev) => [incident, ...prev.slice(0, 99)])
    setMetrics((prev) => ({
      ...prev,
      incidentCount: prev.incidentCount + 1
    }))
  }, [])

  const updateMetrics = useCallback((newMetrics) => {
    setMetrics((prev) => ({
      ...prev,
      ...newMetrics
    }))
  }, [])

  const clearDetections = useCallback(() => {
    setDetections([])
    setDetectionHistory([])
    setIncidents([])
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
    metrics,
    updateDetections,
    addIncident,
    updateMetrics,
    clearDetections,
    getDetectionsByType,
    getDetectionsByConfidence,
    getIncidentsByType,
    getIncidentsBySeverity
  }
}
