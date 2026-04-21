import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error.response?.data || error.message)
    return Promise.reject(error)
  }
)

export const api = {
  // Session endpoints
  createSession: (config) =>
    apiClient.post('/sessions', config),

  getSession: (sessionId) =>
    apiClient.get(`/sessions/${sessionId}`),

  listSessions: () =>
    apiClient.get('/sessions'),

  deleteSession: (sessionId) =>
    apiClient.delete(`/sessions/${sessionId}`),

  // Video/Stream upload endpoints
  uploadVideo: (file, onProgress) => {
    const formData = new FormData()
    formData.append('file', file)

    return apiClient.post('/sessions/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      },
      onUploadProgress: (progressEvent) => {
        if (onProgress) {
          onProgress(Math.round((progressEvent.loaded / progressEvent.total) * 100))
        }
      }
    })
  },

  // Stream URL endpoints.
  // Accepts either a raw URL string (legacy) or an options object.
  // Backend expects { name, stream_url, fps }.
  streamFromUrl: (urlOrOptions) => {
    const payload =
      typeof urlOrOptions === 'string'
        ? { name: 'Live Stream', stream_url: urlOrOptions, fps: 15 }
        : {
            name: urlOrOptions.name || 'Live Stream',
            stream_url: urlOrOptions.stream_url || urlOrOptions.url,
            fps: urlOrOptions.fps || 15,
          }
    return apiClient.post('/sessions/stream', payload)
  },

  // Detection endpoints
  getDetections: (sessionId, skip = 0, limit = 50) =>
    apiClient.get(`/sessions/${sessionId}/detections`, { params: { skip, limit } }),

  getDetectionStats: (sessionId) =>
    apiClient.get(`/sessions/${sessionId}/detections/stats`),

  // Incident endpoints
  getIncidents: (sessionId) =>
    apiClient.get(`/sessions/${sessionId}/incidents`),

  getIncidentStats: (sessionId) =>
    apiClient.get(`/sessions/${sessionId}/incidents/stats`),

  // Stats endpoints
  getStats: (sessionId) =>
    apiClient.get(`/sessions/${sessionId}/stats`),

  getVehicleCounts: (sessionId) =>
    apiClient.get(`/sessions/${sessionId}/vehicle-counts`),

  getHeatmap: (sessionId) =>
    apiClient.get(`/sessions/${sessionId}/heatmap`),

  getSpeeds: (sessionId) =>
    apiClient.get(`/sessions/${sessionId}/speeds`),

  // Chat/AI endpoints with session_id in body
  sendMessage: (sessionId, message) =>
    apiClient.post('/chat', { session_id: sessionId, message }),

  // Alternative endpoint for chat
  sendChatMessage: (sessionId, message) =>
    apiClient.post(`/sessions/${sessionId}/chat`, { message }),

  getChatHistory: (sessionId, limit = 50) =>
    apiClient.get(`/sessions/${sessionId}/chat/history`, { params: { limit } }),

  // Report endpoints
  generateReport: (options = {}) =>
    apiClient.post('/reports/generate', options),

  getReports: (sessionId) =>
    apiClient.get(`/sessions/${sessionId}/reports`),

  downloadReport: (reportId) =>
    apiClient.get(`/reports/${reportId}/download`, { responseType: 'blob' }),

  // Demo mode endpoints
  startDemo: () =>
    apiClient.post('/demo/start'),

  stopDemo: () =>
    apiClient.post('/demo/stop'),

  // Zone management endpoints
  createZone: (zoneData) =>
    apiClient.post('/zones', zoneData),

  getZones: () =>
    apiClient.get('/zones'),

  getZoneStats: (zoneId) =>
    apiClient.get(`/zones/${zoneId}/stats`),

  deleteZone: (zoneId) =>
    apiClient.delete(`/zones/${zoneId}`),

  // Health check
  healthCheck: () =>
    apiClient.get('/health'),

  // Config endpoints
  getConfig: () =>
    apiClient.get('/config'),

  updateConfig: (config) =>
    apiClient.put('/config', config),

  // ---- Scene Intelligence: watchlist rules -----------------------------
  listRules: (sessionId) =>
    apiClient.get(`/scene/sessions/${sessionId}/rules`),

  createRule: (sessionId, body) =>
    apiClient.post(`/scene/sessions/${sessionId}/rules`, body),

  deleteRule: (sessionId, ruleId) =>
    apiClient.delete(`/scene/sessions/${sessionId}/rules/${ruleId}`),

  seedDemoRules: (sessionId) =>
    apiClient.post(`/scene/sessions/${sessionId}/rules/seed`),

  listRulePresets: () =>
    apiClient.get('/scene/rule-presets'),

  // ---- Scene Intelligence: monitor zones (new schema) ------------------
  listMonitorZones: (sessionId) =>
    apiClient.get(`/scene/sessions/${sessionId}/zones`),

  replaceMonitorZones: (sessionId, zones) =>
    apiClient.put(`/scene/sessions/${sessionId}/zones`, zones),

  // ---- Scene Intelligence: alerts --------------------------------------
  listAlerts: (sessionId, params = {}) =>
    apiClient.get(`/scene/sessions/${sessionId}/alerts`, { params }),

  getAlertSnapshot: (sessionId, alertId) =>
    apiClient.get(`/scene/sessions/${sessionId}/alerts/${alertId}/snapshot`),
}

export default api
