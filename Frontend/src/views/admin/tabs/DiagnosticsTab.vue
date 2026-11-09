<template>
<!-- LOG & EXPORT ACTIONS -->
<div class="section-card">
  <h2>Data & Log Exports</h2>
  <div class="action-buttons-grid">
    <button class="btn-action" @click="downloadFile('/admin/logs/business.txt', 'business-log.txt')">
      <AppIcon name="file" :size="17" />
      <span>Download Business Log (.txt)</span>
    </button>
    <button class="btn-action" @click="downloadFile('/admin/logs/technology.txt', 'technology-log.txt')">
      <AppIcon name="tools" :size="17" />
      <span>Download Technology Log (.txt)</span>
    </button>
    <button class="btn-action btn-export" @click="downloadFile('/admin/export/database.csv', 'database-export.csv')">
      <AppIcon name="chart" :size="17" />
      <span>Export Database (.csv)</span>
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
      <AppIcon name="refresh" />
      <span>{{ checkingPorts ? 'Checking...' : 'Check Port Health' }}</span>
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
    <AppIcon name="check" />
    <span>100% Uptime — No downtime incidents recorded in the past 7 days.</span>
  </div>

  <template v-else>
    <!-- Only the most recent incidents are rendered: this is a read of the log, not the
         log itself, which stays complete on disk and in the downloadable copy. -->
    <p v-if="hiddenDowntimeCount > 0" class="downtime-note">
      Showing the {{ DOWNTIME_DISPLAY_LIMIT }} most recent of
      {{ downtimeEvents.length }} incidents recorded in the past 7 days.
    </p>

    <div class="timeline-list">
      <div
        v-for="event in visibleDowntimeEvents"
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
  </template>
</div>
</template>

<script setup>
import AppIcon from '@/components/AppIcon.vue'
import { computed, onMounted, ref } from 'vue'
import apiClient from '@/api/client'
import { useToastStore } from '@/stores/toast'

const toastStore = useToastStore()

// ---------- Diagnostics state ----------
const totalDelegates = ref(0)
const committeeCounts = ref([])
const storage = ref({ usedGb: 0, totalGb: 0 })
const ports = ref([])
const downtimeEvents = ref([])
const checkingPorts = ref(false)

// How many incidents the timeline renders. The API returns the whole 7-day window newest
// first (core.monitor.recent_outages reverses the log), so the first N are the last N.
// This is a display limit only: downtime.log keeps every incident, and the download in the
// card above still contains all of them.
const DOWNTIME_DISPLAY_LIMIT = 10

const visibleDowntimeEvents = computed(() =>
  downtimeEvents.value.slice(0, DOWNTIME_DISPLAY_LIMIT)
)

const hiddenDowntimeCount = computed(() =>
  Math.max(0, downtimeEvents.value.length - DOWNTIME_DISPLAY_LIMIT)
)

const storagePercentage = computed(() => {
  if (!storage.value.totalGb) return 0
  return Number(((storage.value.usedGb / storage.value.totalGb) * 100).toFixed(1))
})

// ---------- Diagnostics helpers ----------
// Fetches secure files/logs as a blob and hands them to the browser as a download.
const downloadFile = async (endpoint, fileName) => {
  try {
    const response = await apiClient.get(endpoint, {
      responseType: 'blob' // Essential for binary/text file downloads
    })

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

// Loaded once, not on every tab entry: the stats only change when the data does, and the
// port check already has its own button.
onMounted(async () => {
  try {
    const response = await apiClient.get('/admin/dashboard-stats')

    totalDelegates.value = response.data.totalDelegates
    committeeCounts.value = response.data.committeeCounts
    storage.value = response.data.storage
    downtimeEvents.value = response.data.downtimeEvents

    await fetchPortHealth()
  } catch (error) {
    // Backend errors will automatically pop up via your global toast store!
  }
})

</script>
