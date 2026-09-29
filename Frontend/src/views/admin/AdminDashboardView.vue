<template>
  <div class="admin-page">
    <header class="page-header">
      <h1>Admin Dashboard & Diagnostics</h1>
    </header>

    <!-- LOG & EXPORT ACTIONS -->
    <div class="section-card">
      <h2>Data & Log Exports</h2>
      <div class="action-buttons-grid">
        <button class="btn-action" @click="downloadFile('/api/admin/logs/business.txt', 'business-log.txt')">
          📄 Download Business Log (.txt)
        </button>
        <button class="btn-action" @click="downloadFile('/api/admin/logs/technology.txt', 'technology-log.txt')">
          🛠️ Download Technology Log (.txt)
        </button>
        <button class="btn-action btn-export" @click="downloadFile('/api/admin/export/database.csv', 'database-export.csv')">
          📊 Export Database (.csv)
        </button>
      </div>
    </div>

    <!-- METRICS GRID: DELEGATES & STORAGE -->
    <div class="metrics-grid">
      <!-- DELEGATE COUNTS -->
      <div class="section-card">
        <h2>Delegate Distribution</h2>
        <div class="total-badge">
          <span>Total Delegates</span>
          <strong>{{ totalDelegates }}</strong>
        </div>
        <div class="committee-list">
          <div 
            v-for="item in committeeCounts" 
            :key="item.committee" 
            class="committee-item"
          >
            <span class="committee-name">{{ item.committee }}</span>
            <span class="committee-count">{{ item.count }} delegates</span>
          </div>
        </div>
      </div>

      <!-- STORAGE CAPACITY -->
      <div class="section-card">
        <h2>Server Storage</h2>
        <div class="storage-info">
          <div class="storage-values">
            <span>Disk Space Used</span>
            <strong>{{ storage.usedGb }} GB / {{ storage.totalGb }} GB</strong>
          </div>
          <div class="progress-bar-bg">
            <div 
              class="progress-bar-fill" 
              :style="{ width: storagePercentage + '%' }"
              :class="{ warning: storagePercentage > 80 }"
            ></div>
          </div>
          <div class="percentage-label">{{ storagePercentage }}% capacity utilized</div>
        </div>
      </div>
    </div>

    <!-- PORT HEALTH MONITOR -->
    <div class="section-card">
      <div class="card-header-action">
        <h2>Port Health Monitor</h2>
        <button class="btn-refresh" :disabled="checkingPorts" @click="fetchPortHealth">
          {{ checkingPorts ? 'Checking...' : '🔄 Check Port Health' }}
        </button>
      </div>

      <div class="ports-grid">
        <div 
          v-for="port in ports" 
          :key="port.port" 
          :class="['port-card', port.status]"
        >
          <div class="port-info">
            <span class="port-name">{{ port.name }}</span>
            <span class="port-number">Port {{ port.port }}</span>
          </div>
          <span :class="['status-badge', port.status]">
            ● {{ port.status === 'healthy' ? 'Healthy' : 'Unreachable' }}
          </span>
        </div>
      </div>
    </div>

    <!-- DOWNTIME INCIDENT TIMELINE (PAST 7 DAYS) -->
    <div class="section-card">
      <h2>Server Downtime Log (Past 7 Days)</h2>
      <p class="section-desc">Recorded incidents where server health checks timed out or reported offline status.</p>

      <div v-if="downtimeEvents.length === 0" class="no-downtime">
        ✅ 100% Uptime — No downtime incidents recorded in the past 7 days.
      </div>

      <div v-else class="timeline-list">
        <div 
          v-for="event in downtimeEvents" 
          :key="event.id" 
          class="timeline-item"
        >
          <div class="timeline-dot"></div>
          <div class="timeline-content">
            <div class="timeline-time">
              <strong>{{ event.startTime }}</strong> to <strong>{{ event.endTime }}</strong>
            </div>
            <div class="timeline-details">
              <span class="duration-badge">Duration: {{ event.duration }}</span>
              <span class="reason-text">{{ event.reason }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import apiClient from '@/api/client'
import { useToastStore } from '@/stores/toast'

// Reactive State
const totalDelegates = ref(0)
const committeeCounts = ref([])
const storage = ref({ usedGb: 0, totalGb: 0 })
const ports = ref([])
const downtimeEvents = ref([])
const checkingPorts = ref(false)
const toastStore = useToastStore() // Assuming you have a global toast store for notifications

// Computed
const storagePercentage = computed(() => {
  if (!storage.value.totalGb) return 0
  return Number(((storage.value.usedGb / storage.value.totalGb) * 100).toFixed(1))
})

// 1. Refactored File Download Helper (Fetches secure files/logs via Axios)
const downloadFile = async (endpoint, fileName) => {
  try {
    const response = await apiClient.get(endpoint, {
      responseType: 'blob' // Essential for binary/text file downloads
    })

    // Create a temporary browser download link
    const blob = new Blob([response.data])
    const url = window.URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = fileName
    document.body.appendChild(anchor)
    anchor.click()
    document.body.removeChild(anchor)
    window.URL.revokeObjectURL(url)
  } catch (error) {
    toastStore.showToast(`Failed to download ${fileName}.`, 'error')
  }
}

// 2. Refactored Port Health Fetch (Real network ping endpoint)
const fetchPortHealth = async () => {
  checkingPorts.value = true

  try {
    const response = await apiClient.get('/admin/ports/health')
    ports.value = response.data
  } catch (error) {
    // Errors automatically pop up via global toast interceptor
  } finally {
    checkingPorts.value = false
  }
}

// Fetch Initial Dashboard Data
onMounted(async () => {
  try {
    // 2. Fetch system overview data from your API
    const response = await apiClient.get('/admin/dashboard-stats')
    
    // 3. Assign the backend data directly to your reactive refs
    totalDelegates.value = response.data.totalDelegates
    committeeCounts.value = response.data.committeeCounts
    storage.value = response.data.storage
    downtimeEvents.value = response.data.downtimeEvents

    // Existing port fetch
    await fetchPortHealth()
  } catch (error) {
    // Backend errors will automatically pop up via your global toast store!
  }
})
</script>

<style scoped>
.admin-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
  color: #ffffff;
  font-family: Arial, sans-serif;
}

.page-header h1 {
  margin: 0;
  font-size: 1.5rem;
  color: #ffffff;
}

/* SECTION CARDS */
.section-card {
  background-color: #2a2e35;
  border: 1px solid #3f444e;
  border-radius: 8px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.section-card h2 {
  margin: 0;
  font-size: 1.1rem;
  color: #ffffff;
}

.section-desc {
  margin: 0;
  font-size: 0.85rem;
  color: #aaaaaa;
}

.card-header-action {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* BUTTONS & EXPORTS */
.action-buttons-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.btn-action {
  background-color: #1a1d21;
  color: #ffffff;
  border: 1px solid #3f444e;
  padding: 12px;
  border-radius: 6px;
  font-weight: bold;
  font-size: 0.9rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-action:hover {
  background-color: #3f444e;
}

.btn-export {
  border-color: #22c55e;
  color: #86efac;
}

.btn-export:hover {
  background-color: #14532d;
}

.btn-refresh {
  background-color: #6366f1;
  color: #ffffff;
  border: none;
  padding: 8px 14px;
  border-radius: 4px;
  font-weight: bold;
  cursor: pointer;
}

.btn-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* METRICS GRID */
.metrics-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.total-badge {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: #1a1d21;
  padding: 12px 16px;
  border-radius: 6px;
  font-size: 1rem;
}

.total-badge strong {
  color: #22d3ee;
  font-size: 1.3rem;
}

.committee-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.committee-item {
  display: flex;
  justify-content: space-between;
  font-size: 0.85rem;
  padding: 6px 10px;
  background-color: #1a1d21;
  border-radius: 4px;
}

.committee-name {
  color: #aaaaaa;
}

.committee-count {
  font-weight: bold;
}

/* STORAGE BAR */
.storage-info {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.storage-values {
  display: flex;
  justify-content: space-between;
  font-size: 0.9rem;
}

.progress-bar-bg {
  background-color: #1a1d21;
  height: 16px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #3f444e;
}

.progress-bar-fill {
  height: 100%;
  background-color: #22c55e;
  transition: width 0.4s ease;
}

.progress-bar-fill.warning {
  background-color: #f59e0b;
}

.percentage-label {
  font-size: 0.8rem;
  color: #aaaaaa;
  text-align: right;
}

/* PORTS GRID */
.ports-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.port-card {
  background-color: #1a1d21;
  border: 1px solid #3f444e;
  border-radius: 6px;
  padding: 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.port-card.unreachable {
  border-color: #ef4444;
}

.port-info {
  display: flex;
  flex-direction: column;
}

.port-name {
  font-weight: bold;
  font-size: 0.9rem;
}

.port-number {
  font-size: 0.75rem;
  color: #888888;
}

.status-badge {
  font-size: 0.8rem;
  font-weight: bold;
  padding: 4px 8px;
  border-radius: 4px;
}

.status-badge.healthy {
  color: #86efac;
  background-color: #14532d;
}

.status-badge.unreachable {
  color: #fca5a5;
  background-color: #7f1d1d;
}

/* DOWNTIME TIMELINE */
.no-downtime {
  background-color: #14532d;
  color: #86efac;
  padding: 12px;
  border-radius: 6px;
  font-size: 0.9rem;
  font-weight: bold;
}

.timeline-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.timeline-item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  background-color: #1a1d21;
  padding: 12px;
  border-radius: 6px;
  border-left: 4px solid #ef4444;
}

.timeline-dot {
  width: 10px;
  height: 10px;
  background-color: #ef4444;
  border-radius: 50%;
  margin-top: 4px;
}

.timeline-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.85rem;
}

.timeline-details {
  display: flex;
  gap: 10px;
  align-items: center;
}

.duration-badge {
  background-color: #7f1d1d;
  color: #fca5a5;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 0.75rem;
  font-weight: bold;
}

.reason-text {
  color: #aaaaaa;
}

@media (max-width: 900px) {
  .action-buttons-grid,
  .metrics-grid,
  .ports-grid {
    grid-template-columns: 1fr;
  }
}
</style>