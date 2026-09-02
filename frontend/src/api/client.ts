import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

export const apiClient = axios.create({
  baseURL: API_URL,
})

// Automatically attach the login token to every request
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('cdr_token')
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// If the token has expired (401), send the user back to the login page
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
