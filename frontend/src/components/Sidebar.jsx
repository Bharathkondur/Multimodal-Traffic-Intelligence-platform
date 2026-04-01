import React, { useState } from 'react'
import { BarChart3, Settings, FileText, LogOut, Moon, Sun, Menu, X, Upload } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'

const Sidebar = ({ onLogout = null, isDarkMode = true, onDarkModeToggle = null, currentRoute = 'dashboard' }) => {
  const [isOpen, setIsOpen] = useState(true)
  const location = useLocation()

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: BarChart3, path: '/' },
    { id: 'upload', label: 'Upload', icon: Upload, path: '/upload' },
    { id: 'reports', label: 'Reports', icon: FileText, path: '/reports' },
    { id: 'settings', label: 'Settings', icon: Settings, path: '/settings' }
  ]

  const getActiveId = () => {
    const path = location.pathname
    if (path === '/') return 'dashboard'
    if (path.startsWith('/upload')) return 'upload'
    if (path.startsWith('/reports')) return 'reports'
    if (path.startsWith('/settings')) return 'settings'
    return currentRoute
  }

  const activeId = getActiveId()

  return (
    <>
      {/* Mobile Menu Toggle */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="md:hidden fixed top-4 left-4 z-50 btn btn-secondary btn-sm"
      >
        {isOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
      </button>

      {/* Sidebar */}
      <aside
        className={`fixed md:relative top-0 left-0 h-full w-64 bg-slate-900 border-r border-slate-800 flex flex-col transition-transform duration-300 z-40 ${
          isOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
        }`}
      >
        {/* Logo */}
        <div className="p-6 border-b border-slate-800">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
              <BarChart3 className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-slate-100">Traffic AI</h1>
              <p className="text-xs text-slate-400">Intelligence Platform</p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-2">
          {navItems.map(({ id, label, icon: Icon, path }) => (
            <Link
              key={id}
              to={path}
              onClick={() => setIsOpen(false)}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                activeId === id
                  ? 'bg-blue-600 text-white'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
              }`}
            >
              <Icon className="w-5 h-5" />
              <span>{label}</span>
            </Link>
          ))}
        </nav>

        {/* Bottom Actions */}
        <div className="border-t border-slate-800 p-4 space-y-2">
          {/* Dark Mode Toggle */}
          <button
            onClick={onDarkModeToggle}
            className="w-full flex items-center justify-between px-4 py-3 rounded-lg text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
            title={isDarkMode ? 'Light mode' : 'Dark mode'}
          >
            <span className="text-sm font-medium">Theme</span>
            {isDarkMode ? (
              <Moon className="w-4 h-4" />
            ) : (
              <Sun className="w-4 h-4" />
            )}
          </button>

          {/* Logout */}
          <button
            onClick={onLogout}
            className="w-full flex items-center gap-3 px-4 py-3 rounded-lg text-slate-400 hover:bg-red-900 hover:text-red-200 transition-colors"
          >
            <LogOut className="w-4 h-4" />
            <span className="text-sm font-medium">Logout</span>
          </button>
        </div>

        {/* Status Indicator */}
        <div className="border-t border-slate-800 p-4">
          <div className="flex items-center gap-2 text-xs">
            <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
            <span className="text-slate-400">System Online</span>
          </div>
          <p className="text-xs text-slate-600 mt-1">Ready to analyze</p>
        </div>
      </aside>

      {/* Mobile Overlay */}
      {isOpen && (
        <div
          onClick={() => setIsOpen(false)}
          className="md:hidden fixed inset-0 bg-black bg-opacity-50 z-30"
        ></div>
      )}
    </>
  )
}

export default Sidebar
