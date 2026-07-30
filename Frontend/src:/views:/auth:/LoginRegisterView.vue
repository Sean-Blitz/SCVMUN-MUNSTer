<template>
  <div class="page-container">
    <header class="app-header">
      <h1>ACCESS PORTAL</h1>
    </header>

    <main class="forms-wrapper">
      <section class="auth-section">
        <div class="auth-card">
          <h2>LOG IN</h2>
          
          <form @submit.prevent="handleLogin" class="auth-form">
            <div class="input-group">
              <span class="icon">#</span> <input 
                type="text" 
                v-model="loginHash" 
                placeholder="HASH / ACCESS CODE" 
                required
              />
            </div>

            <div class="input-group">
              <span class="icon">🔒</span> <input 
                type="password" 
                v-model="loginPassword" 
                placeholder="PASSWORD" 
                required
              />
            </div>

            <button type="submit" class="btn btn-login">LOG IN</button>
          </form>

          <p class="forgot-password">
            Forgot Password? Email sg@scvmun.com to reset it.
          </p>
        </div>
      </section>

      <section class="auth-section">
        <div class="auth-card">
          <h2>FIRST-TIME REGISTRATION</h2>
          
          <form @submit.prevent="handleRegister" class="auth-form">
            <div class="input-group">
              <span class="icon">#</span>
              <input 
                type="text" 
                v-model="registerHash" 
                placeholder="HASH / ACCESS CODE" 
                required
              />
            </div>

            <div class="input-group">
              <span class="icon">🔒</span>
              <input 
                type="password" 
                v-model="registerPassword" 
                placeholder="PASSWORD" 
                required
              />
            </div>

            <button type="submit" class="btn btn-register">REGISTER</button>
          </form>
        </div>

        <p class="registration-note">
          If unregistered, your chosen password will be linked to this unique hash on the backend.
        </p>
      </section>
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

// Reactive state for forms
const loginHash = ref('')
const loginPassword = ref('')
const registerHash = ref('')
const registerPassword = ref('')

// Placeholder functions for form submission
const handleLogin = () => {
  console.log('Logging in with:', loginHash.value, loginPassword.value)
  // Connect to your authService here
}

const handleRegister = () => {
  console.log('Registering with:', registerHash.value, registerPassword.value)
  // Connect to your authService here
}
</script>

<style scoped>
/* GENERAL LAYOUT */
.page-container {
  min-height: 100vh;
  /* Muted solid dark background */
  background-color: #1a1d21;
  color: #ffffff;
  display: flex;
  flex-direction: column;
  font-family: Arial, sans-serif; /* Clean, standard font */
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
  flex: 1; /* Pushes footer down */
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 40px; /* Space between boxes */
  max-width: 1200px;
  margin: 0 auto;
  padding: 40px 0;
}

.auth-section {
  flex: 1;
  max-width: 500px;
  display: flex;
  flex-direction: column;
}

/* CARDS - Solid and Opaque */
.auth-card {
  /* Slightly lighter solid background to distinguish card */
  background-color: #2a2e35;
  padding: 40px;
  border-radius: 8px; /* Regular slight rounded corners */
  border: 1px solid #3f444e; /* Added subtle border for definition */
  box-shadow: 0 4px 6px rgba(0,0,0,0.3); /* Standard shadow, no fancy glow */
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
  background-color: #1a1d21; /* Solid input background */
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

/* placeholder color */
.input-group input::placeholder {
  color: #888888;
}

.icon {
  color: #aaaaaa;
}

/* BUTTONS - Solid colors */
.btn {
  margin-top: 15px;
  padding: 12px;
  border: none;
  border-radius: 4px;
  font-weight: bold;
  cursor: pointer;
  font-size: 1rem;
}

.btn-login {
  background-color: #6366f1; /* Solid indigo */
  color: #ffffff;
}

.btn-login:hover {
  background-color: #4f46e5;
}

.btn-register {
  background-color: #22d3ee; /* Solid cyan */
  color: #111111;
}

.btn-register:hover {
  background-color: #06b6d4;
}

/* CONTEXT TEXT */
.forgot-password {
  margin-top: 20px;
  text-align: center;
  font-size: 0.9rem;
  color: #aaaaaa;
}

.registration-note {
  margin-top: 20px;
  font-size: 0.9rem;
  color: #aaaaaa;
  text-align: center;
  line-height: 1.4;
}

/* FOOTER NOTES */
.bottom-notes-section {
  padding: 30px 0;
  display: flex;
  justify-content: center;
}

.notes-container {
  /* Solid background for footer notes block */
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
@media (max-width: 768px) {
  .forms-wrapper {
    flex-direction: column;
    padding: 20px 0;
  }
}
</style>