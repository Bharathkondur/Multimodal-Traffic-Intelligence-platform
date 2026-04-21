import React, { useEffect, useState, useCallback } from 'react'
import { Siren, Info, AlertTriangle, Zap, Image as ImageIcon, X } from 'lucide-react'
import api from '../services/api'

/**
 * Merged view of live WebSocket alerts and historical alerts fetched from
 * `/api/scene/sessions/{id}/alerts`.
 *
 * Dedupes by alert id. Clicking an entry with a snapshot opens the
 * JPEG lightbox; backend returns the blob as a base64 data URL.
 */

const SEVERITY_META = {
  info: {
    ring: 'border-slate-700',
    bg: 'bg-slate-900',
    text: 'text-slate-300',
    accent: 'text-slate-400',
    Icon: Info,
  },
  warning: {
    ring: 'border-amber-800',
    bg: 'bg-amber-950/40',
    text: 'text-amber-200',
    accent: 'text-amber-400',
    Icon: AlertTriangle,
  },
  critical: {
    ring: 'border-red-800',
    bg: 'bg-red-950/40',
    text: 'text-red-200',
    accent: 'text-red-400',
    Icon: Zap,
  },
}

const AlertHistoryPanel = ({ sessionId, liveAlerts = [] }) => {
  const [history, setHistory] = useState([])
  const [severityFilter, setSeverityFilter] = useState('all')
  const [snapshot, setSnapshot] = useState(null) // {alertId, dataUrl, timestamp}
  const [loadingSnap, setLoadingSnap] = useState(false)

  const loadHistory = useCallback(async () => {
    if (!sessionId) return
    try {
      const params = severityFilter === 'all' ? {} : { severity: severityFilter }
      const { data } = await api.listAlerts(sessionId, params)
      setHistory(Array.isArray(data) ? data : [])
    } catch (e) {
      console.error('listAlerts failed', e)
    }
  }, [sessionId, severityFilter])

  useEffect(() => {
    loadHistory()
  }, [loadHistory])

  // Dedupe live + history, newest first.
  const merged = React.useMemo(() => {
    const byId = new Map()
    const norm = (a) => ({
      id: a.id || a.alert_id,
      rule_name: a.rule_name || 'Rule',
      severity: a.severity || 'info',
      reason: a.reason,
      zone_id: a.zone_id,
      frame_id: a.frame_id,
      timestamp: a.timestamp,
      has_snapshot: a.has_snapshot ?? Boolean(a.snapshot_b64),
      matched_objects: a.matched_objects,
    })
    for (const a of history) byId.set(norm(a).id, norm(a))
    for (const a of liveAlerts) {
      const n = norm(a)
      if (n.id) byId.set(n.id, { ...byId.get(n.id), ...n })
    }
    return Array.from(byId.values()).sort((a, b) => {
      const ta = a.timestamp ? new Date(a.timestamp).getTime() : 0
      const tb = b.timestamp ? new Date(b.timestamp).getTime() : 0
      return tb - ta
    })
  }, [history, liveAlerts])

  const openSnapshot = async (alertId) => {
    if (!alertId) return
    setLoadingSnap(true)
    try {
      const { data } = await api.getAlertSnapshot(sessionId, alertId)
      setSnapshot({
        alertId: data.alert_id,
        dataUrl: data.data_url,
        timestamp: data.timestamp,
      })
    } catch (e) {
      console.error('getAlertSnapshot failed', e)
    } finally {
      setLoadingSnap(false)
    }
  }

  const counts = React.useMemo(() => {
    const c = { info: 0, warning: 0, critical: 0 }
    for (const a of merged) if (c[a.severity] !== undefined) c[a.severity] += 1
    return c
  }, [merged])

  return (
    <div className="h-full flex flex-col bg-slate-950/70 rounded-lg border border-slate-800">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-800">
        <Siren className="w-4 h-4 text-red-400" />
        <h3 className="text-sm font-semibold text-slate-200 tracking-wide uppercase">
          Alert History
        </h3>
        <div className="ml-auto flex items-center gap-2 text-xs font-mono">
          <span className="text-slate-500">{merged.length}</span>
          {counts.critical > 0 && (
            <span className="text-red-400">{counts.critical} crit</span>
          )}
          {counts.warning > 0 && (
            <span className="text-amber-400">{counts.warning} warn</span>
          )}
        </div>
      </div>

      {/* Filter row */}
      <div className="flex items-center gap-1 px-4 py-2 border-b border-slate-800 text-xs">
        {['all', 'critical', 'warning', 'info'].map((s) => (
          <button
            key={s}
            onClick={() => setSeverityFilter(s)}
            className={`px-2 py-0.5 rounded capitalize font-mono tracking-wide transition-colors ${
              severityFilter === s
                ? 'bg-slate-700 text-slate-100'
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      {/* Alert list */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2 text-sm">
        {merged.length === 0 ? (
          <p className="text-slate-500 italic text-xs">
            No alerts yet. Rules will fire once scene conditions match.
          </p>
        ) : (
          merged.map((a) => {
            const meta = SEVERITY_META[a.severity] || SEVERITY_META.info
            const { Icon } = meta
            return (
              <button
                key={a.id || Math.random()}
                onClick={() => a.has_snapshot && openSnapshot(a.id)}
                disabled={!a.has_snapshot}
                className={`w-full text-left border ${meta.ring} ${meta.bg} ${meta.text} rounded px-3 py-2 flex items-start gap-2 transition-colors ${
                  a.has_snapshot ? 'hover:bg-slate-800/50 cursor-pointer' : ''
                }`}
              >
                <Icon className={`w-4 h-4 mt-0.5 flex-shrink-0 ${meta.accent}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium truncate">{a.rule_name}</span>
                    {a.zone_id && (
                      <span className="text-[10px] font-mono text-slate-500">
                        · {a.zone_id}
                      </span>
                    )}
                  </div>
                  {a.reason && (
                    <div className="text-xs text-slate-400 truncate">{a.reason}</div>
                  )}
                  <div className="flex items-center gap-2 text-[10px] font-mono text-slate-500 mt-0.5">
                    {a.timestamp && (
                      <span>{new Date(a.timestamp).toLocaleTimeString()}</span>
                    )}
                    {typeof a.frame_id === 'number' && (
                      <span>frame #{a.frame_id}</span>
                    )}
                    {a.has_snapshot && (
                      <span className="flex items-center gap-0.5 text-cyan-400">
                        <ImageIcon className="w-3 h-3" /> snapshot
                      </span>
                    )}
                  </div>
                </div>
              </button>
            )
          })
        )}
      </div>

      {/* Snapshot lightbox */}
      {snapshot && (
        <div
          className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
          onClick={() => setSnapshot(null)}
        >
          <div
            className="relative max-w-4xl w-full bg-slate-900 rounded-lg border border-slate-700 overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => setSnapshot(null)}
              className="absolute top-2 right-2 text-slate-300 hover:text-white bg-black/50 rounded-full p-1"
            >
              <X className="w-4 h-4" />
            </button>
            <img
              src={snapshot.dataUrl}
              alt="alert snapshot"
              className="w-full h-auto"
            />
            <div className="px-4 py-2 text-xs font-mono text-slate-400 border-t border-slate-800">
              {snapshot.alertId} ·{' '}
              {snapshot.timestamp
                ? new Date(snapshot.timestamp).toLocaleString()
                : ''}
            </div>
          </div>
        </div>
      )}
      {loadingSnap && (
        <div className="absolute bottom-3 right-3 text-xs text-cyan-400 font-mono">
          Loading snapshot…
        </div>
      )}
    </div>
  )
}

export default AlertHistoryPanel
