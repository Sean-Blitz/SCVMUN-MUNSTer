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
/* ============================================================ PAGE ====== */
/* The same white surface, navy ink and hairline rules as the login and delegate
   pages, so every role's portal reads as one product. Nothing here touches the
   data: only colour, spacing, radius and shadow are set. */
.advisor-page {
  --ink: #03045e;
  --ink-2: #232d5c;
  --muted: #63708c;
  --line: rgba(3, 4, 94, 0.09);
  --accent: #009ddb;
  --green: #15803d;
  --red: #b42318;
  --gap: clamp(12px, 1.6vh, 18px);
  --radius: 16px;
  --ease: cubic-bezier(0.22, 1, 0.36, 1);
  --font:
    'Inter', -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto,
    'Helvetica Neue', Arial, sans-serif;

  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: var(--gap);
  width: 100%;
  max-width: 1240px;
  margin: 0 auto;
  padding: clamp(14px, 2.1vh, 24px) clamp(16px, 2.4vw, 34px);
  color: var(--muted);
  font-family: var(--font);
  font-size: clamp(0.85rem, 1.6vh, 1rem);
  line-height: 1.5;
  letter-spacing: 0.005em;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  background: #ffffff;
}

/* =========================================================== TOGGLE ===== */
/* Segmented pills: the page in view carries the navy weight, the other stays a
   quiet outline, exactly like the primary/secondary pairing on the login page. */
.toggle-container {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
}

.toggle-btn {
  min-width: 210px;
  padding: 10px 22px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background-color: #ffffff;
  color: var(--muted);
  font-family: inherit;
  font-size: 0.76em;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  cursor: pointer;
  transition:
    background-color 0.25s ease,
    border-color 0.25s ease,
    color 0.25s ease,
    transform 0.25s var(--ease);
}

.toggle-btn:hover:not(.active) {
  border-color: rgba(3, 4, 94, 0.18);
  color: var(--ink);
  transform: translateY(-1px);
}

.toggle-btn.active {
  border-color: var(--ink);
  background-color: var(--ink);
  color: #ffffff;
}

/* ============================================================= STATS ===== */
.stats-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 11px 16px;
  border: 1px solid var(--line);
  border-left: 3px solid var(--ink);
  border-radius: 14px;
  background-color: #ffffff;
  box-shadow: 0 1px 2px rgba(3, 4, 94, 0.04);
  font-size: 0.72em;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--muted);
}

.stats-bar strong {
  color: var(--ink);
  font-size: 1.35em;
  letter-spacing: 0;
  font-variant-numeric: tabular-nums;
}

/* ============================================================== LIST ===== */
.list-container {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.table-headers {
  display: grid;
  grid-template-columns: 1.5fr 1.2fr 1fr 1fr 1fr 1.2fr;
  gap: 10px;
  padding: 0 18px;
}

.header-col {
  font-size: 0.66em;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--muted);
}

/* ROWS: white cards on white, separated by a hairline and one soft shadow. */
.delegate-box {
  display: grid;
  grid-template-columns: 1.5fr 1.2fr 1fr 1fr 1fr 1.2fr;
  align-items: center;
  gap: 10px;
  padding: 14px 18px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.99), rgba(255, 255, 255, 0.92));
  box-shadow:
    0 1px 2px rgba(3, 4, 94, 0.04),
    0 20px 40px -38px rgba(3, 4, 94, 0.45);
  transition:
    border-color 0.3s ease,
    box-shadow 0.3s ease,
    transform 0.3s var(--ease);
  animation: row-in 0.7s var(--ease) both;
}

.delegate-box:hover {
  border-color: rgba(3, 4, 94, 0.16);
  transform: translateY(-1px);
  box-shadow:
    0 1px 2px rgba(3, 4, 94, 0.05),
    0 22px 44px -38px rgba(3, 4, 94, 0.35);
}

@keyframes row-in {
  from {
    opacity: 0;
    transform: translate3d(0, 10px, 0);
  }
}

.col-cell {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-width: 0;
}

.primary-text {
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--ink);
  font-size: 0.9em;
  font-weight: 650;
}

.sub-text {
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--muted);
  font-size: 0.78em;
}

.grade-text {
  color: var(--ink);
  font-size: 0.86em;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}

.hash-text {
  width: fit-content;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  padding: 4px 9px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background-color: #f7fafd;
  color: var(--ink-2);
  font-family: 'SFMono-Regular', ui-monospace, Menlo, Consolas, monospace;
  font-size: 0.74em;
  letter-spacing: 0.04em;
}

/* ============================================================ BADGES ===== */
.status-badge {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 0.64em;
  font-weight: 700;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  white-space: nowrap;
}

/* Nothing submitted yet is the resting state, not a problem: plain ink on a hairline. */
.status-unsubmitted {
  border: 1px solid var(--line);
  background-color: transparent;
  color: var(--muted);
}

.status-submitted {
  border: 1px solid rgba(3, 4, 94, 0.1);
  background-color: #f2f4f8;
  color: var(--ink-2);
}

.status-graded {
  background-color: rgba(22, 163, 74, 0.1);
  color: var(--green);
}

.reg-badge {
  font-size: 0.66em;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.reg-yes {
  color: var(--green);
}

.reg-no {
  color: var(--muted);
}

/* =========================================================== BUTTONS ===== */
.btn-download {
  padding: 7px 13px;
  border: 1px solid rgba(0, 157, 219, 0.4);
  border-radius: 9px;
  background-color: #ffffff;
  color: #0079ab;
  font-family: inherit;
  font-size: 0.72em;
  font-weight: 650;
  cursor: pointer;
  transition:
    background-color 0.25s ease,
    border-color 0.25s ease,
    transform 0.25s var(--ease),
    box-shadow 0.25s ease;
}

.btn-download:hover:not(:disabled) {
  border-color: var(--accent);
  background-color: #f2f9fe;
  transform: translateY(-1px);
  box-shadow: 0 10px 20px -16px rgba(0, 121, 171, 0.9);
}

.btn-download:disabled {
  border-color: rgba(3, 4, 94, 0.12);
  color: #9aa5b1;
  cursor: not-allowed;
}

.bottom-actions {
  display: flex;
  justify-content: center;
  margin-top: 6px;
}

.btn-reveal {
  padding: 11px 22px;
  border: 0;
  border-radius: 999px;
  background-color: var(--ink);
  color: #ffffff;
  font-family: inherit;
  font-size: 0.72em;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  cursor: pointer;
  box-shadow: 0 12px 24px -18px rgba(3, 4, 94, 0.9);
  transition:
    background-color 0.25s ease,
    transform 0.25s var(--ease),
    box-shadow 0.25s ease;
}

.btn-reveal:hover {
  background-color: #071f7a;
  transform: translateY(-1px);
  box-shadow: 0 16px 28px -18px rgba(3, 4, 94, 0.9);
}

.btn-reveal:active {
  transform: translateY(0) scale(0.99);
}

.revealed-notice {
  display: inline-flex;
  align-items: center;
  padding: 7px 15px;
  border-radius: 999px;
  background-color: rgba(22, 163, 74, 0.1);
  color: var(--green);
  font-size: 0.7em;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

/* ============================================================= MODAL ===== */
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 20px;
  background-color: rgba(3, 4, 94, 0.45);
  backdrop-filter: blur(2px);
}

.modal-card {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
  max-width: 400px;
  padding: 28px;
  border: 1px solid var(--line);
  border-radius: 18px;
  background-color: #ffffff;
  box-shadow: 0 40px 80px -40px rgba(3, 4, 94, 0.6);
  animation: modal-in 0.45s var(--ease) both;
}

@keyframes modal-in {
  from {
    opacity: 0;
    transform: translate3d(0, 12px, 0) scale(0.98);
  }
}

.modal-card h3 {
  margin: 0;
  font-size: 1.06em;
  font-weight: 650;
  letter-spacing: -0.005em;
  color: var(--ink);
}

.modal-card p {
  margin: 0;
  font-size: 0.84em;
  line-height: 1.55;
  color: var(--muted);
}

/* Underline field, the same treatment the login inputs use. */
.modal-card input {
  width: 100%;
  box-sizing: border-box;
  padding: 10px 2px;
  border: none;
  border-bottom: 1px solid var(--line);
  border-radius: 0;
  background: transparent;
  color: var(--ink);
  font-family: inherit;
  font-size: 0.95em;
  letter-spacing: 0.01em;
  transition: border-color 0.2s ease;
}

.modal-card input:focus {
  outline: none;
  border-bottom-color: #023e8a;
}

.modal-card input::placeholder {
  color: rgba(3, 4, 94, 0.45);
}

.error-msg {
  color: var(--red) !important;
  font-size: 0.8em !important;
}

.modal-buttons {
  display: flex;
  gap: 10px;
  margin-top: 4px;
}

.btn-confirm {
  flex: 1;
  padding: 11px;
  border: 0;
  border-radius: 10px;
  background-color: var(--ink);
  color: #ffffff;
  font-family: inherit;
  font-size: 0.74em;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  cursor: pointer;
  transition:
    background-color 0.25s ease,
    transform 0.25s var(--ease);
}

.btn-confirm:hover {
  background-color: #071f7a;
  transform: translateY(-1px);
}

.btn-cancel {
  flex: 1;
  padding: 11px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background-color: #ffffff;
  color: var(--ink-2);
  font-family: inherit;
  font-size: 0.74em;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  cursor: pointer;
  transition:
    border-color 0.25s ease,
    color 0.25s ease;
}

.btn-cancel:hover {
  border-color: rgba(3, 4, 94, 0.2);
  color: var(--ink);
}

/* ========================================================== RESPONSIVE === */
@media (max-width: 900px) {
  .table-headers {
    display: none;
  }

  .delegate-box {
    grid-template-columns: 1fr;
    gap: 12px;
  }

  .col-cell {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }

  .toggle-btn {
    flex: 1;
    min-width: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .delegate-box,
  .modal-card {
    animation: none;
  }
}
</style>
