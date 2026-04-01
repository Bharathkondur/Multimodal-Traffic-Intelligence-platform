import React, { useState } from 'react'
import { AlertTriangle, AlertCircle, AlertOctagon, Info, Trash2 } from 'lucide-react'

const SEVERITY_CONFIG = {
  critical: { color: 'text-red-400', bg: 'bg-red-900', icon: AlertOctagon, label: 'Critical' },
  high: { color: 'text-orange-400', bg: 'bg-orange-900', icon: AlertTriangle, label: 'High' },
  medium: { color: 'text-yellow-400', bg: 'bg-yellow-900', icon: AlertCircle, label: 'Medium' },
  low: { color: 'text-green-400', bg: 'bg-green-900', icon: Info, label: 'Low' }
}

const IncidentLog = ({ incidents = [], onIncidentClick = null }) => {
  const [filter, setFilter] = useState('all')
  const [expandedId, setExpandedId] = useState(null)

  const filteredIncidents = filter === 'all'
    ? incidents
    : incidents.filter((i) => i.severity === filter)

  const getSeverityConfig = (severity) => {
    return SEVERITY_CONFIG[severity] || SEVERITY_CONFIG.low
  }

  const handleClear = () => {
    if (window.confirm('Clear all incidents?')) {
      // Implement clear logic in parent
    }
  }

  return (
    <div className="card h-full flex flex-col">
      <div className="card-header flex justify-between items-center">
        <div>
          <h3 className="card-title">Incident Log</h3>
          <p className="card-subtitle">{filteredIncidents.length} incidents</p>
        </div>
        {incidents.length > 0 && (
          <button
            onClick={handleClear}
            className="btn btn-danger btn-sm"
            title="Clear all incidents"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Filter Buttons */}
      <div className="flex gap-2 mb-4 overflow-x-auto pb-2">
        {['all', 'critical', 'high', 'medium', 'low'].map((severity) => (
          <button
            key={severity}
            onClick={() => setFilter(severity)}
            className={`btn btn-sm whitespace-nowrap transition-colors ${
              filter === severity
                ? 'btn-primary'
                : 'btn-secondary'
            }`}
          >
            {severity.charAt(0).toUpperCase() + severity.slice(1)}
          </button>
        ))}
      </div>

      {/* Incidents List */}
      <div className="flex-1 overflow-y-auto space-y-2">
        {filteredIncidents.length === 0 ? (
          <div className="text-center py-8">
            <Info className="w-8 h-8 text-slate-600 mx-auto mb-2" />
            <p className="text-slate-400 text-sm">No incidents detected</p>
          </div>
        ) : (
          filteredIncidents.map((incident, idx) => {
            const config = getSeverityConfig(incident.severity)
            const Icon = config.icon
            const isExpanded = expandedId === incident.id

            return (
              <div
                key={incident.id || idx}
                className={`border rounded-lg overflow-hidden transition-all cursor-pointer ${
                  config.bg
                } border-opacity-50`}
                onClick={() => {
                  setExpandedId(isExpanded ? null : incident.id)
                  if (onIncidentClick) {
                    onIncidentClick(incident)
                  }
                }}
              >
                <div className="p-3">
                  <div className="flex items-start gap-3">
                    <Icon className={`w-5 h-5 flex-shrink-0 mt-0.5 ${config.color}`} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-baseline justify-between gap-2">
                        <h4 className={`font-semibold text-sm ${config.color}`}>
                          {incident.type}
                        </h4>
                        <span className="text-xs text-slate-500 flex-shrink-0">
                          {new Date(incident.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 mt-1 line-clamp-2">
                        {incident.description}
                      </p>
                      {incident.location && (
                        <p className="text-xs text-slate-500 mt-1">
                          Location: {incident.location}
                        </p>
                      )}
                    </div>
                    {incident.confidence && (
                      <span className="text-xs font-mono text-slate-400 flex-shrink-0">
                        {(incident.confidence * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>

                  {/* Expanded Details */}
                  {isExpanded && (
                    <div className="mt-3 pt-3 border-t border-opacity-30 text-xs text-slate-400 space-y-1">
                      {incident.vehicle_type && (
                        <div>
                          <span className="text-slate-500">Vehicle Type:</span> {incident.vehicle_type}
                        </div>
                      )}
                      {incident.track_id && (
                        <div>
                          <span className="text-slate-500">Track ID:</span> {incident.track_id}
                        </div>
                      )}
                      {incident.zone_id && (
                        <div>
                          <span className="text-slate-500">Zone ID:</span> {incident.zone_id}
                        </div>
                      )}
                      {incident.details && (
                        <div className="mt-2">
                          <span className="text-slate-500">Details:</span>
                          <p className="text-slate-400 mt-1">{incident.details}</p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )
          })
        )}
      </div>

      {/* Summary Stats */}
      {incidents.length > 0 && (
        <div className="border-t border-slate-800 pt-3 mt-3">
          <div className="grid grid-cols-2 gap-2 text-xs text-slate-400">
            <div>
              <span className="text-red-400">Critical:</span> {incidents.filter(i => i.severity === 'critical').length}
            </div>
            <div>
              <span className="text-orange-400">High:</span> {incidents.filter(i => i.severity === 'high').length}
            </div>
            <div>
              <span className="text-yellow-400">Medium:</span> {incidents.filter(i => i.severity === 'medium').length}
            </div>
            <div>
              <span className="text-green-400">Low:</span> {incidents.filter(i => i.severity === 'low').length}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default IncidentLog
