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
  color: #00007e93;
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
  background-color: #ffffff;
  color: #5b6b7d;
  border: 1px solid #e8c604;
  border-radius: 4px;
  font-weight: bold;
  cursor: pointer;
  transition: all 0.2s ease;
}

.toggle-btn.active {
  background-color: #009ddbda;
  color: #00007e;
  border-color: #009ddb;
}

.toggle-btn:hover:not(.active) {
  background-color: #e8c604;
  color: #00007e;
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
  background-color: #ffffff;
  border: 1px solid #e8c604;
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
  color: #00007e;
  border-bottom: 1px solid #e8c604;
  padding-bottom: 8px;
}

.section-sub-title {
  font-size: 0.9rem;
  text-transform: uppercase;
  color: #00007e;
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
  background-color: #f5fafd;
  border: 1px solid #e8c604;
  padding: 10px 14px;
  border-radius: 4px;
  margin-bottom: 6px;
}

.info-label {
  color: #5b6b7d;
  font-size: 0.9rem;
}

.info-value {
  color: #00007e93;
  font-weight: bold;
  font-size: 0.9rem;
}

.invoice-link {
  color: #00007e;
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
  background-color: #dcfce7;
  color: #166534;
  border: 1px solid #16a34a;
}

.status-partial {
  background-color: #fdf6d3;
  color: #7a5c00;
  border: 1px solid #e8c604;
}

.status-unpaid {
  background-color: #fee2e2;
  color: #991b1b;
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
  background-color: #f5fafd;
  border: 1px solid #e8c604;
  padding: 14px 16px;
  border-radius: 6px;
  transition: all 0.2s ease;
}

.check-indicator {
  width: 24px;
  height: 24px;
  border-radius: 4px;
  background-color: #ffffff;
  border: 1px solid #e8c604;
  display: flex;
  justify-content: center;
  align-items: center;
  font-weight: bold;
  font-size: 0.9rem;
  color: #6b7c8d;
}

.checklist-label {
  color: #00007e93;
  font-size: 0.95rem;
}

/* COMPLETED CHECKLIST STYLING */
.checklist-item.completed {
  border-color: #16a34a;
}

.checklist-item.completed .check-indicator {
  background-color: #dcfce7;
  color: #166534;
  border-color: #16a34a;
}

.checklist-item.completed .checklist-label {
  color: #5b6b7d;
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