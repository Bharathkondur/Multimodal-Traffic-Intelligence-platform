import React from 'react'
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell
} from 'recharts'
import { Activity, Radio, Zap } from 'lucide-react'

const MetricsPanel = ({ metrics = {}, history = [] }) => {
  const {
    vehicleCount = {},
    totalDetections = 0,
    avgConfidence = 0,
    activeTracks = 0,
    fps = 0,
    latency = 0
  } = metrics

  // Prepare vehicle count data
  const vehicleData = Object.entries(vehicleCount).map(([type, count]) => ({
    name: type.charAt(0).toUpperCase() + type.slice(1),
    count: count
  }))

  // Prepare history chart data
  const chartData = history.slice(-60).map((item) => ({
    timestamp: new Date(item.timestamp).toLocaleTimeString(),
    vehicles: item.detections?.length || 0
  }))

  // Prepare confidence distribution
  const confidenceData = [
    { name: '90-100%', value: 35, color: '#10b981' },
    { name: '80-90%', value: 40, color: '#3b82f6' },
    { name: '70-80%', value: 20, color: '#f59e0b' },
    { name: '<70%', value: 5, color: '#ef4444' }
  ]

  const vehicleColors = ['#3b82f6', '#ef4444', '#f59e0b', '#8b5cf6', '#10b981', '#ec4899']

  return (
    <div className="space-y-4">
      {/* KPI Cards */}
      <div className="grid grid-cols-2 gap-3">
        <div className="card">
          <div className="flex items-center justify-between">
            <div>
              <p className="card-subtitle">Total Objects</p>
              <p className="text-2xl font-bold text-blue-400">{totalDetections}</p>
            </div>
            <Activity className="w-8 h-8 text-blue-500 opacity-50" />
          </div>
        </div>

        <div className="card">
          <div className="flex items-center justify-between">
            <div>
              <p className="card-subtitle">Active Tracks</p>
              <p className="text-2xl font-bold text-green-400">{activeTracks}</p>
            </div>
            <Radio className="w-8 h-8 text-green-500 opacity-50" />
          </div>
        </div>

        <div className="card">
          <div className="flex items-center justify-between">
            <div>
              <p className="card-subtitle">Avg Confidence</p>
              <p className="text-2xl font-bold text-yellow-400">{avgConfidence}%</p>
            </div>
            <Zap className="w-8 h-8 text-yellow-500 opacity-50" />
          </div>
        </div>

        <div className="card">
          <div className="flex items-center justify-between">
            <div>
              <p className="card-subtitle">Latency</p>
              <p className="text-2xl font-bold text-purple-400">{latency}ms</p>
            </div>
            <span className="text-xs text-slate-400">FPS: {fps}</span>
          </div>
        </div>
      </div>

      {/* Vehicle Count Bar Chart */}
      <div className="card">
        <h3 className="card-title mb-4">Vehicle Count by Type</h3>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={vehicleData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="name" stroke="#64748b" />
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

      {/* Traffic Flow Chart */}
      {chartData.length > 0 && (
        <div className="card">
          <h3 className="card-title mb-4">Detection Timeline</h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis
                dataKey="timestamp"
                stroke="#64748b"
                style={{ fontSize: '12px' }}
              />
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
                dataKey="vehicles"
                stroke="#10b981"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Confidence Distribution */}
      <div className="card">
        <h3 className="card-title mb-4">Confidence Distribution</h3>
        <ResponsiveContainer width="100%" height={200}>
          <PieChart>
            <Pie
              data={confidenceData}
              cx="50%"
              cy="50%"
              innerRadius={40}
              outerRadius={80}
              paddingAngle={2}
              dataKey="value"
            >
              {confidenceData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                backgroundColor: '#1e293b',
                border: '1px solid #475569',
                borderRadius: '0.5rem'
              }}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="flex flex-wrap gap-2 mt-4 justify-center">
          {confidenceData.map((item) => (
            <div key={item.name} className="flex items-center gap-1 text-xs">
              <span
                className="w-2 h-2 rounded-full"
                style={{ backgroundColor: item.color }}
              ></span>
              <span className="text-slate-400">{item.name}</span>
            </div>
          ))}
        </div>
      </div>

      {/* System Stats */}
      <div className="card">
        <h3 className="card-title mb-3">System Status</h3>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between items-center py-2 border-b border-slate-800">
            <span className="text-slate-400">FPS</span>
            <span className={`font-mono font-bold ${fps >= 30 ? 'text-green-400' : fps >= 15 ? 'text-yellow-400' : 'text-red-400'}`}>
              {fps} fps
            </span>
          </div>
          <div className="flex justify-between items-center py-2 border-b border-slate-800">
            <span className="text-slate-400">Latency</span>
            <span className={`font-mono font-bold ${latency < 100 ? 'text-green-400' : latency < 200 ? 'text-yellow-400' : 'text-red-400'}`}>
              {latency} ms
            </span>
          </div>
          <div className="flex justify-between items-center py-2">
            <span className="text-slate-400">Avg Confidence</span>
            <span className="font-mono font-bold text-blue-400">{avgConfidence}%</span>
          </div>
        </div>
      </div>
    </div>
  )
}

export default MetricsPanel
