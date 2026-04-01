import React, { useState, useEffect } from 'react'
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { AlertTriangle, Gauge } from 'lucide-react'
import api from '../services/api'

const SpeedGauge = ({ speed, maxSpeed = 80 }) => {
  const percentage = Math.min((speed / maxSpeed) * 100, 100)
  const radius = 80
  const circumference = 2 * Math.PI * radius

  // Determine color based on speed
  let color = '#10b981' // green for normal
  if (speed > maxSpeed * 0.8) {
    color = '#ef4444' // red for speeding
  } else if (speed > maxSpeed * 0.6) {
    color = '#f59e0b' // amber for moderate
  }

  const offset = circumference - (percentage / 100) * circumference

  return (
    <div className="flex flex-col items-center justify-center py-6">
      <svg width="200" height="200" className="transform -rotate-90">
        {/* Background circle */}
        <circle
          cx="100"
          cy="100"
          r={radius}
          fill="none"
          stroke="#334155"
          strokeWidth="8"
        />
        {/* Progress circle */}
        <circle
          cx="100"
          cy="100"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 0.3s ease' }}
        />
      </svg>
      <div className="absolute text-center">
        <div className="text-3xl font-bold text-slate-100">{speed.toFixed(1)}</div>
        <div className="text-xs text-slate-400">km/h</div>
      </div>
    </div>
  )
}

const SpeedPanel = ({ sessionId, onError = null }) => {
  const [speedData, setSpeedData] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!sessionId) return

    const fetchSpeedData = async () => {
      setIsLoading(true)
      setError(null)

      try {
        const response = await api.getSpeeds(sessionId)
        if (response.data) {
          setSpeedData(response.data)
        }
      } catch (err) {
        const errorMsg = 'Failed to load speed data'
        setError(errorMsg)
        if (onError) onError(errorMsg)
        console.error('Speed data error:', err)
      } finally {
        setIsLoading(false)
      }
    }

    fetchSpeedData()

    // Refresh every 10 seconds
    const interval = setInterval(fetchSpeedData, 10000)
    return () => clearInterval(interval)
  }, [sessionId, onError])

  if (!speedData && !isLoading) {
    return (
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Speed Analytics</h3>
        </div>
        <div className="p-4 text-center">
          <p className="text-slate-400 text-sm">No speed data available</p>
        </div>
      </div>
    )
  }

  const {
    average_speed = 0,
    max_speed = 0,
    min_speed = 0,
    speed_limit = 50,
    violations = [],
    distribution = [],
    history = []
  } = speedData || {}

  // Prepare distribution data for chart
  const distributionData = distribution.map((item) => ({
    range: item.range,
    count: item.count
  }))

  // Prepare history data
  const historyData = history.map((item) => ({
    time: new Date(item.timestamp).toLocaleTimeString(),
    speed: item.average_speed
  }))

  return (
    <div className="space-y-4">
      {/* Error */}
      {error && (
        <div className="card bg-red-900 border border-red-700">
          <p className="text-sm text-red-200">{error}</p>
        </div>
      )}

      {/* Speed Gauge */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Current Average Speed</h3>
        </div>
        <div className="flex justify-center relative py-4">
          <SpeedGauge speed={average_speed} maxSpeed={speed_limit * 1.5} />
        </div>
      </div>

      {/* Speed Stats */}
      <div className="grid grid-cols-3 gap-3">
        <div className="card">
          <p className="card-subtitle text-xs">Average</p>
          <p className="text-xl font-bold text-blue-400">{average_speed.toFixed(1)}</p>
          <p className="text-xs text-slate-500">km/h</p>
        </div>
        <div className="card">
          <p className="card-subtitle text-xs">Maximum</p>
          <p className="text-xl font-bold text-red-400">{max_speed.toFixed(1)}</p>
          <p className="text-xs text-slate-500">km/h</p>
        </div>
        <div className="card">
          <p className="card-subtitle text-xs">Speed Limit</p>
          <p className="text-xl font-bold text-green-400">{speed_limit}</p>
          <p className="text-xs text-slate-500">km/h</p>
        </div>
      </div>

      {/* Distribution Chart */}
      {distributionData.length > 0 && (
        <div className="card">
          <h3 className="card-title mb-4">Speed Distribution</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={distributionData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="range" stroke="#64748b" fontSize={12} />
              <YAxis stroke="#64748b" />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #475569',
                  borderRadius: '0.5rem'
                }}
              />
              <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Speed Trend Chart */}
      {historyData.length > 0 && (
        <div className="card">
          <h3 className="card-title mb-4">Speed Trend</h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={historyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="time" stroke="#64748b" fontSize={12} />
              <YAxis stroke="#64748b" />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #475569',
                  borderRadius: '0.5rem'
                }}
              />
              <Line
                type="monotone"
                dataKey="speed"
                stroke="#10b981"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Speeding Violations */}
      {violations && violations.length > 0 && (
        <div className="card">
          <div className="card-header flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-red-400" />
            <h3 className="card-title">Speeding Violations</h3>
            <span className="ml-auto text-sm font-mono text-red-400">{violations.length}</span>
          </div>
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {violations.slice(0, 10).map((violation, idx) => (
              <div key={idx} className="p-2 bg-red-900 bg-opacity-30 rounded border border-red-700">
                <div className="flex justify-between items-start text-xs">
                  <div>
                    <p className="font-semibold text-red-300">Track ID: {violation.track_id}</p>
                    <p className="text-red-200">{violation.speed.toFixed(1)} km/h (limit: {speed_limit})</p>
                  </div>
                  <span className="text-red-400 font-mono">{violation.excess.toFixed(1)} km/h over</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default SpeedPanel
