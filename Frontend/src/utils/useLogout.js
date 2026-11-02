import { useRouter } from 'vue-router'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/auth'

// Signing out is one operation in one place: revoke the session server-side, then clear the
// local session and return to the login screen. Shared by the shell's navbar and by pages
// that carry their own header.
export function useLogout() {
  const router = useRouter()
  const authStore = useAuthStore()

  const handleLogout = async () => {
    try {
      // Revoke the session server-side too; a failure must not block signing out locally.
      await apiClient.post('/auth/logout')
    } catch (error) {
      // Ignored on purpose: the token is cleared below regardless.
    }
    authStore.logout()
    router.push('/')
  }

  return { handleLogout }
}
