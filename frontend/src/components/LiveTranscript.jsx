import React, { useEffect, useRef } from 'react'
import { Radio } from 'lucide-react'

/**
 * Scrolling feed of live VLM scene captions.
 *
 * The backend emits a `caption` message every `caption_interval_s` (default
 * 3 s). We keep the last N captions in a ring and auto-scroll so the most
 * recent one is visible. Each entry shows a timestamp, the short summary,
 * and any tags that came back from the model.
 */
const LiveTranscript = ({ captions = [] }) => {
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [captions])

  return (
    <div className="h-full flex flex-col bg-slate-950/70 rounded-lg border border-slate-800">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-800">
        <Radio className="w-4 h-4 text-cyan-400 animate-pulse" />
        <h3 className="text-sm font-semibold text-slate-200 tracking-wide uppercase">
          Live Transcript
        </h3>
        <span className="ml-auto text-xs text-slate-500 font-mono">
          {captions.length} entries
        </span>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 text-sm">
        {captions.length === 0 ? (
          <p className="text-slate-500 italic text-xs">
            Waiting for scene captions…
          </p>
        ) : (
          captions.map((c, i) => (
            <div
              key={c.frame_id || i}
              className="group border-l-2 border-cyan-700 pl-3 py-1"
            >
              <div className="text-slate-300 leading-relaxed">
                {c.summary || c.caption}
              </div>
              {c.caption && c.summary && c.caption !== c.summary && (
                <div className="text-slate-500 text-xs mt-1">{c.caption}</div>
              )}
              <div className="flex flex-wrap gap-1 mt-1">
                {(c.tags || []).map((t) => (
                  <span
                    key={t}
                    className="text-[10px] font-mono text-cyan-300 bg-cyan-950/50 border border-cyan-800 rounded px-1.5 py-0.5"
                  >
                    {t}
                  </span>
                ))}
                <span className="ml-auto text-[10px] text-slate-600 font-mono">
                  {c.timestamp
                    ? new Date(c.timestamp).toLocaleTimeString()
                    : ''}
                </span>
              </div>
            </div>
          ))
        )}
        <div ref={endRef} />
      </div>
    </div>
  )
}

export default LiveTranscript
