import React, { useState } from 'react'
import { Play, Square, AlertCircle, Settings } from 'lucide-react'
import api from '../services/api'

const DemoControls = ({ onSessionCreated = null }) => {
  const [demoRunning, setDemoRunning] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [demoSettings, setDemoSettings] = useState({
    speed: 1,
    vehicleDensity: 'medium',
    duration: 60
  })

  const startDemo = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await api.startDemo()
      setDemoRunning(true)

      if (response.data.session_id && onSessionCreated) {
        onSessionCreated(response.data.session_id)
      }
    } catch (err) {
      setError('Failed to start demo mode')
      console.error('Demo start error:', err)
    } finally {
      setIsLoading(false)
    }
  }

  const stopDemo = async () => {
    setIsLoading(true)
    setError(null)

    try {
      await api.stopDemo()
      setDemoRunning(false)
    } catch (err) {
      setError('Failed to stop demo mode')
      console.error('Demo stop error:', err)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="text-center mb-8">
        <h2 className="text-3xl font-bold text-slate-100 mb-2">Scene Intelligence Demo</h2>
        <p className="text-slate-400 text-lg">
          Simulate real-time traffic analysis without a video feed
        </p>
      </div>

      {/* Demo Explanation */}
      <div className="bg-blue-900 border border-blue-700 rounded-lg p-4 mb-6">
        <div className="flex gap-3">
          <AlertCircle className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-blue-200">
            <p className="font-semibold mb-1">Demo Mode</p>
            <p>
              Demo mode generates simulated traffic data so you can explore all dashboard features
              without a real video feed. Perfect for testing and demonstrations.
            </p>
          </div>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="bg-red-900 border border-red-700 rounded-lg p-4">
          <div className="flex gap-3">
            <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-red-200">
              <p className="font-semibold">{error}</p>
            </div>
          </div>
        </div>
      )}

      {/* Demo Controls Card */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Demo Configuration</h3>
        </div>

        <div className="space-y-4">
          {/* Status */}
          <div className="flex items-center gap-3 p-4 bg-slate-800 rounded-lg">
            <div className={`w-3 h-3 rounded-full ${demoRunning ? 'bg-green-500 animate-pulse' : 'bg-slate-600'}`}></div>
            <span className="text-slate-300 font-medium">
              Status: {demoRunning ? 'Running' : 'Stopped'}
            </span>
          </div>

          {/* Settings */}
          <div className="space-y-4">
            {/* Simulation Speed */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                Simulation Speed
              </label>
              <div className="flex gap-2 items-center">
                <input
                  type="range"
                  min="0.5"
                  max="2"
                  step="0.5"
                  value={demoSettings.speed}
                  onChange={(e) => setDemoSettings({ ...demoSettings, speed: parseFloat(e.target.value) })}
                  disabled={demoRunning || isLoading}
                  className="flex-1"
                />
                <span className="text-slate-400 text-sm font-mono">{demoSettings.speed.toFixed(1)}x</span>
              </div>
            </div>

            {/* Vehicle Density */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                Vehicle Density
              </label>
              <select
                value={demoSettings.vehicleDensity}
                onChange={(e) => setDemoSettings({ ...demoSettings, vehicleDensity: e.target.value })}
                disabled={demoRunning || isLoading}
                className="input w-full"
              >
                <option value="low">Low (5-10 vehicles)</option>
                <option value="medium">Medium (10-20 vehicles)</option>
                <option value="high">High (20-40 vehicles)</option>
                <option value="rush">Rush Hour (40+ vehicles)</option>
              </select>
            </div>

            {/* Duration */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                Duration (minutes)
              </label>
              <input
                type="number"
                min="1"
                max="120"
                value={demoSettings.duration}
                onChange={(e) => setDemoSettings({ ...demoSettings, duration: parseInt(e.target.value) })}
                disabled={demoRunning || isLoading}
                className="input w-full"
              />
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex gap-3 pt-4">
            {!demoRunning ? (
              <button
                onClick={startDemo}
                disabled={isLoading}
                className="btn btn-primary flex-1 flex items-center justify-center gap-2"
              >
                <Play className="w-4 h-4" />
                Start Demo
              </button>
            ) : (
              <button
                onClick={stopDemo}
                disabled={isLoading}
                className="btn btn-danger flex-1 flex items-center justify-center gap-2"
              >
                <Square className="w-4 h-4" />
                Stop Demo
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Features Highlight */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          {
            title: 'Live Detection',
            description: 'Simulated vehicle detection with bounding boxes and tracking'
          },
          {
            title: 'Incident Detection',
            description: 'Realistic traffic incidents and alerts generated during demo'
          },
          {
            title: 'Analytics',
            description: 'Real-time metrics, heatmaps, and performance statistics'
          }
        ].map((feature, idx) => (
          <div key={idx} className="card">
            <h4 className="font-semibold text-slate-200 mb-2">{feature.title}</h4>
            <p className="text-sm text-slate-400">{feature.description}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

export default DemoControls
