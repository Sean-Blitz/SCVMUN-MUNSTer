import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

// =============================================================================
// TEMPORARY DEV SWITCH - has no effect in a production build
//
// Change the word on the `DEV_ROLE` line to 'delegate', 'advisor', 'chair' or 'admin' and
// the app opens that role's dashboard without logging in as it. Set it back to `null` for
// the real behaviour. Everything below is gated on `import.meta.env.DEV`, which Vite
// replaces with `false` in `npm run build`, so a forgotten word cannot ship.
//
// What a preview can and cannot do: the *router* is satisfied by this switch, but every API
// request still authenticates with a real token, because the backend decides what is
// allowed. That means:
//   - `admin` works fully (and so does `chair`, which the router also grants admins) while
//     you are logged in as the admin account: the token is real, the role matches.
//   - `delegate` / `advisor` render their layout, but their endpoints answer 403, so panels
//     stay empty. To make a preview fully functional, paste that role's real token into
//     DEV_TOKENS below: log in as the role once in another browser profile, then run
//     `localStorage.getItem('token')` in its console.
// The switch never writes to localStorage, so a real session survives turning it on and off.
// =============================================================================
const DEV_ROLE = null

const DEV_TOKENS = {
  delegate: null,
  advisor: null,
  chair: null,
  admin: null
}

const previewRole = import.meta.env.DEV && DEV_ROLE ? DEV_ROLE : "delegate"

/** Whether a role preview is active. `api/client.js` asks, so a 401 cannot end the preview. */
export function isPreviewing() {
  return Boolean(previewRole)
}

export const useAuthStore = defineStore('auth', () => {
  const storedToken = localStorage.getItem('token') || null
  const storedUser = JSON.parse(localStorage.getItem('user') || 'null')

  // While previewing, identity comes from the switch. The token stays the real one when
  // there is one, so the endpoints this role may call still work; otherwise a placeholder is
  // enough, because isLoggedIn only asks whether a token exists.
  const token = ref(
    previewRole ? DEV_TOKENS[previewRole] || storedToken || 'dev-preview-token' : storedToken
  )
  const user = ref(
    previewRole ? { name: `Preview (${previewRole})`, role: previewRole } : storedUser
  )

  const isLoggedIn = computed(() => !!token.value)
  const userRole = computed(() => user.value?.role || null)

  function setAuth(userData, authToken) {
    // The switch wins while it is on: set DEV_ROLE back to null to log in for real.
    if (previewRole) return

    user.value = userData
    token.value = authToken
    // Persisted so a page refresh keeps the session: these are the values read above.
    localStorage.setItem('token', authToken)
    localStorage.setItem('user', JSON.stringify(userData))
  }

  function logout() {
    // A preview has nothing to log out of, and clearing here would bounce you to the login
    // screen the moment any request came back 401.
    if (previewRole) return

    user.value = null
    token.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  return { token, user, isLoggedIn, userRole, setAuth, logout }
})
