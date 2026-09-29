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

          <div class="button-group">
            <button 
              type="button" 
              @click="handleLogin" 
              class="btn btn-login"
            >
              Log In
            </button>
            
            <button 
              type="button" 
              @click="handleRegister" 
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
import { ref } from 'vue'
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

const handleLogin = async () => {
  if (!userHash.value || !userPassword.value) {
    toastStore.showToast('Please enter both your hash and password.', 'error')
    return
  }

  isLoading.value = true
  try {
    // 1. Send credentials to backend login endpoint
    const response = await apiClient.post('/auth/login', {
      hash: userHash.value,
      password: userPassword.value
    })

    // 2. Extract returned user and token
    const { user, token } = response.data

    // 3. Save session into Pinia Auth Store
    authStore.setAuth(user, token)

    toastStore.showToast(`Welcome back, ${user.name || 'User'}!`, 'success')

    // 4. Redirect based on their role
    router.push(`/${user.role}/dashboard`)
  } catch (error) {
    // Backend error message will automatically trigger via the global Toast Interceptor
  } finally {
    isLoading.value = false
  }
}

const handleRegister = async () => {
  if (!userHash.value || !userPassword.value) {
    toastStore.showToast('Please enter both your hash and password.', 'error')
    return
  }

  isLoading.value = true
  try {
    // 1. Send registration payload to backend
    const response = await apiClient.post('/auth/register', {
      hash: userHash.value,
      password: userPassword.value
    })

    const { user, token } = response.data

    // 2. Save session into Pinia Auth Store
    authStore.setAuth(user, token)

    toastStore.showToast('Account registered successfully!', 'success')

    // 3. Redirect to role portal
    router.push(`/${user.role}/dashboard`)
  } catch (error) {
    // Backend error message handles popup automatically
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