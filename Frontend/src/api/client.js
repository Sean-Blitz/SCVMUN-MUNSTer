import axios from 'axios'
import { useAuthStore } from '../stores/auth'
import { useToastStore } from '../stores/toast'
import router from '../router'

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  headers: {
    'Content-Type': 'application/json'
  }
})

apiClient.interceptors.request.use((config) => {
  const authStore = useAuthStore()
  if (authStore.token) {
    config.headers.Authorization = `Bearer ${authStore.token}`
  }
  return config
})

// Automatically catch backend errors and display popups
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const toastStore = useToastStore()
    const authStore = useAuthStore()

    if (error.response) {
      // Backend responded with an error message in JSON
      const errorMessage = error.response.data?.message || `Server Error (${error.response.status})`
      toastStore.showToast(errorMessage, 'error')

      if (error.response.status === 401) {
        authStore.logout()
        router.push('/')
      }
    } else if (error.request) {
      // Network failure or backend server down
      toastStore.showToast('Unable to reach the server. Please check your network connection.', 'error')
    } else {
      toastStore.showToast(error.message, 'error')
    }

    return Promise.reject(error)
  }
)

export default apiClient