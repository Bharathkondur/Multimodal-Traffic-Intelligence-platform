import React, { useState, useEffect } from 'react'
import { BrowserRouter as Router, Routes, Route, useSearchParams, useNavigate } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Dashboard from './components/Dashboard'
import ReportView from './components/ReportView'
import UploadPanel from './components/UploadPanel'
import api from './services/api'

const AppContent = () => {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [isDarkMode, setIsDarkMode] = useState(true)
  const [currentRoute, setCurrentRoute] = useState('dashboard')
  const [sessionId, setSessionId] = useState(null)

  const sessionParam = searchParams.get('session')

  useEffect(() => {
    // Get session from URL or localStorage
    if (sessionParam) {
      setSessionId(sessionParam)
      localStorage.setItem('lastSessionId', sessionParam)
    } else {
      const lastSessionId = localStorage.getItem('lastSessionId')
      if (lastSessionId) {
        setSessionId(lastSessionId)
      }
    }
  }, [sessionParam])

  useEffect(() => {
    // Apply dark mode
    if (isDarkMode) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }, [isDarkMode])

  const handleLogout = () => {
    localStorage.removeItem('lastSessionId')
    setSessionId(null)
    navigate('/')
  }

  const handleDarkModeToggle = () => {
    setIsDarkMode(!isDarkMode)
    localStorage.setItem('darkMode', !isDarkMode)
  }

  const handleUploadComplete = (result) => {
    if (result.sessionId) {
      setSessionId(result.sessionId)
      localStorage.setItem('lastSessionId', result.sessionId)
      navigate(`/?session=${result.sessionId}`)
    }
  }

  return (
    <div className="flex h-screen bg-slate-950 text-slate-100">
      {/* Sidebar */}
      <Sidebar
        onLogout={handleLogout}
        isDarkMode={isDarkMode}
        onDarkModeToggle={handleDarkModeToggle}
        currentRoute={currentRoute}
      />

      {/* Main Content */}
      <main className="flex-1 overflow-hidden">
        <Routes>
          <Route
            path="/"
            element={<Dashboard sessionId={sessionId} />}
          />
          <Route
            path="/upload"
            element={<UploadPanel onUploadComplete={handleUploadComplete} />}
          />
          <Route
            path="/reports"
            element={<ReportView sessionId={sessionId} />}
          />
          <Route
            path="/settings"
            element={
              <div className="h-full p-4">
                <div className="card max-w-2xl">
                  <div className="card-header">
                    <h2 className="card-title">Settings</h2>
                  </div>
                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-2">
                        Theme
                      </label>
                      <button
                        onClick={handleDarkModeToggle}
                        className="btn btn-secondary"
                      >
                        {isDarkMode ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
                      </button>
                    </div>
                    <p className="text-slate-400 text-sm">More settings coming soon...</p>
                  </div>
                </div>
              </div>
            }
          />
        </Routes>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <Router>
      <AppContent />
    </Router>
  )
}
