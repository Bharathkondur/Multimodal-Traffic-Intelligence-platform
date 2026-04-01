import React, { useState, useEffect } from 'react'
import { Zap, CheckCircle, Clock, AlertCircle } from 'lucide-react'

const AGENTS = [
  {
    id: 'detection',
    name: 'Detection Analyst',
    description: 'Analyzes vehicle detections and classifications',
    icon: 'eye'
  },
  {
    id: 'incident',
    name: 'Incident Responder',
    description: 'Identifies and prioritizes traffic incidents',
    icon: 'alert'
  },
  {
    id: 'flow',
    name: 'Flow Optimizer',
    description: 'Analyzes traffic flow and patterns',
    icon: 'flow'
  },
  {
    id: 'safety',
    name: 'Safety Monitor',
    description: 'Detects safety violations and hazards',
    icon: 'shield'
  },
  {
    id: 'synthesis',
    name: 'Response Synthesizer',
    description: 'Combines all analyses into final response',
    icon: 'merge'
  }
]

const AgentCard = ({ agent, status, isActive }) => {
  const statusConfig = {
    thinking: { color: 'bg-yellow-900', textColor: 'text-yellow-400', icon: Clock },
    processing: { color: 'bg-blue-900', textColor: 'text-blue-400', icon: Zap },
    done: { color: 'bg-green-900', textColor: 'text-green-400', icon: CheckCircle },
    error: { color: 'bg-red-900', textColor: 'text-red-400', icon: AlertCircle },
    idle: { color: 'bg-slate-800', textColor: 'text-slate-400', icon: null }
  }

  const config = statusConfig[status] || statusConfig.idle
  const StatusIcon = config.icon

  return (
    <div
      className={`p-3 rounded-lg border transition-all duration-300 ${
        config.color
      } ${isActive ? 'border-2' : 'border'} ${
        isActive ? config.textColor : 'border-slate-700'
      }`}
    >
      <div className="flex items-start gap-2">
        {StatusIcon && (
          <StatusIcon
            className={`w-4 h-4 flex-shrink-0 mt-0.5 ${
              status === 'thinking' || status === 'processing' ? 'animate-spin' : ''
            }`}
          />
        )}
        <div className="flex-1 min-w-0">
          <h4 className="font-semibold text-sm">{agent.name}</h4>
          <p className="text-xs opacity-75 truncate">{agent.description}</p>
        </div>
      </div>

      {/* Status Indicator */}
      <div className="mt-2 pt-2 border-t border-current border-opacity-30">
        <p className="text-xs font-mono opacity-75 capitalize">{status}</p>
      </div>
    </div>
  )
}

const MultiAgentView = ({ isActive = false, agentStatuses = {} }) => {
  const [agentStates, setAgentStates] = useState({
    detection: 'idle',
    incident: 'idle',
    flow: 'idle',
    safety: 'idle',
    synthesis: 'idle'
  })

  // Update agent states from props
  useEffect(() => {
    setAgentStates(agentStatuses)
  }, [agentStatuses])

  // Simulate agent processing flow when active
  useEffect(() => {
    if (!isActive) return

    const flow = async () => {
      // Start coordinators and initial agents
      setAgentStates({
        detection: 'processing',
        incident: 'processing',
        flow: 'processing',
        safety: 'processing',
        synthesis: 'idle'
      })

      // Wait for agents to process
      await new Promise((resolve) => setTimeout(resolve, 2000))

      // Mark agents as done and start synthesis
      setAgentStates({
        detection: 'done',
        incident: 'done',
        flow: 'done',
        safety: 'done',
        synthesis: 'processing'
      })

      // Final synthesis
      await new Promise((resolve) => setTimeout(resolve, 1500))

      setAgentStates({
        detection: 'done',
        incident: 'done',
        flow: 'done',
        safety: 'done',
        synthesis: 'done'
      })

      // Reset after completion
      await new Promise((resolve) => setTimeout(resolve, 2000))
      setAgentStates({
        detection: 'idle',
        incident: 'idle',
        flow: 'idle',
        safety: 'idle',
        synthesis: 'idle'
      })
    }

    flow()
  }, [isActive])

  return (
    <div className="card">
      <div className="card-header">
        <h3 className="card-title">Multi-Agent Processing</h3>
        <span className={`ml-auto text-xs font-mono px-2 py-1 rounded ${isActive ? 'bg-green-900 text-green-300' : 'bg-slate-800 text-slate-400'}`}>
          {isActive ? 'Processing' : 'Idle'}
        </span>
      </div>

      {/* Agent Flow Visualization */}
      <div className="space-y-4">
        {/* Coordinator Info */}
        <div className="p-3 bg-blue-900 border border-blue-700 rounded-lg">
          <p className="text-sm font-semibold text-blue-300">Query Coordinator</p>
          <p className="text-xs text-blue-200 mt-1">Routes queries to specialized agents for parallel processing</p>
        </div>

        {/* Specialist Agents Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {AGENTS.slice(0, 4).map((agent) => (
            <AgentCard
              key={agent.id}
              agent={agent}
              status={agentStates[agent.id] || 'idle'}
              isActive={agentStates[agent.id] !== 'idle'}
            />
          ))}
        </div>

        {/* Flow Arrows */}
        {Object.values(agentStates).some((s) => s !== 'idle') && (
          <div className="flex items-center justify-center py-2">
            <div className="text-slate-500 text-xs font-mono">↓ Synthesizing Results ↓</div>
          </div>
        )}

        {/* Synthesizer Agent */}
        <AgentCard
          agent={AGENTS[4]}
          status={agentStates.synthesis || 'idle'}
          isActive={agentStates.synthesis !== 'idle'}
        />

        {/* Info Box */}
        <div className="p-3 bg-slate-800 rounded-lg border border-slate-700">
          <p className="text-xs text-slate-400">
            <span className="font-semibold text-slate-300">How it works:</span> When you ask a question, the system routes
            it to multiple specialist agents that work in parallel. Each agent analyzes different aspects
            (detections, incidents, flow, safety), then the synthesizer combines their insights into a comprehensive response.
          </p>
        </div>

        {/* Action Button */}
        {!isActive && (
          <button
            className="w-full btn btn-primary text-sm"
            onClick={() => {
              // This would be triggered when a user sends a message
              // For now, it's just informational
            }}
          >
            Send a message to see agents in action
          </button>
        )}
      </div>
    </div>
  )
}

export default MultiAgentView
