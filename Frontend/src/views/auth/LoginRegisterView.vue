<template>
  <div class="page-container">
    <header class="app-header">
      <img 
    src="@/assets/logo.png" 
    alt="SCVMUN Logo" 
    class="header-logo"
  />
    </header>

    <main class="forms-wrapper">
      <div class="auth-card">
        <h2>Account Access</h2>
        
        <form @submit.prevent class="auth-form">
          <div class="input-group">
            <span class="icon">#</span> 
            <input 
              type="text" 
              v-model="userHash" 
              placeholder="Hash / Access Code" 
              required
            />
          </div>

          <div class="input-group">
            <span class="icon">🔒</span> 
            <input 
              type="password" 
              v-model="userPassword" 
              placeholder="Password" 
              required
            />
          </div>

          <div v-if="captchaEnabled" class="captcha-group">
            <div ref="captchaContainer" class="captcha-widget"></div>
            <p v-if="captchaError" class="captcha-error">{{ captchaError }}</p>
          </div>

          <div class="button-group">
            <button 
              type="button" 
              @click="handleLogin" 
              :disabled="isLoading || captchaPending"
              class="btn btn-login"
            >
              Log In
            </button>
            
            <button 
              type="button" 
              @click="handleRegister" 
              :disabled="isLoading || captchaPending"
              class="btn btn-register"
            >
              First-Time Register
            </button>
          </div>
        </form>

        <p class="registration-note">
          Click <strong>First-Time Register</strong> to create your account using the hash you received from your advisor. Afterwards, you can use the password you set above to log in again.
        </p>

        <p class="forgot-password">
          Forgot Password? Email sg@scvmun.com to reset it.
        </p>
      </div>
    </main>

    <footer class="bottom-notes-section">
      <div class="notes-container">
        <p><strong>Note: </strong>Your access code/hash is confidential. Do not share it with other delegates!</p>
        <p>If you do not yet have your access code, talk with your advisor.</p>
        <p>Good luck on conference day!</p>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'

const router = useRouter()
const authStore = useAuthStore()
const toastStore = useToastStore()

// Unified reactive state for both actions
const userHash = ref('')
const userPassword = ref('')
const isLoading = ref(false)

// ---------- Human check (Cloudflare Turnstile) ----------
// The site key is public and baked in at build time, so leaving it unset disables the
// widget completely - which is how development runs, matching the backend's behaviour
// when TURNSTILE_SECRET_KEY is absent.
const turnstileSiteKey = import.meta.env.VITE_TURNSTILE_SITE_KEY || ''
const captchaEnabled = Boolean(turnstileSiteKey)
const TURNSTILE_SCRIPT = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'

const captchaContainer = ref(null)
const captchaToken = ref('')
const captchaWidgetId = ref(null)
const captchaError = ref('')

// Turnstile tokens are single-use and expire after 5 minutes, so a submission needs one
// that this page has just obtained: until the callback fires there is nothing to send.
const captchaPending = computed(() => captchaEnabled && !captchaToken.value)

let scriptPromise = null

const loadTurnstile = () => {
  if (window.turnstile) return Promise.resolve()
  if (scriptPromise) return scriptPromise

  scriptPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = TURNSTILE_SCRIPT
    script.async = true
    script.defer = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Turnstile failed to load'))
    document.head.appendChild(script)
  })

  return scriptPromise
}

const renderCaptcha = () => {
  if (!captchaEnabled || !window.turnstile || !captchaContainer.value) return

  captchaWidgetId.value = window.turnstile.render(captchaContainer.value, {
    sitekey: turnstileSiteKey,
    theme: 'light',
    // Must match captcha.ACTION in the backend: Siteverify echoes this back and the server
    // rejects a token minted for any other action.
    action: 'auth',
    // Stays out of the way unless Cloudflare decides an interactive challenge is needed.
    appearance: 'interaction-only',
    // Fetch a fresh token when the old one expires behind the five-minute limit.
    'refresh-expired': 'auto',
    callback: (token) => {
      captchaToken.value = token
      captchaError.value = ''
    },
    'expired-callback': () => { captchaToken.value = '' },
    'timeout-callback': () => { captchaToken.value = '' },
    'error-callback': () => {
      captchaToken.value = ''
      captchaError.value = 'The human check failed to run. Please refresh the page.'
    }
  })
}

// A failed submit has consumed the token (they are single-use), so the next attempt needs
// a fresh one. Safe to call on any error, including a network failure.
const resetCaptcha = () => {
  captchaToken.value = ''
  if (captchaWidgetId.value !== null && window.turnstile) {
    window.turnstile.reset(captchaWidgetId.value)
  }
}

const captchaHeaders = () =>
  captchaEnabled && captchaToken.value ? { 'X-Turnstile-Token': captchaToken.value } : {}

onMounted(async () => {
  if (!captchaEnabled) return
  try {
    await loadTurnstile()
    renderCaptcha()
  } catch (error) {
    captchaError.value = 'The human check could not load. Please refresh the page.'
  }
})

onBeforeUnmount(() => {
  if (captchaWidgetId.value !== null && window.turnstile) {
    window.turnstile.remove(captchaWidgetId.value)
  }
})

const handleLogin = async () => {
  if (!userHash.value || !userPassword.value) {
    toastStore.showToast('Please enter both your hash and password.', 'error')
    return
  }
  if (captchaPending.value) {
    toastStore.showToast('Please complete the human check first.', 'error')
    return
  }

  isLoading.value = true
  try {
    // 1. Send credentials to backend login endpoint
    const response = await apiClient.post(
      '/auth/login',
      { hash: userHash.value, password: userPassword.value },
      { headers: captchaHeaders() }
    )

    // 2. Extract returned user and token
    const { user, token } = response.data

    // 3. Save session into Pinia Auth Store
    authStore.setAuth(user, token)

    toastStore.showToast(`Welcome back, ${user.name || 'User'}!`, 'success')

    // 4. Redirect based on their role
    router.push(`/${user.role}/dashboard`)
  } catch (error) {
    // Backend error message will automatically trigger via the global Toast Interceptor
    resetCaptcha()
  } finally {
    isLoading.value = false
  }
}

const handleRegister = async () => {
  if (!userHash.value || !userPassword.value) {
    toastStore.showToast('Please enter both your hash and password.', 'error')
    return
  }
  if (captchaPending.value) {
    toastStore.showToast('Please complete the human check first.', 'error')
    return
  }

  isLoading.value = true
  try {
    // 1. Send registration payload to backend
    const response = await apiClient.post(
      '/auth/register',
      { hash: userHash.value, password: userPassword.value },
      { headers: captchaHeaders() }
    )

    const { user, token } = response.data

    // 2. Save session into Pinia Auth Store
    authStore.setAuth(user, token)

    toastStore.showToast('Account registered successfully!', 'success')

    // 3. Redirect to role portal
    router.push(`/${user.role}/dashboard`)
  } catch (error) {
    // Backend error message handles popup automatically
    resetCaptcha()
  } finally {
    isLoading.value = false
  }
}
</script>

<style scoped>
/* GENERAL LAYOUT */
.page-container {
  min-height: 100vh;
  background: 
    /* Subtle geometric angled lines */
    repeating-linear-gradient(
      225deg,
      rgba(255, 255, 255, 0) 10px,
      rgba(246, 246, 246, 0.076) 10px,
      transparent 20px,
      transparent 40px
    ),
    /* Main color gradient: Top-Right to Bottom-Left */
    linear-gradient(225deg, #009ddbda 20%,#00007e93 80%);
  color: #ffffff;
  display: flex;
  flex-direction: column;
  font-family: Arial, sans-serif;
  padding: 0 20px;
}

.app-header {
  padding: 20px 0;
  display: flex;
  justify-content: flex-start; /* Aligns content to the top right */
  align-items: center;
}

.header-logo {
  height: 175px; /* Adjust height as needed */
  width: auto;  /* Maintains aspect ratio */
  object-fit: contain;
}

.app-header h1 {
  font-size: 1.5rem;
  font-weight: bold;
  color: #FFFFFF;
  margin: 0;
}

/* FORMS SECTION */
.forms-wrapper {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 40px 0;
}

/* CARD LAYOUT - Centered Single Box */
.auth-card {
  width: 100%;
  max-width: 480px;
  background-color: #009ddbda;
  padding: 40px;
  border-radius: 8px;
  border: 3px solid #e8c604;
  box-shadow: 0 4px 6px rgba(0,0,0,0.3);
}

.auth-card h2 {
  font-size: 1.25rem;
  font-weight: bold;
  text-align: center;
  margin-bottom: 30px;
  color: #00007e;
}

/* FORMS & INPUTS */
.auth-form {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.input-group {
  display: flex;
  align-items: center;
  background-color: #FFFFFF;
  border: 2px solid #e8c604;
  border-radius: 4px;
  padding: 10px 15px;
}

.input-group input {
  flex: 1;
  background: transparent;
  border: none;
  color: #00007e;
  padding-left: 10px;
  font-size: 1rem;
}

.input-group input:focus {
  outline: none;
}

.input-group input::placeholder {
  color: #00007e;
}

.icon {
  color: #aaaaaa;
}

/* BUTTON GROUP (SIDE-BY-SIDE) */
.button-group {
  display: flex;
  gap: 12px;
  margin-top: 15px;
}

.btn {
  flex: 1;
  padding: 12px;
  border: none;
  border-radius: 8px;
  font-weight: bold;
  cursor: pointer;
  font-size: 0.95rem;
  transition: background-color 0.2s ease;
}

.captcha-group {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.captcha-error {
  margin: 0;
  color: #b33;
  font-size: 0.85rem;
  text-align: center;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-login {
  background-color: #00007e;
  color: #ffffff;
}

.btn-login:hover {
  background-color: #e8c604;
}

.btn-register {
  background-color: #FFFFFF;
  color: #00007e;
}

.btn-register:hover {
  background-color: #e8c604;
}

/* CONTEXT TEXT */
.registration-note {
  margin-top: 25px;
  font-size: 0.85rem;
  color: #00007e;
  text-align: center;
  line-height: 1.4;
}

.registration-note strong {
  color: #00007e;
}

.forgot-password {
  margin-top: 15px;
  text-align: center;
  font-size: 0.85rem;
  color: #00007e;
}

/* FOOTER NOTES */
.bottom-notes-section {
  padding: 30px 0;
  display: flex;
  justify-content: center;
}

.notes-container {
  background-color: #009ddbda;
  border: 3px solid #e8c604;
  border-radius: 8px;
  padding: 20px 30px;
  text-align: center;
  width: 100%;
  max-width: 800px;
}

.notes-container p {
  margin: 5px 0;
  font-size: 0.9rem;
  color: #00007e;
  line-height: 1.5;
}

/* Responsive adjustment for small screens */
@media (max-width: 480px) {
  .button-group {
    flex-direction: column;
  }
}
</style>