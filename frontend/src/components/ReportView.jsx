import React, { useState, useEffect } from 'react'
import { Download, Printer, Copy, CheckCircle, Loader } from 'lucide-react'
import api from '../services/api'

const ReportView = ({ sessionId, reportId = null, onClose = null }) => {
  const [report, setReport] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isCopied, setIsCopied] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (reportId) {
      loadReport()
    }
  }, [reportId])

  const loadReport = async () => {
    setIsLoading(true)
    setError(null)

    try {
      // In a real app, fetch the specific report
      const response = await api.generateReport(sessionId)
      setReport(response.data)
    } catch (err) {
      setError('Failed to load report')
      console.error('Report load error:', err)
    } finally {
      setIsLoading(false)
    }
  }

  const generateReport = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await api.generateReport(sessionId)
      setReport(response.data)
    } catch (err) {
      setError('Failed to generate report')
      console.error('Report generation error:', err)
    } finally {
      setIsLoading(false)
    }
  }

  const handleCopy = () => {
    if (report?.content) {
      navigator.clipboard.writeText(report.content)
      setIsCopied(true)
      setTimeout(() => setIsCopied(false), 2000)
    }
  }

  const handleDownload = () => {
    if (report?.content) {
      const element = document.createElement('a')
      element.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(report.content))
      element.setAttribute('download', `report-${new Date().toISOString().split('T')[0]}.txt`)
      element.style.display = 'none'
      document.body.appendChild(element)
      element.click()
      document.body.removeChild(element)
    }
  }

  const handlePrint = () => {
    const printWindow = window.open('', '', 'height=600,width=800')
    printWindow.document.write(`
      <html>
        <head>
          <title>Traffic Intelligence Report</title>
          <style>
            body { font-family: monospace; white-space: pre-wrap; padding: 20px; }
            h1 { font-size: 24px; margin-bottom: 20px; }
          </style>
        </head>
        <body>
          ${report?.content || ''}
        </body>
      </html>
    `)
    printWindow.document.close()
    printWindow.print()
  }

  return (
    <div className="card h-full flex flex-col">
      <div className="card-header flex justify-between items-center">
        <div>
          <h3 className="card-title">Analysis Report</h3>
          <p className="card-subtitle">
            {report ? 'Generated ' + new Date(report.timestamp).toLocaleString() : 'No report generated'}
          </p>
        </div>
        {onClose && (
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200">
            ✕
          </button>
        )}
      </div>

      {!report ? (
        <div className="flex-1 flex flex-col items-center justify-center">
          {isLoading ? (
            <div className="text-center">
              <Loader className="w-12 h-12 text-blue-400 animate-spin mx-auto mb-4" />
              <p className="text-slate-400">Generating report...</p>
            </div>
          ) : (
            <div className="text-center">
              <p className="text-slate-400 mb-4">No report generated yet</p>
              <button
                onClick={generateReport}
                className="btn btn-primary"
              >
                Generate Report
              </button>
            </div>
          )}

          {error && (
            <div className="mt-4 bg-red-900 border border-red-700 rounded-lg p-3 w-full">
              <p className="text-sm text-red-200">{error}</p>
            </div>
          )}
        </div>
      ) : (
        <>
          {/* Report Controls */}
          <div className="flex gap-2 mb-4">
            <button
              onClick={handleCopy}
              className="btn btn-secondary btn-sm flex items-center gap-2"
            >
              {isCopied ? (
                <>
                  <CheckCircle className="w-4 h-4" />
                  Copied!
                </>
              ) : (
                <>
                  <Copy className="w-4 h-4" />
                  Copy
                </>
              )}
            </button>
            <button
              onClick={handleDownload}
              className="btn btn-secondary btn-sm flex items-center gap-2"
            >
              <Download className="w-4 h-4" />
              Download
            </button>
            <button
              onClick={handlePrint}
              className="btn btn-secondary btn-sm flex items-center gap-2"
            >
              <Printer className="w-4 h-4" />
              Print
            </button>
            <button
              onClick={generateReport}
              className="btn btn-primary btn-sm ml-auto"
            >
              Regenerate
            </button>
          </div>

          {/* Report Content */}
          <div className="flex-1 overflow-y-auto bg-slate-950 rounded-lg p-4 font-mono text-sm text-slate-300 border border-slate-800">
            <pre className="whitespace-pre-wrap break-words">{report.content}</pre>
          </div>

          {/* Metadata */}
          {report.metadata && (
            <div className="border-t border-slate-800 mt-4 pt-4 grid grid-cols-2 gap-4 text-xs">
              {Object.entries(report.metadata).map(([key, value]) => (
                <div key={key}>
                  <p className="text-slate-500">{key}</p>
                  <p className="text-slate-300 font-mono">{String(value)}</p>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default ReportView
