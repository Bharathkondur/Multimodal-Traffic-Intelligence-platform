import React, { useState, useRef, useEffect } from 'react'
import { Send, Loader, RotateCcw } from 'lucide-react'
import MultiAgentView from './MultiAgentView'
import api from '../services/api'

const SUGGESTED_QUERIES = [
  'How many vehicles detected?',
  'Any incidents detected?',
  'Generate traffic report',
  'What is the peak traffic time?',
  'Show vehicle count by type',
  'Analyze traffic flow patterns'
]

const ChatPanel = ({ sessionId, disabled = false }) => {
  const [messages, setMessages] = useState([])
  const [inputValue, setInputValue] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [showAgentView, setShowAgentView] = useState(false)
  const [agentStatuses, setAgentStatuses] = useState({})
  const messagesEndRef = useRef(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const sendMessage = async (text) => {
    if (!text.trim() || !sessionId || isLoading) return

    // Add user message
    const userMessage = {
      id: Date.now(),
      type: 'user',
      content: text,
      timestamp: new Date()
    }

    setMessages((prev) => [...prev, userMessage])
    setInputValue('')
    setIsLoading(true)
    setError(null)
    setShowAgentView(true)

    // Simulate agent processing
    setAgentStatuses({
      detection: 'processing',
      incident: 'processing',
      flow: 'processing',
      safety: 'processing',
      synthesis: 'idle'
    })

    try {
      // Try the primary endpoint first
      let response
      try {
        response = await api.sendMessage(sessionId, text)
      } catch (err1) {
        // Fallback to alternative endpoint
        response = await api.sendChatMessage(sessionId, text)
      }

      // Simulate agent completion
      await new Promise((resolve) => setTimeout(resolve, 800))
      setAgentStatuses({
        detection: 'done',
        incident: 'done',
        flow: 'done',
        safety: 'done',
        synthesis: 'processing'
      })

      await new Promise((resolve) => setTimeout(resolve, 600))
      setAgentStatuses({
        detection: 'done',
        incident: 'done',
        flow: 'done',
        safety: 'done',
        synthesis: 'done'
      })

      const aiMessage = {
        id: Date.now() + 1,
        type: 'ai',
        content: response.data.response || response.data.message || 'Analysis complete',
        timestamp: new Date()
      }
      setMessages((prev) => [...prev, aiMessage])

      // Hide agent view after completion
      setTimeout(() => setShowAgentView(false), 2000)
    } catch (err) {
      setError('Failed to send message')
      console.error('Chat error:', err)
      setShowAgentView(false)
    } finally {
      setIsLoading(false)
    }
  }

  const handleSend = () => {
    sendMessage(inputValue)
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const clearChat = () => {
    setMessages([])
    setError(null)
    setShowAgentView(false)
  }

  const renderMessage = (message) => {
    if (message.type === 'user') {
      return (
        <div key={message.id} className="message message-user">
          <div className="message-bubble message-bubble-user">
            <p className="text-sm">{message.content}</p>
          </div>
        </div>
      )
    } else {
      return (
        <div key={message.id} className="message message-ai">
          <div className="message-bubble message-bubble-ai">
            <div className="text-sm prose prose-invert max-w-none">
              {message.content}
            </div>
          </div>
        </div>
      )
    }
  }

  return (
    <div className="card h-full flex flex-col">
      <div className="card-header flex justify-between items-center">
        <div>
          <h3 className="card-title">AI Assistant</h3>
          <p className="card-subtitle">Scene Intelligence Chat</p>
        </div>
        <button
          onClick={clearChat}
          className="btn btn-secondary btn-sm"
          title="Clear chat history"
        >
          <RotateCcw className="w-4 h-4" />
        </button>
      </div>

      {/* Messages Container */}
      <div className="flex-1 overflow-y-auto mb-4 pr-2">
        {showAgentView && (
          <div className="mb-4">
            <MultiAgentView isActive={isLoading} agentStatuses={agentStatuses} />
          </div>
        )}

        {messages.length === 0 && !showAgentView && (
          <div className="text-center py-8">
            <p className="text-slate-400 text-sm mb-4">
              Start by asking a question about traffic conditions
            </p>

            {/* Suggested Queries */}
            <div className="space-y-2">
              {SUGGESTED_QUERIES.map((query, idx) => (
                <button
                  key={idx}
                  onClick={() => sendMessage(query)}
                  disabled={disabled || isLoading}
                  className="w-full text-left px-3 py-2 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {query}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => renderMessage(msg))}

        {isLoading && !showAgentView && (
          <div className="message message-ai">
            <div className="message-bubble message-bubble-ai flex items-center gap-2">
              <Loader className="w-4 h-4 animate-spin" />
              <span className="text-sm">Analyzing...</span>
            </div>
          </div>
        )}

        {error && (
          <div className="message">
            <div className="message-bubble bg-red-900 text-red-100">
              <p className="text-sm">{error}</p>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="flex gap-2">
        <input
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="Ask about traffic conditions..."
          disabled={disabled || isLoading}
          className="input flex-1"
        />
        <button
          onClick={handleSend}
          disabled={disabled || isLoading || !inputValue.trim()}
          className="btn btn-primary btn-sm"
        >
          {isLoading ? (
            <Loader className="w-4 h-4 animate-spin" />
          ) : (
            <Send className="w-4 h-4" />
          )}
        </button>
      </div>
    </div>
  )
}

export default ChatPanel
