<template>
  <div class="advisor-page">
    <!-- TOP VIEW TOGGLE BUTTONS -->
    <div class="toggle-container">
    <button 
      class="toggle-btn active" 
      @click="switchView('advisor-roster')"
    >
      Delegates Overview
    </button>
    <button 
      class="toggle-btn" 
      @click="switchView('school-overview')"
    >
      School Overview
    </button>
    </div>

    <!-- STATS SUMMARY -->
    <div class="stats-bar">
      <span>Total Delegates: <strong>{{ totalDelegates }}</strong></span>
    </div>

    <!-- DELEGATE LIST CONTAINER -->
    <div class="list-container">
      <!-- COLUMN HEADER LABELS -->
      <div class="table-headers">
        <span class="header-col">Assignment</span>
        <span class="header-col">Position Paper Status</span>
        <span class="header-col">Position Paper Grade</span>
        <span class="header-col">Delegate Hash</span>
        <span class="header-col">Registration Status</span>
        <span class="header-col">Action</span>
      </div>

      <!-- DELEGATE ROWS / BOXES -->
      <div 
        v-for="delegate in delegates" 
        :key="delegate.id" 
        class="delegate-box"
      >
        <!-- Assignment -->
        <div class="col-cell">
          <strong class="primary-text">{{ delegate.country }}</strong>
          <span class="sub-text">{{ delegate.committee }}</span>
        </div>

        <!-- Position Paper Status -->
        <div class="col-cell">
          <span :class="['status-badge', getStatusClass(delegate.paperStatus)]">
            {{ delegate.paperStatus.toUpperCase() }}
          </span>
        </div>

        <!-- Position Paper Grade -->
        <div class="col-cell">
          <span class="grade-text">{{ delegate.paperGrade || 'N/A' }}</span>
        </div>

        <!-- Delegate Hash -->
        <div class="col-cell">
          <code class="hash-text">
            {{ hashesRevealed ? delegate.hash : '••••••••' }}
          </code>
        </div>

        <!-- Registration Status -->
        <div class="col-cell">
          <span :class="['reg-badge', delegate.registered ? 'reg-yes' : 'reg-no']">
            {{ delegate.registered ? 'Registered' : 'Pending' }}
          </span>
        </div>

        <!-- Action / Download Button -->
        <div class="col-cell">
          <button 
            class="btn-download" 
            :disabled="delegate.paperStatus === 'unsubmitted'"
            @click="downloadPaper(delegate.id)"
          >
            Download PDF
          </button>
        </div>
      </div>
    </div>

    <!-- BOTTOM HASH REVEAL ACTION -->
    <div class="bottom-actions">
      <button 
        v-if="!hashesRevealed" 
        class="btn-reveal" 
        @click="showPasswordModal = true"
      >
        Reveal All Hashes
      </button>
      <span v-else class="revealed-notice">
        ✓ Confidential hashes unlocked for session.
      </span>
    </div>

    <!-- PASSWORD VERIFICATION MODAL -->
    <div v-if="showPasswordModal" class="modal-overlay">
      <div class="modal-card">
        <h3>Security Verification</h3>
        <p>Re-enter your password to view delegate hashes.</p>
        
        <input 
          type="password" 
          v-model="passwordInput" 
          placeholder="Advisor Password"
          @keyup.enter="verifyPasswordAndReveal"
        />

        <p v-if="errorMessage" class="error-msg">{{ errorMessage }}</p>

        <div class="modal-buttons">
          <button class="btn-confirm" @click="verifyPasswordAndReveal">Confirm</button>
          <button class="btn-cancel" @click="closeModal">Cancel</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import apiClient from '@/api/client'
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useToastStore } from '@/stores/toast'

const router = useRouter()
const toastStore = useToastStore()

// Reactive State
const totalDelegates = ref(0)
const delegates = ref([])
const hashesRevealed = ref(false)

// Modal State
const showPasswordModal = ref(false)
const passwordInput = ref('')
const errorMessage = ref('')

// Navigation toggle
const switchView = (routeName) => {
  router.push({ name: routeName })
}

// Map paper status to badge colors
const getStatusClass = (status) => {
  switch (status) {
    case 'submitted':
      return 'status-submitted'
    case 'graded':
      return 'status-graded'
    case 'unsubmitted':
    default:
      return 'status-unsubmitted'
  }
}

// 1. Refactored Paper Download Handler
const downloadPaper = async (delegateId) => {
  try {
    const response = await apiClient.get(`/advisor/delegates/${delegateId}/paper`, {
      responseType: 'blob' // Required for PDF/file download
    })

    const blob = new Blob([response.data], { type: 'application/pdf' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `delegate_${delegateId}_paper.pdf`)
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  } catch (err) {
    toastStore.showToast('Failed to download position paper.', 'error')
  }
}

// 2. Refactored Password Verification & Hash Unlocking
const verifyPasswordAndReveal = async () => {
  if (!passwordInput.value) {
    errorMessage.value = 'Password is required.'
    return
  }

  try {
    // Send password to unlock decrypted delegate hashes
    const response = await apiClient.post('/advisor/verify-hashes', {
      password: passwordInput.value
    })

    // Update delegates list with returned unmasked hashes
    delegates.value = response.data.delegates
    hashesRevealed.value = true
    toastStore.showToast('Delegate hashes revealed successfully.', 'success')
    closeModal()
  } catch (err) {
    errorMessage.value = err.response?.data?.message || 'Incorrect password. Access denied.'
  }
}

const closeModal = () => {
  showPasswordModal.value = false
  passwordInput.value = ''
  errorMessage.value = ''
}

// 3. Refactored Initial Data Fetch on Mount
onMounted(async () => {
  try {
    const response = await apiClient.get('/advisor/delegates')
    delegates.value = response.data.delegates
    totalDelegates.value = response.data.total
  } catch (err) {
    // Global toast interceptor handles network/server errors automatically
  }
})
</script>

<style scoped>
.advisor-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
  color: #ffffff;
  font-family: Arial, sans-serif;
}

/* TOP TOGGLE BUTTONS */
.toggle-container {
  display: flex;
  justify-content: center;
  gap: 15px;
}

.toggle-btn {
  width: 240px;
  height: 40px;
  background-color: #2a2e35;
  color: #aaaaaa;
  border: 1px solid #3f444e;
  border-radius: 4px;
  font-weight: bold;
  cursor: pointer;
  transition: all 0.2s ease;
}

.toggle-btn.active {
  background-color: #6366f1;
  color: #ffffff;
  border-color: #6366f1;
}

.toggle-btn:hover:not(.active) {
  background-color: #3f444e;
  color: #ffffff;
}

/* STATS BAR */
.stats-bar {
  background-color: #2a2e35;
  border: 1px solid #3f444e;
  border-radius: 4px;
  padding: 12px 20px;
  font-size: 0.95rem;
  color: #cccccc;
}

.stats-bar strong {
  color: #22d3ee;
}

/* LIST & TABLE HEADERS */
.list-container {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.table-headers {
  display: grid;
  grid-template-columns: 1.5fr 1.2fr 1fr 1fr 1fr 1.2fr;
  padding: 0 20px;
  gap: 10px;
}

.header-col {
  font-size: 0.85rem;
  font-weight: bold;
  color: #888888;
  text-transform: uppercase;
}

/* DELEGATE BOX (ROW) */
.delegate-box {
  background-color: #2a2e35;
  border: 1px solid #3f444e;
  border-radius: 6px;
  padding: 15px 20px;
  display: grid;
  grid-template-columns: 1.5fr 1.2fr 1fr 1fr 1fr 1.2fr;
  align-items: center;
  gap: 10px;
}

.col-cell {
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.primary-text {
  color: #ffffff;
  font-size: 1rem;
}

.sub-text {
  color: #aaaaaa;
  font-size: 0.85rem;
}

.grade-text {
  color: #ffffff;
  font-weight: bold;
}

.hash-text {
  font-family: monospace;
  background-color: #1a1d21;
  padding: 4px 8px;
  border-radius: 4px;
  border: 1px solid #3f444e;
  width: fit-content;
  color: #22d3ee;
}

/* BADGES */
.status-badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-weight: bold;
  font-size: 0.75rem;
  width: fit-content;
}

.status-unsubmitted {
  background-color: #7f1d1d;
  color: #fca5a5;
  border: 1px solid #ef4444;
}

.status-submitted {
  background-color: #78350f;
  color: #fcd34d;
  border: 1px solid #f59e0b;
}

.status-graded {
  background-color: #14532d;
  color: #86efac;
  border: 1px solid #22c55e;
}

.reg-badge {
  font-size: 0.85rem;
  font-weight: bold;
}

.reg-yes {
  color: #22c55e;
}

.reg-no {
  color: #ef4444;
}

/* BUTTONS */
.btn-download {
  background-color: #1a1d21;
  color: #ffffff;
  border: 1px solid #3f444e;
  padding: 8px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: bold;
}

.btn-download:hover:not(:disabled) {
  background-color: #6366f1;
  border-color: #6366f1;
}

.btn-download:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.bottom-actions {
  display: flex;
  justify-content: center;
  margin-top: 10px;
}

.btn-reveal {
  background-color: #22d3ee;
  color: #111111;
  border: none;
  padding: 10px 24px;
  border-radius: 4px;
  font-weight: bold;
  cursor: pointer;
}

.btn-reveal:hover {
  background-color: #06b6d4;
}

.revealed-notice {
  color: #22c55e;
  font-weight: bold;
}

/* MODAL */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background-color: rgba(0, 0, 0, 0.7);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 100;
}

.modal-card {
  background-color: #2a2e35;
  border: 1px solid #3f444e;
  border-radius: 8px;
  padding: 30px;
  width: 100%;
  max-width: 400px;
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.modal-card h3 {
  margin: 0;
  color: #ffffff;
}

.modal-card p {
  margin: 0;
  color: #aaaaaa;
  font-size: 0.9rem;
}

.modal-card input {
  background-color: #1a1d21;
  border: 1px solid #3f444e;
  color: #ffffff;
  padding: 10px;
  border-radius: 4px;
}

.error-msg {
  color: #ef4444 !important;
  font-size: 0.85rem !important;
}

.modal-buttons {
  display: flex;
  gap: 10px;
}

.btn-confirm {
  flex: 1;
  background-color: #6366f1;
  color: #ffffff;
  border: none;
  padding: 10px;
  border-radius: 4px;
  font-weight: bold;
  cursor: pointer;
}

.btn-cancel {
  flex: 1;
  background-color: #1a1d21;
  color: #ffffff;
  border: 1px solid #3f444e;
  padding: 10px;
  border-radius: 4px;
  cursor: pointer;
}

/* RESPONSIVE */
@media (max-width: 900px) {
  .table-headers {
    display: none;
  }

  .delegate-box {
    grid-template-columns: 1fr;
    gap: 15px;
  }
}
</style>