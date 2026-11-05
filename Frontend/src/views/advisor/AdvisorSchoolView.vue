<template>
  <div class="advisor-page">
    <!-- TOP VIEW TOGGLE BUTTONS -->
    <div class="toggle-container">
      <button 
        class="toggle-btn" 
        @click="switchView('/advisor/delegates')"
      >
        Delegates Overview
      </button>
      <button 
        class="toggle-btn active" 
        @click="switchView('/advisor/school')"
      >
        School Overview
      </button>
    </div>

    <!-- MAIN 50/50 TWO-COLUMN GRID -->
    <div class="overview-grid">
      <!-- LEFT COLUMN (STACKED PANELS) -->
      <div class="left-column">
        <!-- PANEL 1: SCHOOL & CONTACT INFO -->
        <section class="panel">
          <h2 class="panel-title">School & Contact Information</h2>
          
          <div class="info-section">
            <h3 class="section-sub-title">School Details</h3>
            <div class="info-row">
              <span class="info-label">School Name:</span>
              <span class="info-value">{{ school.name || 'N/A' }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Address:</span>
              <span class="info-value">{{ school.address || 'N/A' }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">City, State, ZIP:</span>
              <span class="info-value">
                {{ school.city }}, {{ school.state }} {{ school.zip }}
              </span>
            </div>
          </div>

          <div class="info-section">
            <h3 class="section-sub-title">Faculty Advisor</h3>
            <div class="info-row">
              <span class="info-label">Name:</span>
              <span class="info-value">{{ school.advisorName || 'N/A' }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Email:</span>
              <span class="info-value">{{ school.advisorEmail || 'N/A' }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Phone:</span>
              <span class="info-value">{{ school.advisorPhone || 'N/A' }}</span>
            </div>
          </div>

          <div class="info-section">
            <h3 class="section-sub-title">Head Delegate</h3>
            <div class="info-row">
              <span class="info-label">Name:</span>
              <span class="info-value">{{ school.headDelegateName || 'N/A' }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Email:</span>
              <span class="info-value">{{ school.headDelegateEmail || 'N/A' }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Phone:</span>
              <span class="info-value">{{ school.headDelegatePhone || 'N/A' }}</span>
            </div>
          </div>
        </section>

        <!-- PANEL 2: BILLING & PAYMENT -->
        <section class="panel">
          <h2 class="panel-title">Billing & Payment</h2>
          <div class="billing-content">
            <div class="info-row">
              <span class="info-label">Invoice Link:</span>
              <a 
                v-if="billing.invoiceUrl" 
                :href="billing.invoiceUrl" 
                target="_blank" 
                rel="noopener noreferrer" 
                class="invoice-link"
              >
                {{ billing.invoiceUrl }}
              </a>
              <span v-else class="info-value">No invoice available</span>
            </div>

            <div class="info-row">
              <span class="info-label">Payment Status:</span>
              <span :class="['status-badge', paymentStatusClass]">
                {{ (billing.paymentStatus || 'unpaid').toUpperCase() }}
              </span>
            </div>
          </div>
        </section>
      </div>

      <!-- RIGHT COLUMN (CHECKLIST PANEL) -->
      <div class="right-column">
        <section class="panel full-height-panel">
          <h2 class="panel-title">Conference Action Checklist</h2>
          
          <div class="checklist-container">
            <div 
              v-for="(item, index) in checklist" 
              :key="index" 
              :class="['checklist-item', { completed: item.completed }]"
            >
              <div class="check-indicator">
                <span v-if="item.completed">✓</span>
                <span v-else class="bullet-dot">•</span>
              </div>
              <span class="checklist-label">{{ item.label }}</span>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import apiClient from '@/api/client'
import { useToastStore } from '@/stores/toast'

const toastStore = useToastStore()
const router = useRouter()

// Reactive State
const school = ref({
  name: '',
  address: '',
  city: '',
  state: '',
  zip: '',
  advisorName: '',
  advisorEmail: '',
  advisorPhone: '',
  headDelegateName: '',
  headDelegateEmail: '',
  headDelegatePhone: ''
})

const billing = ref({
  invoiceUrl: '',
  paymentStatus: 'unpaid' // 'paid', 'partially paid', 'unpaid'
})

const checklist = ref([])

// Navigation Handler
const switchView = (path) => {
  router.push(path)
}

// Payment Status Badge Styling
const paymentStatusClass = computed(() => {
  switch (billing.value.paymentStatus?.toLowerCase()) {
    case 'paid':
      return 'status-paid'
    case 'partially paid':
      return 'status-partial'
    case 'unpaid':
    default:
      return 'status-unpaid'
  }
})

// Fetch initial data on mount
onMounted(async () => {
  try {
    const response = await apiClient.get('/advisor/school')
    const data = response.data || {}

    // Merge defensively so a partial payload still renders
    school.value = {
      name: data.school?.name || '',
      address: data.school?.address || '',
      city: data.school?.city || '',
      state: data.school?.state || '',
      zip: data.school?.zip || '',
      advisorName: data.school?.advisorName || '',
      advisorEmail: data.school?.advisorEmail || '',
      advisorPhone: data.school?.advisorPhone || '',
      headDelegateName: data.school?.headDelegateName || '',
      headDelegateEmail: data.school?.headDelegateEmail || '',
      headDelegatePhone: data.school?.headDelegatePhone || ''
    }

    billing.value = {
      invoiceUrl: data.billing?.invoiceUrl || '',
      paymentStatus: data.billing?.paymentStatus || 'unpaid'
    }

    checklist.value = data.checklist || []
  } catch (error) {
    // Backend errors are surfaced globally by the client.js toast interceptor
  }
})
</script>

<style scoped>
/* ============================================================ PAGE ====== */
/* Same white surface, navy ink and hairline rules as the login and delegate
   pages. Only presentation lives here - the fetch and the defensive merge above
   are untouched. */
.advisor-page {
  --ink: #03045e;
  --ink-2: #232d5c;
  --muted: #63708c;
  --line: rgba(3, 4, 94, 0.09);
  --accent: #009ddb;
  --green: #15803d;
  --gold: #7a5c00;
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

/* ============================================================ GRID ====== */
.overview-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--gap);
  align-items: start;
}

.left-column,
.right-column {
  display: flex;
  flex-direction: column;
  gap: var(--gap);
  min-width: 0;
}

/* =========================================================== PANELS ===== */
/* White cards on white: a hairline and one soft shadow carry the separation. */
.panel {
  display: flex;
  flex-direction: column;
  gap: clamp(9px, 1.3vh, 14px);
  padding: clamp(14px, 1.9vh, 20px) clamp(14px, 1.5vw, 22px);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.99), rgba(255, 255, 255, 0.92));
  box-shadow:
    0 1px 2px rgba(3, 4, 94, 0.04),
    0 24px 48px -38px rgba(3, 4, 94, 0.45);
  transition:
    border-color 0.35s ease,
    box-shadow 0.35s ease;
  animation: panel-in 0.8s var(--ease) both;
}

.panel:hover {
  border-color: rgba(3, 4, 94, 0.16);
  box-shadow:
    0 1px 2px rgba(3, 4, 94, 0.05),
    0 22px 44px -38px rgba(3, 4, 94, 0.35);
}

@keyframes panel-in {
  from {
    opacity: 0;
    transform: translate3d(0, 14px, 0);
  }
}

.panel-title {
  margin: 0;
  font-size: 1.04em;
  font-weight: 650;
  line-height: 1.25;
  letter-spacing: -0.005em;
  color: var(--ink);
}

.section-sub-title {
  margin: 0;
  font-size: 0.64em;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--muted);
}

.info-section,
.billing-content {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.info-section + .info-section {
  margin-top: 4px;
}

/* ============================================================== ROWS ===== */
.info-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 12px;
  border-radius: 11px;
  background-color: #f7fafd;
}

.info-label {
  flex: none;
  font-size: 0.66em;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
}

.info-value {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 0.84em;
  font-weight: 600;
  text-align: right;
  color: var(--ink);
  overflow-wrap: anywhere;
}

.invoice-link {
  font-size: 0.84em;
  font-weight: 600;
  text-align: right;
  color: #0079ab;
  text-decoration: none;
  word-break: break-all;
  transition: color 0.2s ease;
}

.invoice-link:hover {
  color: var(--accent);
  text-decoration: underline;
}

/* ============================================================ BADGES ===== */
.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 0.64em;
  font-weight: 700;
  letter-spacing: 0.09em;
  white-space: nowrap;
}

.status-paid {
  background-color: rgba(22, 163, 74, 0.1);
  color: var(--green);
}

.status-partial {
  background-color: rgba(232, 198, 4, 0.18);
  color: var(--gold);
}

.status-unpaid {
  border: 1px solid rgba(3, 4, 94, 0.1);
  background-color: #f2f4f8;
  color: var(--ink-2);
}

/* ========================================================= CHECKLIST ===== */
.checklist-container {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.checklist-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background-color: #f7fafd;
  transition:
    border-color 0.3s ease,
    background-color 0.3s ease,
    transform 0.3s var(--ease);
}

.checklist-item:hover {
  border-color: rgba(3, 4, 94, 0.14);
  transform: translateX(2px);
}

.check-indicator {
  flex: none;
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border: 1px solid var(--line);
  border-radius: 50%;
  background-color: #ffffff;
  color: var(--muted);
  font-size: 0.72em;
  font-weight: 700;
}

.checklist-label {
  font-size: 0.86em;
  color: var(--ink-2);
}

.bullet-dot {
  font-size: 0.9em;
  line-height: 1;
}

/* COMPLETED: a quiet green tick, the label settled back rather than shouted. */
.checklist-item.completed {
  border-color: rgba(22, 163, 74, 0.3);
  background-color: rgba(22, 163, 74, 0.05);
}

.checklist-item.completed .check-indicator {
  border-color: transparent;
  background-color: var(--green);
  color: #ffffff;
}

.checklist-item.completed .checklist-label {
  color: var(--muted);
  text-decoration: line-through;
}

/* ========================================================== RESPONSIVE === */
@media (max-width: 900px) {
  .overview-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .toggle-btn {
    flex: 1;
    min-width: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .panel {
    animation: none;
  }
}
</style>
