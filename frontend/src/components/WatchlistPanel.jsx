import React, { useEffect, useState, useCallback } from 'react'
import { Eye, Plus, Trash2, Zap, AlertTriangle, Info, Sparkles } from 'lucide-react'
import api from '../services/api'

/**
 * Watchlist rule management UI — plain-English rule CRUD over
 * `/api/scene/sessions/{id}/rules`. Users type a rule like
 * "alert if more than 3 people in entrance" and the backend compiles
 * it into a predicate that fires WebSocket alerts when matched.
 *
 * Shows the compiled predicate for trust/debugging; offers a
 * one-click button to seed the four canonical demo rules.
 */

const SEVERITY_META = {
  info: { color: 'text-slate-300 bg-slate-800 border-slate-700', Icon: Info },
  warning: { color: 'text-amber-300 bg-amber-950/50 border-amber-800', Icon: AlertTriangle },
  critical: { color: 'text-red-300 bg-red-950/50 border-red-800', Icon: Zap },
}

const PREDICATE_LABEL = {
  count: 'Count threshold',
  action: 'Action detection',
  appear: 'Object appearance',
  absence: 'Absence / empty scene',
}

const WatchlistPanel = ({ sessionId, disabled = false }) => {
  const [rules, setRules] = useState([])
  const [text, setText] = useState('')
  const [severity, setSeverity] = useState('warning')
  const [name, setName] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [isSeeding, setIsSeeding] = useState(false)
  const [error, setError] = useState(null)

  const loadRules = useCallback(async () => {
    if (!sessionId) return
    try {
      const { data } = await api.listRules(sessionId)
      setRules(Array.isArray(data) ? data : [])
    } catch (e) {
      console.error('listRules failed', e)
    }
  }, [sessionId])

  useEffect(() => {
    loadRules()
  }, [loadRules])

  const addRule = async () => {
    if (!text.trim() || !sessionId) return
    setIsSaving(true)
    setError(null)
    try {
      const { data } = await api.createRule(sessionId, {
        text: text.trim(),
        name: name.trim() || null,
        severity,
        cooldown_s: 15.0,
      })
      setRules((prev) => [...prev, data])
      setText('')
      setName('')
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to create rule')
    } finally {
      setIsSaving(false)
    }
  }

  const removeRule = async (ruleId) => {
    try {
      await api.deleteRule(sessionId, ruleId)
      setRules((prev) => prev.filter((r) => r.id !== ruleId))
    } catch (e) {
      console.error('deleteRule failed', e)
    }
  }

  const seed = async () => {
    setIsSeeding(true)
    setError(null)
    try {
      const { data } = await api.seedDemoRules(sessionId)
      setRules((prev) => {
        const seen = new Set(prev.map((r) => r.id))
        return [...prev, ...data.filter((r) => !seen.has(r.id))]
      })
    } catch (e) {
      setError('Failed to seed demo rules')
    } finally {
      setIsSeeding(false)
    }
  }

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      addRule()
    }
  }

  return (
    <div className="h-full flex flex-col bg-slate-950/70 rounded-lg border border-slate-800">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-800">
        <Eye className="w-4 h-4 text-cyan-400" />
        <h3 className="text-sm font-semibold text-slate-200 tracking-wide uppercase">
          Watchlist
        </h3>
        <span className="ml-auto text-xs text-slate-500 font-mono">
          {rules.length} rule{rules.length === 1 ? '' : 's'}
        </span>
      </div>

      {/* Composer */}
      <div className="px-4 py-3 border-b border-slate-800 space-y-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder='e.g. "alert if more than 3 people in entrance" or "person falling"'
          disabled={disabled}
          rows={2}
          className="w-full text-sm bg-slate-900 border border-slate-700 rounded px-3 py-2 text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-cyan-600 resize-none"
        />
        <div className="flex items-center gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Name (optional)"
            disabled={disabled}
            className="flex-1 text-xs bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-cyan-600"
          />
          <select
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
            disabled={disabled}
            className="text-xs bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-slate-200 focus:outline-none focus:border-cyan-600"
          >
            <option value="info">info</option>
            <option value="warning">warning</option>
            <option value="critical">critical</option>
          </select>
          <button
            onClick={addRule}
            disabled={disabled || isSaving || !text.trim()}
            className="flex items-center gap-1 text-xs font-medium bg-cyan-700 hover:bg-cyan-600 disabled:bg-slate-800 disabled:text-slate-500 text-white rounded px-3 py-1.5 transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            {isSaving ? 'Adding…' : 'Add'}
          </button>
        </div>
        {rules.length === 0 && (
          <button
            onClick={seed}
            disabled={disabled || isSeeding}
            className="w-full flex items-center justify-center gap-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-cyan-300 rounded px-3 py-1.5 transition-colors border border-slate-700"
          >
            <Sparkles className="w-3.5 h-3.5" />
            {isSeeding ? 'Seeding…' : 'Seed 4 demo rules'}
          </button>
        )}
        {error && (
          <p className="text-xs text-red-400">{error}</p>
        )}
      </div>

      {/* Rule list */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2 text-sm">
        {rules.length === 0 ? (
          <p className="text-slate-500 italic text-xs">
            No rules yet. Write one above or seed the demo set.
          </p>
        ) : (
          rules.map((r) => {
            const meta = SEVERITY_META[r.severity] || SEVERITY_META.info
            const { Icon } = meta
            const kind = r.predicate?.kind
            return (
              <div
                key={r.id}
                className={`group rounded border ${meta.color} px-3 py-2 flex items-start gap-2`}
              >
                <Icon className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium truncate">{r.name}</span>
                    {!r.enabled && (
                      <span className="text-[10px] font-mono uppercase text-slate-500">
                        paused
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-slate-400 italic truncate">
                    “{r.raw_text}”
                  </div>
                  {kind && (
                    <div className="mt-1 text-[10px] font-mono text-slate-500">
                      {PREDICATE_LABEL[kind] || kind}
                      {r.predicate?.class && ` · ${r.predicate.class}`}
                      {typeof r.predicate?.threshold === 'number' &&
                        ` · ≥${r.predicate.threshold}`}
                      {r.predicate?.action && ` · ${r.predicate.action}`}
                      {r.predicate?.zone && ` · zone:${r.predicate.zone}`}
                    </div>
                  )}
                </div>
                <button
                  onClick={() => removeRule(r.id)}
                  className="opacity-0 group-hover:opacity-100 transition-opacity text-slate-500 hover:text-red-400"
                  title="Remove rule"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

export default WatchlistPanel
