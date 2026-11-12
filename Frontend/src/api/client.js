import axios from 'axios'
import { isPreviewing, useAuthStore } from '../stores/auth'
import { useToastStore } from '../stores/toast'
import router from '../router'

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api'
  // No default Content-Type on purpose. Setting one here made axios treat every body the
  // same way: with `application/json` pinned as the default, a FormData body was serialised
  // as JSON ({"paper": {}}) and the file never reached the server, which answered 422
  // "Paper is required" for the position-paper upload. Axios sets application/json itself
  // for plain-object bodies, and leaves FormData alone so the browser can add the multipart
  // boundary.
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

      // A role preview is not a real session, so a 401 must not end it - otherwise the first
      // request from a previewed dashboard bounces you straight back to the login screen.
      // isPreviewing() is false in every production build (see stores/auth.js).
      if (error.response.status === 401 && !isPreviewing()) {
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