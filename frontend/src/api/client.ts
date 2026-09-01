import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

export const apiClient = axios.create({
  baseURL: API_URL,
})

// Ambatanisha token ya login kwenye kila request kiotomatiki
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('cdr_token')
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Kama token imeisha muda (401), rudisha mtumiaji kwenye login
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      localStorage.removeItem('cdr_token')
      localStorage.removeItem('cdr_user')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default apiClient
