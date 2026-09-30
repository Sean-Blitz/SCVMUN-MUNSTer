<template>
  <div class="delegate-page">
    <!-- ANNOUNCEMENT BAR -->
    <div v-if="dashboardData.announcements.length" class="announcement-bar">
      <span class="announcement-label">ANNOUNCEMENT:</span>
      <span class="announcement-text">{{ dashboardData.announcements[0] }}</span>
    </div>

    <!-- MAIN TOP GRID (GENERAL INFO & DELEGATE INFO) -->
    <div class="top-grid">
      <!-- CONFERENCE / GENERAL INFO PANEL -->
      <section class="panel">
        <h2 class="panel-title">Conference & General Info</h2>
        <div class="links-container">
          <div 
            v-for="(link, index) in formattedLinks" 
            :key="index" 
            class="link-box"
          >
            <a 
              v-if="link.url && link.text" 
              :href="link.url" 
              target="_blank" 
              rel="noopener noreferrer"
            >
              {{ link.text }}: {{ link.url }}
            </a>
          </div>
        </div>
      </section>

      <!-- DELEGATE INFO PANEL -->
      <section class="panel">
        <h2 class="panel-title">Delegate Information</h2>
        <div class="info-content">
          <div class="info-row">
            <span class="info-label">Committee:</span>
            <span class="info-value">{{ dashboardData.delegate.committee || 'Unassigned' }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">Country Assignment:</span>
            <span class="info-value">{{ dashboardData.delegate.country || 'Unassigned' }}</span>
          </div>
        </div>
      </section>
    </div>

    <!-- WIDE POSITION PAPER PANEL -->
    <section class="panel paper-panel">
      <h2 class="panel-title">Position Paper Submission</h2>

      <!-- INSTRUCTIONS LIST -->
      <div v-if="dashboardData.positionPaper.instructions.length" class="instructions-block">
        <ol class="instructions-list">
          <li 
            v-for="(instruction, index) in dashboardData.positionPaper.instructions" 
            :key="index"
          >
            {{ instruction }}
          </li>
        </ol>
      </div>

      <!-- STATUS DISPLAY -->
      <div class="status-block">
        <span class="status-label">Current Status:</span>
        <span :class="['status-badge', statusClass]">
          {{ dashboardData.positionPaper.status.toUpperCase() }}
        </span>
      </div>

      <!-- GRADED DETAILS (SCORE & FEEDBACK) -->
      <div 
        v-if="dashboardData.positionPaper.status === 'graded'" 
        class="grading-block"
      >
        <div class="score-row">
          <span>Score:</span>
          <strong class="score-value">{{ dashboardData.positionPaper.score }}</strong>
        </div>
        <div class="feedback-box">
          <p class="feedback-title">Chair Comments:</p>
          <p class="feedback-text">{{ dashboardData.positionPaper.feedback }}</p>
        </div>
      </div>

      <!-- FILE UPLOAD BOX -->
      <form @submit.prevent="submitPaper" class="upload-box">
        <label for="pdf-upload" class="upload-label">Select PDF Document</label>
        <input 
          id="pdf-upload" 
          type="file" 
          accept="application/pdf" 
          @change="handleFileSelect"
          class="file-input"
        />
        <button 
          type="submit" 
          class="btn-submit" 
          :disabled="!selectedFile"
        >
          Upload Position Paper
        </button>
      </form>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import apiClient from '@/api/client'
import { useToastStore } from '@/stores/toast'

const toastStore = useToastStore()

// Local state for dashboard data
const dashboardData = ref({
  announcements: [],
  delegate: {
    committee: '',
    country: ''
  },
  conferenceLinks: [],
  positionPaper: {
    status: 'unsubmitted', // 'unsubmitted', 'submitted', 'graded'
    score: '',
    feedback: '',
    instructions: []
  }
})

const selectedFile = ref(null)

// Pad or trim links array to strictly 5 slot boxes
const formattedLinks = computed(() => {
  const links = [...(dashboardData.value.conferenceLinks || [])]
  while (links.length < 5) {
    links.push({ text: '', url: '' })
  }
  return links.slice(0, 5)
})

// Dynamic class for status indicators
const statusClass = computed(() => {
  switch (dashboardData.value.positionPaper.status) {
    case 'submitted':
      return 'status-submitted'
    case 'graded':
      return 'status-graded'
    case 'unsubmitted':
    default:
      return 'status-unsubmitted'
  }
})

// File selection handler
const handleFileSelect = (event) => {
  const file = event.target.files[0]
  if (file && file.type === 'application/pdf') {
    selectedFile.value = file
  } else {
    selectedFile.value = null
  }
}

// Upload submission function
const submitPaper = async () => {
  if (!selectedFile.value) return

  const formData = new FormData()
  formData.append('paper', selectedFile.value)

  try {
    await apiClient.post('/delegate/upload-paper', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })

    // Reflect the new status locally so the panel updates immediately
    dashboardData.value.positionPaper.status = 'submitted'
    selectedFile.value = null
    toastStore.showToast('Paper submitted successfully!', 'success')
  } catch (error) {
    // Backend errors are surfaced globally by the client.js toast interceptor
  }
}

// Fetch dashboard data from backend on mount
onMounted(async () => {
  try {
    const response = await apiClient.get('/delegate/my-assignment')
    const data = response.data || {}

    // Merge defensively so a partial payload still renders (and never throws in template)
    dashboardData.value = {
      announcements: data.announcements || [],
      delegate: {
        committee: data.delegate?.committee || '',
        country: data.delegate?.country || ''
      },
      conferenceLinks: data.conferenceLinks || [],
      positionPaper: {
        status: data.positionPaper?.status || 'unsubmitted',
        score: data.positionPaper?.score ?? '',
        feedback: data.positionPaper?.feedback || '',
        instructions: data.positionPaper?.instructions || []
      }
    }
  } catch (error) {
    // Backend errors are surfaced globally by the client.js toast interceptor
  }
})
</script>

<style scoped>
/* GENERAL LAYOUT */
.delegate-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
  color: #ffffff;
  font-family: Arial, sans-serif;
}

/* ANNOUNCEMENT BAR */
.announcement-bar {
  background-color: #2a2e35;
  border: 1px solid #3f444e;
  border-left: 4px solid #6366f1;
  padding: 12px 20px;
  border-radius: 4px;
  display: flex;
  gap: 10px;
  align-items: center;
}

.announcement-label {
  font-weight: bold;
  color: #6366f1;
}

.announcement-text {
  color: #e0e0e0;
}

/* PANELS */
.top-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.panel {
  background-color: #2a2e35;
  border: 1px solid #3f444e;
  border-radius: 8px;
  padding: 20px;
  display: flex;
  flex-direction: column;
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

/* CONFERENCE LINKS */
.links-container {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.link-box {
  background-color: #1a1d21;
  border: 1px solid #3f444e;
  border-radius: 4px;
  min-height: 38px;
  padding: 0 12px;
  display: flex;
  align-items: center;
}

.link-box a {
  color: #22d3ee;
  text-decoration: none;
  font-size: 0.9rem;
  word-break: break-all;
}

.link-box a:hover {
  text-decoration: underline;
}

/* DELEGATE INFO */
.info-content {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  background-color: #1a1d21;
  border: 1px solid #3f444e;
  padding: 12px 15px;
  border-radius: 4px;
}

.info-label {
  color: #aaaaaa;
}

.info-value {
  font-weight: bold;
  color: #ffffff;
}

/* POSITION PAPER PANEL */
.paper-panel {
  gap: 20px;
}

.instructions-block {
  background-color: #1a1d21;
  border: 1px solid #3f444e;
  border-radius: 4px;
  padding: 15px 20px 15px 35px;
}

.instructions-list {
  margin: 0;
  padding: 0;
  color: #cccccc;
  line-height: 1.6;
  font-size: 0.95rem;
}

.status-block {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-label {
  font-size: 1rem;
  color: #aaaaaa;
}

.status-badge {
  padding: 6px 12px;
  border-radius: 4px;
  font-weight: bold;
  font-size: 0.85rem;
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

/* GRADED SECTION */
.grading-block {
  background-color: #1a1d21;
  border: 1px solid #3f444e;
  border-radius: 4px;
  padding: 15px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.score-row {
  font-size: 1rem;
  color: #aaaaaa;
  display: flex;
  gap: 10px;
  align-items: center;
}

.score-value {
  color: #22c55e;
  font-size: 1.2rem;
}

.feedback-title {
  margin: 0 0 5px 0;
  color: #aaaaaa;
  font-size: 0.9rem;
}

.feedback-text {
  margin: 0;
  color: #ffffff;
  line-height: 1.4;
  font-size: 0.95rem;
}

/* FILE UPLOAD */
.upload-box {
  background-color: #1a1d21;
  border: 1px dashed #3f444e;
  border-radius: 4px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.upload-label {
  font-size: 0.9rem;
  color: #aaaaaa;
}

.file-input {
  color: #ffffff;
}

.btn-submit {
  align-self: flex-start;
  background-color: #6366f1;
  color: #ffffff;
  border: none;
  padding: 10px 20px;
  border-radius: 4px;
  font-weight: bold;
  cursor: pointer;
}

.btn-submit:disabled {
  background-color: #3f444e;
  color: #888888;
  cursor: not-allowed;
}

/* RESPONSIVE */
@media (max-width: 768px) {
  .top-grid {
    grid-template-columns: 1fr;
  }
}
</style>