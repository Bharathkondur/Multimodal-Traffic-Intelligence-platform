import React, { useState, useRef } from 'react'
import { Upload, Link, Video, Loader, CheckCircle } from 'lucide-react'
import api from '../services/api'

const UploadPanel = ({ onUploadStart = null, onUploadComplete = null, disabled = false }) => {
  const [uploadProgress, setUploadProgress] = useState(0)
  const [isUploading, setIsUploading] = useState(false)
  const [rtspUrl, setRtspUrl] = useState('')
  const [selectedFile, setSelectedFile] = useState(null)
  const [uploadStatus, setUploadStatus] = useState(null)
  const [isDragOver, setIsDragOver] = useState(false)
  const fileInputRef = useRef(null)

  const handleFileSelect = async (file) => {
    if (!file) return

    // Validate file type
    if (!file.type.startsWith('video/')) {
      setUploadStatus({ type: 'error', message: 'Please select a video file' })
      return
    }

    setSelectedFile(file)
    await uploadFile(file)
  }

  const uploadFile = async (file) => {
    setIsUploading(true)
    setUploadProgress(0)
    setUploadStatus(null)

    try {
      if (onUploadStart) {
        onUploadStart(file.name)
      }

      const response = await api.uploadVideo(file, (progress) => {
        setUploadProgress(progress)
      })

      setUploadStatus({
        type: 'success',
        message: 'Video uploaded successfully'
      })

      if (onUploadComplete) {
        onUploadComplete({
          sessionId: response.data.session_id,
          fileName: file.name
        })
      }

      // Clear after 3 seconds
      setTimeout(() => {
        setUploadStatus(null)
        setUploadProgress(0)
        setSelectedFile(null)
      }, 3000)
    } catch (error) {
      setUploadStatus({
        type: 'error',
        message: error.response?.data?.detail || 'Upload failed'
      })
    } finally {
      setIsUploading(false)
    }
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(true)
  }

  const handleDragLeave = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(false)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(false)

    const files = e.dataTransfer.files
    if (files.length > 0) {
      handleFileSelect(files[0])
    }
  }

  const handleRtspSubmit = async () => {
    if (!rtspUrl.trim()) {
      setUploadStatus({
        type: 'error',
        message: 'Please enter an RTSP URL'
      })
      return
    }

    setIsUploading(true)
    setUploadStatus(null)

    try {
      if (onUploadStart) {
        onUploadStart(rtspUrl)
      }

      // In a real app, this would create a session with RTSP source
      const response = await api.createSession({
        source_type: 'rtsp',
        source_url: rtspUrl
      })

      setUploadStatus({
        type: 'success',
        message: 'RTSP stream connected'
      })

      if (onUploadComplete) {
        onUploadComplete({
          sessionId: response.data.session_id,
          source: rtspUrl
        })
      }

      setTimeout(() => {
        setUploadStatus(null)
        setRtspUrl('')
      }, 3000)
    } catch (error) {
      setUploadStatus({
        type: 'error',
        message: error.response?.data?.detail || 'Failed to connect to RTSP stream'
      })
    } finally {
      setIsUploading(false)
    }
  }

  return (
    <div className="card h-full flex flex-col">
      <div className="card-header">
        <h3 className="card-title">Add Source</h3>
        <p className="card-subtitle">Upload video, RTSP stream, or select webcam</p>
      </div>

      <div className="space-y-4 flex-1 flex flex-col">
        {/* File Upload */}
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Video File
          </label>
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
              isDragOver
                ? 'border-blue-500 bg-blue-500 bg-opacity-10'
                : 'border-slate-700 hover:border-slate-600'
            } ${disabled || isUploading ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept="video/*"
              onChange={(e) => handleFileSelect(e.target.files?.[0])}
              disabled={disabled || isUploading}
              className="hidden"
            />

            {isUploading && !rtspUrl ? (
              <div>
                <Loader className="w-8 h-8 text-blue-400 mx-auto mb-2 animate-spin" />
                <p className="text-sm text-slate-300">Uploading...</p>
                <div className="w-full bg-slate-700 rounded-full h-2 mt-3">
                  <div
                    className="bg-blue-500 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${uploadProgress}%` }}
                  ></div>
                </div>
                <p className="text-xs text-slate-400 mt-2">{uploadProgress}%</p>
              </div>
            ) : uploadStatus?.type === 'success' ? (
              <div>
                <CheckCircle className="w-8 h-8 text-green-400 mx-auto mb-2" />
                <p className="text-sm text-green-400">{uploadStatus.message}</p>
              </div>
            ) : (
              <div>
                <Upload className="w-8 h-8 text-slate-500 mx-auto mb-2" />
                <p className="text-sm text-slate-300">
                  Drag & drop video here or click to select
                </p>
                <p className="text-xs text-slate-500 mt-1">MP4, WebM, or other video format</p>
              </div>
            )}
          </div>
        </div>

        {/* RTSP URL Input */}
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            RTSP Stream URL
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={rtspUrl}
              onChange={(e) => setRtspUrl(e.target.value)}
              placeholder="rtsp://example.com/stream"
              disabled={disabled || isUploading}
              className="input flex-1"
            />
            <button
              onClick={handleRtspSubmit}
              disabled={disabled || isUploading || !rtspUrl.trim()}
              className="btn btn-primary"
            >
              {isUploading && rtspUrl ? (
                <Loader className="w-4 h-4 animate-spin" />
              ) : (
                <Link className="w-4 h-4" />
              )}
            </button>
          </div>
        </div>

        {/* Webcam Option */}
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Webcam
          </label>
          <button
            disabled={disabled || isUploading}
            className="w-full btn btn-secondary flex items-center justify-center gap-2"
            onClick={() => {
              // Implement webcam selection
              if (onUploadStart) {
                onUploadStart('Webcam')
              }
              if (onUploadComplete) {
                onUploadComplete({
                  sessionId: 'webcam-session',
                  source: 'webcam'
                })
              }
            }}
          >
            <Video className="w-4 h-4" />
            Use Default Webcam
          </button>
        </div>

        {/* Status Message */}
        {uploadStatus && uploadStatus.type === 'error' && (
          <div className="bg-red-900 border border-red-700 rounded-lg p-3">
            <p className="text-sm text-red-200">{uploadStatus.message}</p>
          </div>
        )}

        {/* Recent Files Info */}
        {!isUploading && (
          <div className="bg-slate-800 rounded-lg p-3 text-xs text-slate-400 mt-auto">
            <p className="font-semibold text-slate-300 mb-2">Supported formats:</p>
            <ul className="space-y-1 text-slate-500">
              <li>- Video files (MP4, WebM, AVI, MOV)</li>
              <li>- RTSP/RTMP streams</li>
              <li>- Webcam and IP cameras</li>
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}

export default UploadPanel
