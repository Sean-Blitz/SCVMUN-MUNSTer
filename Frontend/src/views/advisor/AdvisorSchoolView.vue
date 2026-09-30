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

/* 50/50 TWO-COLUMN GRID */
.overview-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.left-column {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.right-column {
  display: flex;
  flex-direction: column;
}

/* PANELS */
.panel {
  background-color: #2a2e35;
  border: 1px solid #3f444e;
  border-radius: 8px;
  padding: 20px;
  display: flex;
  flex-direction: column;
}

.full-height-panel {
  height: 100%;
}

.panel-title {
  font-size: 1.1rem;
  font-weight: bold;
  margin-top: 0;
  margin-bottom: 15px;
  color: #ffffff;
  border-bottom: 1px solid #3f444e;
  padding-bottom: 8px;
}

.section-sub-title {
  font-size: 0.9rem;
  text-transform: uppercase;
  color: #22d3ee;
  margin: 15px 0 8px 0;
}

.info-section:first-of-type .section-sub-title {
  margin-top: 0;
}

/* ROWS AND DATA */
.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: #1a1d21;
  border: 1px solid #3f444e;
  padding: 10px 14px;
  border-radius: 4px;
  margin-bottom: 6px;
}

.info-label {
  color: #aaaaaa;
  font-size: 0.9rem;
}

.info-value {
  color: #ffffff;
  font-weight: bold;
  font-size: 0.9rem;
}

.invoice-link {
  color: #22d3ee;
  text-decoration: none;
  font-size: 0.9rem;
  word-break: break-all;
}

.invoice-link:hover {
  text-decoration: underline;
}

/* STATUS BADGES */
.status-badge {
  padding: 4px 10px;
  border-radius: 4px;
  font-weight: bold;
  font-size: 0.8rem;
}

.status-paid {
  background-color: #14532d;
  color: #86efac;
  border: 1px solid #22c55e;
}

.status-partial {
  background-color: #78350f;
  color: #fcd34d;
  border: 1px solid #f59e0b;
}

.status-unpaid {
  background-color: #7f1d1d;
  color: #fca5a5;
  border: 1px solid #ef4444;
}

/* CHECKLIST */
.checklist-container {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.checklist-item {
  display: flex;
  align-items: center;
  gap: 12px;
  background-color: #1a1d21;
  border: 1px solid #3f444e;
  padding: 14px 16px;
  border-radius: 6px;
  transition: all 0.2s ease;
}

.check-indicator {
  width: 24px;
  height: 24px;
  border-radius: 4px;
  background-color: #2a2e35;
  border: 1px solid #3f444e;
  display: flex;
  justify-content: center;
  align-items: center;
  font-weight: bold;
  font-size: 0.9rem;
  color: #888888;
}

.checklist-label {
  color: #ffffff;
  font-size: 0.95rem;
}

/* COMPLETED CHECKLIST STYLING */
.checklist-item.completed {
  border-color: #22c55e;
}

.checklist-item.completed .check-indicator {
  background-color: #14532d;
  color: #86efac;
  border-color: #22c55e;
}

.checklist-item.completed .checklist-label {
  color: #aaaaaa;
  text-decoration: line-through;
}

.bullet-dot {
  font-size: 1.2rem;
  line-height: 1;
}

/* RESPONSIVE */
@media (max-width: 900px) {
  .overview-grid {
    grid-template-columns: 1fr;
  }
}
</style>