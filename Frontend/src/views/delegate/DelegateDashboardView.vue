<template>
  <div class="delegate-page">
    <!-- ANNOUNCEMENT BAR (the backend sends at most 3: 2 general + 1 for this committee) -->
    <div v-if="dashboardData.announcements.length" class="announcement-bar">
      <span class="announcement-label">
        {{ dashboardData.announcements.length > 1 ? 'ANNOUNCEMENTS:' : 'ANNOUNCEMENT:' }}
      </span>
      <div class="announcement-lines">
        <span
          v-for="(announcement, index) in dashboardData.announcements"
          :key="index"
          class="announcement-text"
        >
          {{ announcement }}
        </span>
      </div>
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

    <!-- POSITION PAPER SUBMISSION + CHAIR FEEDBACK -->
    <div class="paper-grid">
      <!-- SUBMISSION PANEL -->
      <section class="panel paper-panel">
        <h2 class="panel-title">Position Paper Submission</h2>

        <!-- INSTRUCTIONS LIST -->
        <div v-if="positionPaper.instructions.length" class="instructions-block">
          <ol class="instructions-list">
            <li 
              v-for="(instruction, index) in positionPaper.instructions" 
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
            {{ positionPaper.status.toUpperCase() }}
          </span>
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

      <!-- GRADE & FEEDBACK PANEL -->
      <section class="panel grade-panel">
        <h2 class="panel-title">Grade &amp; Chair Feedback</h2>

        <!-- AWAITING GRADING -->
        <div v-if="!isGraded" class="grade-empty">
          <span class="grade-empty-icon">⏳</span>
          <p v-if="positionPaper.status === 'submitted'">
            Your position paper has been submitted and is awaiting grading by your chair.
          </p>
          <p v-else>
            Upload your position paper to receive a grade and written feedback from your chair.
          </p>
        </div>

        <!-- GRADED -->
        <template v-else>
          <div class="grade-summary">
            <div class="grade-total">
              <span class="grade-total-label">Final Score</span>
              <strong class="grade-total-value">{{ scoreDisplay }}</strong>
            </div>
            <span :class="['status-badge', statusClass]">
              {{ positionPaper.status.toUpperCase() }}
            </span>
          </div>

          <div v-if="criteria.length" class="rubric-breakdown">
            <h3 class="subsection-title">Rubric Breakdown</h3>
            <div 
              v-for="criterion in criteria" 
              :key="criterion.id" 
              class="criterion-row"
            >
              <div class="criterion-head">
                <span class="criterion-label">{{ criterion.label }}</span>
                <span class="criterion-score">{{ criterion.score }} / {{ criterion.maxScore }}</span>
              </div>
              <div class="criterion-bar-bg">
                <div 
                  class="criterion-bar-fill" 
                  :class="{ low: criterionPercent(criterion) < 50 }"
                  :style="{ width: criterionPercent(criterion) + '%' }"
                ></div>
              </div>
            </div>
          </div>
          <p v-else class="grade-muted">
            No per-criterion breakdown was recorded for this paper.
          </p>

          <div class="feedback-block">
            <h3 class="subsection-title">Chair Comments</h3>
            <p class="feedback-text">{{ feedback || 'No comments were provided.' }}</p>
          </div>
        </template>
      </section>
    </div>
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
    instructions: [],
    criteria: []
  }
})

const selectedFile = ref(null)

// Shorthand for the position paper panel state
const positionPaper = computed(() => dashboardData.value.positionPaper)

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

/* --- Chair grade & feedback --- */

// The grade panel only shows results once a chair has graded the paper
const isGraded = computed(() => positionPaper.value.status === 'graded')

// Per-criterion marks, already joined with their labels and maxima by the backend
const criteria = computed(() => positionPaper.value.criteria || [])

const scoreDisplay = computed(() => {
  const raw = positionPaper.value.score
  return raw === '' || raw === null || raw === undefined ? '—' : raw
})
const feedback = computed(() => positionPaper.value.feedback || '')

// Percentage of the maximum for a single rubric criterion (guards against maxScore 0)
const criterionPercent = (criterion) => {
  const max = Number(criterion.maxScore)
  if (!max) return 0
  return Math.min(100, Number(((Number(criterion.score) / max) * 100).toFixed(1)))
}

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
    // No explicit Content-Type: the browser has to add the multipart boundary, and
    // setting the header by hand would send "multipart/form-data" without one.
    await apiClient.post('/delegate/upload-paper', formData)

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
        instructions: data.positionPaper?.instructions || [],
        criteria: data.positionPaper?.criteria || []
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
  color: #00007e93;
  font-family: Arial, sans-serif;
}

/* ANNOUNCEMENT BAR */
.announcement-bar {
  background-color: #ffffff;
  border: 1px solid #e8c604;
  border-left: 4px solid #009ddb;
  padding: 12px 20px;
  border-radius: 4px;
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.announcement-lines {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.announcement-label {
  font-weight: bold;
  color: #00007e;
}

.announcement-text {
  color: #00007e93;
  line-height: 1.4;
}

/* PANELS */
.top-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.panel {
  background-color: #ffffff;
  border: 1px solid #e8c604;
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
  color: #00007e;
  border-bottom: 1px solid #e8c604;
  padding-bottom: 8px;
}

/* CONFERENCE LINKS */
.links-container {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.link-box {
  background-color: #f5fafd;
  border: 1px solid #e8c604;
  border-radius: 4px;
  min-height: 38px;
  padding: 0 12px;
  display: flex;
  align-items: center;
}

.link-box a {
  color: #00007e;
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
  background-color: #f5fafd;
  border: 1px solid #e8c604;
  padding: 12px 15px;
  border-radius: 4px;
}

.info-label {
  color: #5b6b7d;
}

.info-value {
  font-weight: bold;
  color: #00007e93;
}

/* POSITION PAPER + FEEDBACK GRID */
.paper-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  align-items: start;
}

/* POSITION PAPER PANEL */
.paper-panel {
  gap: 20px;
}

.instructions-block {
  background-color: #f5fafd;
  border: 1px solid #e8c604;
  border-radius: 4px;
  padding: 15px 20px 15px 35px;
}

.instructions-list {
  margin: 0;
  padding: 0;
  color: #5b6b7d;
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
  color: #5b6b7d;
}

.status-badge {
  padding: 6px 12px;
  border-radius: 4px;
  font-weight: bold;
  font-size: 0.85rem;
}

.status-unsubmitted {
  background-color: #fee2e2;
  color: #991b1b;
  border: 1px solid #ef4444;
}

.status-submitted {
  background-color: #fdf6d3;
  color: #7a5c00;
  border: 1px solid #e8c604;
}

.status-graded {
  background-color: #dcfce7;
  color: #166534;
  border: 1px solid #16a34a;
}

/* GRADE & FEEDBACK PANEL */
.grade-panel {
  gap: 18px;
}

.grade-empty {
  background-color: #f5fafd;
  border: 1px dashed #e8c604;
  border-radius: 4px;
  padding: 24px 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  text-align: center;
  color: #5b6b7d;
}

.grade-empty p {
  margin: 0;
  font-size: 0.9rem;
  line-height: 1.5;
}

.grade-empty-icon {
  font-size: 1.6rem;
}

.grade-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: #f5fafd;
  border: 1px solid #e8c604;
  border-radius: 6px;
  padding: 14px 16px;
}

.grade-total {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.grade-total-label {
  font-size: 0.75rem;
  color: #5b6b7d;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.grade-total-value {
  font-size: 1.6rem;
  color: #16a34a;
}

.rubric-breakdown {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.subsection-title {
  margin: 0;
  font-size: 0.75rem;
  font-weight: bold;
  color: #5b6b7d;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.criterion-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.criterion-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 0.88rem;
}

.criterion-label {
  color: #00007e93;
}

.criterion-score {
  font-weight: bold;
  color: #00007e93;
  white-space: nowrap;
}

.criterion-bar-bg {
  background-color: #f5fafd;
  border: 1px solid #e8c604;
  border-radius: 4px;
  height: 8px;
  overflow: hidden;
}

.criterion-bar-fill {
  height: 100%;
  background-color: #16a34a;
  transition: width 0.4s ease;
}

.criterion-bar-fill.low {
  background-color: #e8c604;
}

.grade-muted {
  margin: 0;
  font-size: 0.85rem;
  color: #6b7c8d;
  font-style: italic;
}

.feedback-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.feedback-text {
  margin: 0;
  color: #00007e93;
  line-height: 1.5;
  font-size: 0.95rem;
  background-color: #f5fafd;
  border: 1px solid #e8c604;
  border-radius: 4px;
  padding: 12px 14px;
  white-space: pre-wrap;
}

/* FILE UPLOAD */
.upload-box {
  background-color: #f5fafd;
  border: 1px dashed #e8c604;
  border-radius: 4px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.upload-label {
  font-size: 0.9rem;
  color: #5b6b7d;
}

.file-input {
  color: #00007e93;
}

.btn-submit {
  align-self: flex-start;
  background-color: #009ddbda;
  color: #00007e;
  border: none;
  padding: 10px 20px;
  border-radius: 4px;
  font-weight: bold;
  cursor: pointer;
}

.btn-submit:disabled {
  background-color: #f5fafd;
  color: #9aa5b1;
  cursor: not-allowed;
}

/* RESPONSIVE */
@media (max-width: 768px) {
  .top-grid,
  .paper-grid {
    grid-template-columns: 1fr;
  }
}
</style>
