<template>
  <div class="page-container">
    <header class="app-header">
      <h1>ACCESS PORTAL</h1>
    </header>

    <main class="forms-wrapper">
      <div class="auth-card">
        <h2>ACCOUNT ACCESS</h2>
        
        <form @submit.prevent class="auth-form">
          <div class="input-group">
            <span class="icon">#</span> 
            <input 
              type="text" 
              v-model="userHash" 
              placeholder="HASH / ACCESS CODE" 
              required
            />
          </div>

          <div class="input-group">
            <span class="icon">🔒</span> 
            <input 
              type="password" 
              v-model="userPassword" 
              placeholder="PASSWORD" 
              required
            />
          </div>

          <div class="button-group">
            <button 
              type="button" 
              @click="handleLogin" 
              class="btn btn-login"
            >
              LOG IN
            </button>
            
            <button 
              type="button" 
              @click="handleRegister" 
              class="btn btn-register"
            >
              FIRST-TIME REGISTER
            </button>
          </div>
        </form>

        <p class="registration-note">
          First time? Entering your details and clicking <strong>First-Time Register</strong> will link your password to your unique hash on the backend.
        </p>

        <p class="forgot-password">
          Forgot Password? Email sg@scvmun.com to reset it.
        </p>
      </div>
    </main>

    <footer class="bottom-notes-section">
      <div class="notes-container">
        <p>Your access code is confidential. Do not share it with other delegates!</p>
        <p>If you do not yet have your access code, talk with your advisor.</p>
        <p>Good luck on conference day.</p>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { ref } from 'vue'

// Unified reactive state for both actions
const userHash = ref('')
const userPassword = ref('')

const handleLogin = () => {
  if (!userHash.value || !userPassword.value) {
    alert('Please enter both your hash and password.')
    return
  }
  console.log('Logging in with:', userHash.value, userPassword.value)
  // Connect to your authService here
}

const handleRegister = () => {
  if (!userHash.value || !userPassword.value) {
    alert('Please enter both your hash and password.')
    return
  }
  console.log('Registering with:', userHash.value, userPassword.value)
  // Connect to your authService here
}
</script>

<style scoped>
/* GENERAL LAYOUT */
.page-container {
  min-height: 100vh;
  background-color: #1a1d21;
  color: #ffffff;
  display: flex;
  flex-direction: column;
  font-family: Arial, sans-serif;
  padding: 0 20px;
}

.app-header {
  padding: 20px 0;
}

.app-header h1 {
  font-size: 1.5rem;
  font-weight: bold;
  color: #e0e0e0;
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
  background-color: #2a2e35;
  padding: 40px;
  border-radius: 8px;
  border: 1px solid #3f444e;
  box-shadow: 0 4px 6px rgba(0,0,0,0.3);
}

.auth-card h2 {
  font-size: 1.25rem;
  font-weight: normal;
  text-align: center;
  margin-bottom: 30px;
  color: #ffffff;
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
  background-color: #1a1d21;
  border: 1px solid #3f444e;
  border-radius: 4px;
  padding: 10px 15px;
}

.input-group input {
  flex: 1;
  background: transparent;
  border: none;
  color: #ffffff;
  padding-left: 10px;
  font-size: 1rem;
}

.input-group input:focus {
  outline: none;
}

.input-group input::placeholder {
  color: #888888;
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
  border-radius: 4px;
  font-weight: bold;
  cursor: pointer;
  font-size: 0.95rem;
  transition: background-color 0.2s ease;
}

.btn-login {
  background-color: #6366f1;
  color: #ffffff;
}

.btn-login:hover {
  background-color: #4f46e5;
}

.btn-register {
  background-color: #22d3ee;
  color: #111111;
}

.btn-register:hover {
  background-color: #06b6d4;
}

/* CONTEXT TEXT */
.registration-note {
  margin-top: 25px;
  font-size: 0.85rem;
  color: #aaaaaa;
  text-align: center;
  line-height: 1.4;
}

.registration-note strong {
  color: #ffffff;
}

.forgot-password {
  margin-top: 15px;
  text-align: center;
  font-size: 0.85rem;
  color: #aaaaaa;
}

/* FOOTER NOTES */
.bottom-notes-section {
  padding: 30px 0;
  display: flex;
  justify-content: center;
}

.notes-container {
  background-color: #2a2e35;
  border: 1px solid #3f444e;
  border-radius: 8px;
  padding: 20px 30px;
  text-align: center;
  width: 100%;
  max-width: 800px;
}

.notes-container p {
  margin: 5px 0;
  font-size: 0.9rem;
  color: #cccccc;
  line-height: 1.5;
}

/* Responsive adjustment for small screens */
@media (max-width: 480px) {
  .button-group {
    flex-direction: column;
  }
}
</style>