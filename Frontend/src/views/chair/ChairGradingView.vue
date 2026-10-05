<template>
  <div class="chair-page">
    <!-- TOP VIEW TOGGLE BUTTONS -->
    <div class="toggle-container">
      <button 
        class="toggle-btn" 
        @click="switchView('/chair/committee')"
      >
        Committee Overview
      </button>
      <button 
        class="toggle-btn active" 
        @click="switchView('/chair/grading')"
      >
        Position Paper Grading
      </button>
      <button 
        class="toggle-btn" 
        @click="switchView('/chair/awards')"
      >
        Awards
      </button>
    </div>

    <!-- COMPACT DELEGATE GRID VIEW -->
    <div class="grid-container">
      <div 
        v-for="delegate in delegates" 
        :key="delegate.id" 
        class="delegate-card"
      >
        <div class="card-header">
          <span class="country-name">{{ delegate.country }}</span>
          <span class="committee-tag">{{ delegate.committee }}</span>
        </div>

        <!-- STATUS DISPLAY -->
        <div class="status-container">
          <div v-if="delegate.status === 'unsubmitted'" class="status-line status-unsubmitted">
            • Not Submitted
          </div>

          <div v-else-if="delegate.status === 'submitted'" class="status-line status-submitted">
            <span>• Submitted</span>
            <span class="sub-date">{{ delegate.submissionDate }}</span>
          </div>

          <div v-else-if="delegate.status === 'graded'" class="status-line status-graded">
            <div class="graded-header">
              <span>• Graded</span>
              <span class="score-badge">{{ delegate.totalScore }}</span>
            </div>
            <span class="sub-date">{{ delegate.submissionDate }}</span>
          </div>
        </div>

        <!-- CARD ACTIONS -->
        <div class="card-actions">
          <button 
            class="btn-action btn-view" 
            :disabled="delegate.status === 'unsubmitted'"
            @click="openGradingModal(delegate)"
          >
            View & Grade
          </button>
          
          <button 
            class="btn-action btn-download" 
            :disabled="delegate.status === 'unsubmitted'"
            @click="downloadPaper(delegate)"
          >
            PDF
          </button>
        </div>
      </div>
    </div>

    <!-- FULL SCREEN PDF VIEWER & GRADING OVERLAY -->
    <div v-if="activeDelegate" class="grading-modal-overlay">
      <!-- TOP GRADING CONTROL BAR -->
      <header class="top-grading-bar">
        <!-- HEADER ROW: INFO, SCORE SUMMARY, & ACTIONS -->
        <div class="bar-header-row">
          <div class="delegate-summary">
            <h2>{{ activeDelegate.country }}</h2>
            <span class="committee-label">{{ activeDelegate.committee }}</span>
          </div>

          <div class="score-summary-box">
            <span class="summary-label">Total Score:</span>
            <span class="summary-score">{{ calculatedTotalScore }} / {{ maxPossibleScore }}</span>
          </div>

          <div class="bar-actions">
            <button class="btn-save" @click="saveGrade">Submit Grade</button>
            <button class="btn-close" @click="closeGradingModal">✕ Close</button>
          </div>
        </div>

        <!-- DYNAMIC RUBRIC INPUTS & COMMENTS ROW -->
        <div class="rubric-row">
          <div class="rubric-inputs">
            <div 
              v-for="cat in rubric" 
              :key="cat.id" 
              class="rubric-field"
            >
              <label>{{ cat.label }} (Max {{ cat.maxScore }})</label>
              <input 
                type="number" 
                min="0" 
                :max="cat.maxScore"
                v-model.number="gradingScores[cat.id]"
              />
            </div>
          </div>

          <div class="comments-field">
            <label>Chair Feedback / Comments:</label>
            <textarea 
              v-model="gradingComments" 
              placeholder="Enter comments for delegate..."
            ></textarea>
          </div>
        </div>
      </header>

      <!-- NATIVE PDF PREVIEW IFRAME -->
      <div class="pdf-viewer-container">
        <iframe 
          v-if="activeDelegate.pdfUrl" 
          :src="activeDelegate.pdfUrl" 
          class="pdf-iframe"
          title="Position Paper PDF Preview"
        ></iframe>
        <div v-else class="pdf-error-fallback">
          Unable to preview document.
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import apiClient from '@/api/client'
import { useToastStore } from '@/stores/toast'
const toastStore = useToastStore()
import { useRouter } from 'vue-router'

const router = useRouter()

// Reactive State
const rubric = ref([])
const delegates = ref([])

// Active Modal State
const activeDelegate = ref(null)
const gradingScores = ref({})
const gradingComments = ref('')

// Navigation Handler
const switchView = (path) => {
  router.push(path)
}

// Compute live rubric score total
const calculatedTotalScore = computed(() => {
  let total = 0
  for (const cat of rubric.value) {
    const val = Number(gradingScores.value[cat.id]) || 0
    total += val
  }
  return total
})

const maxPossibleScore = computed(() => {
  return rubric.value.reduce((acc, cat) => acc + cat.maxScore, 0)
})

// Open Grading Modal & Initialize Inputs
const openGradingModal = (delegate) => {
  activeDelegate.value = delegate
  gradingComments.value = delegate.comments || ''

  // Pre-fill existing scores or default to 0
  const initialScores = {}
  rubric.value.forEach((cat) => {
    initialScores[cat.id] = (delegate.scores && delegate.scores[cat.id] !== undefined)
      ? delegate.scores[cat.id]
      : 0
  })
  gradingScores.value = initialScores
}

const closeGradingModal = () => {
  activeDelegate.value = null
  gradingScores.value = {}
  gradingComments.value = ''
}

// 1. Refactored Save/Submit Grade Handler
const saveGrade = async () => {
  if (!activeDelegate.value) return

  const gradePayload = {
    delegateId: activeDelegate.value.id,
    scores: { ...gradingScores.value },
    totalScore: `${calculatedTotalScore.value}/${maxPossibleScore.value}`,
    comments: gradingComments.value
  }

  try {
    // Send grade and feedback to backend
    await apiClient.post(`/chair/papers/${activeDelegate.value.id}/grade`, gradePayload)

    // Update local state upon successful response
    activeDelegate.value.status = 'graded'
    activeDelegate.value.totalScore = gradePayload.totalScore
    activeDelegate.value.scores = { ...gradingScores.value }
    activeDelegate.value.comments = gradingComments.value

    toastStore.showToast('Grade saved successfully.', 'success')
    closeGradingModal()
  } catch (error) {
    // Backend errors handle popup automatically via client.js interceptor
  }
}

// 2. Refactored Download Handler
const downloadPaper = async (delegate) => {
  try {
    const response = await apiClient.get(`/chair/papers/${delegate.id}/download`, {
      responseType: 'blob' // Essential for binary file downloads
    })

    // Create a temporary browser download link for the PDF
    const blob = new Blob([response.data], { type: 'application/pdf' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `${delegate.country}_Position_Paper.pdf`)
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  } catch (error) {
    toastStore.showToast('Failed to download position paper.', 'error')
  }
}

// 3. Refactored Data Fetching on Mount
onMounted(async () => {
  try {
    // Fetch rubric criteria and assigned delegate papers in parallel
    const [rubricResponse, delegatesResponse] = await Promise.all([
      apiClient.get('/chair/rubric'),
      apiClient.get('/chair/delegates')
    ])

    rubric.value = rubricResponse.data
    delegates.value = delegatesResponse.data
  } catch (error) {
    // Automatic error notification handled globally
  }
})
</script>

<style scoped>
.chair-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 1400px;
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
  width: 220px;
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

/* COMPACT DELEGATE GRID (4 COLUMNS) */
.grid-container {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.delegate-card {
  background-color: #ffffff;
  border: 1px solid #e8c604;
  border-radius: 6px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 10px;
  min-height: 125px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.country-name {
  font-weight: bold;
  font-size: 0.95rem;
  color: #00007e93;
}

.committee-tag {
  font-size: 0.75rem;
  color: #00007e;
  background-color: #f5fafd;
  padding: 2px 6px;
  border-radius: 3px;
  border: 1px solid #e8c604;
}

/* STATUS DISPLAY */
.status-container {
  font-size: 0.8rem;
}

.status-line {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.status-unsubmitted {
  color: #ef4444;
  font-weight: bold;
}

.status-submitted {
  color: #e8c604;
  font-weight: bold;
}

.status-graded {
  color: #16a34a;
}

.graded-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: bold;
}

.score-badge {
  background-color: #dcfce7;
  color: #166534;
  border: 1px solid #16a34a;
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 0.75rem;
}

.sub-date {
  font-size: 0.75rem;
  color: #6b7c8d;
  font-weight: normal;
}

/* CARD ACTIONS */
.card-actions {
  display: flex;
  gap: 6px;
}

.btn-action {
  padding: 6px;
  border-radius: 4px;
  font-size: 0.8rem;
  font-weight: bold;
  cursor: pointer;
  border: none;
}

.btn-view {
  flex: 3;
  background-color: #009ddbda;
  color: #00007e;
}

.btn-view:hover:not(:disabled) {
  background-color: #00007e;
  color: #ffffff;
}

.btn-download {
  flex: 1;
  background-color: #f5fafd;
  color: #00007e;
  border: 1px solid #e8c604;
}

.btn-download:hover:not(:disabled) {
  background-color: #e8c604;
}

.btn-action:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

/* FULL SCREEN GRADING MODAL OVERLAY */
.grading-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background-color: #f5fafd;
  z-index: 1000;
  display: flex;
  flex-direction: column;
}

/* TOP GRADING CONTROL BAR */
.top-grading-bar {
  background-color: #ffffff;
  border-bottom: 2px solid #e8c604;
  padding: 12px 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.bar-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.delegate-summary h2 {
  margin: 0;
  font-size: 1.2rem;
  color: #00007e;
}

.committee-label {
  font-size: 0.8rem;
  color: #00007e;
}

.score-summary-box {
  background-color: #f5fafd;
  border: 1px solid #e8c604;
  padding: 6px 16px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.summary-label {
  font-size: 0.85rem;
  color: #5b6b7d;
}

.summary-score {
  font-size: 1.1rem;
  font-weight: bold;
  color: #16a34a;
}

.bar-actions {
  display: flex;
  gap: 10px;
}

.btn-save {
  background-color: #16a34a;
  color: #00007e;
  border: none;
  padding: 8px 16px;
  border-radius: 4px;
  font-weight: bold;
  cursor: pointer;
}

.btn-save:hover {
  background-color: #e8c604;
  color: #00007e;
}

.btn-close {
  background-color: #f5fafd;
  color: #00007e;
  border: 1px solid #e8c604;
  padding: 8px 14px;
  border-radius: 4px;
  cursor: pointer;
  font-weight: bold;
}

.btn-close:hover {
  background-color: #ef4444;
  color: #ffffff;
  border-color: #ef4444;
}

/* RUBRIC INPUTS & COMMENTS */
.rubric-row {
  display: flex;
  gap: 20px;
  align-items: flex-end;
}

.rubric-inputs {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.rubric-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.rubric-field label {
  font-size: 0.75rem;
  color: #5b6b7d;
}

.rubric-field input {
  width: 80px;
  background-color: #ffffff;
  border: 1px solid #e8c604;
  color: #00007e93;
  padding: 6px;
  border-radius: 4px;
  font-weight: bold;
}

.comments-field {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.comments-field label {
  font-size: 0.75rem;
  color: #5b6b7d;
}

.comments-field textarea {
  height: 34px;
  background-color: #ffffff;
  border: 1px solid #e8c604;
  color: #00007e93;
  padding: 6px 10px;
  border-radius: 4px;
  resize: none;
  font-family: Arial, sans-serif;
  font-size: 0.85rem;
}

/* PDF PREVIEW CONTAINER */
.pdf-viewer-container {
  flex: 1;
  width: 100%;
  background-color: #00007e;
  color: #ffffff;
}

.pdf-iframe {
  width: 100%;
  height: 100%;
  border: none;
}

.pdf-error-fallback {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
  color: #5b6b7d;
}

/* RESPONSIVE LAYOUT BREAKPOINTS */
@media (max-width: 1200px) {
  .grid-container {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 800px) {
  .grid-container {
    grid-template-columns: repeat(2, 1fr);
  }
  .rubric-row {
    flex-direction: column;
    align-items: stretch;
  }
}

@media (max-width: 500px) {
  .grid-container {
    grid-template-columns: 1fr;
  }
}
</style>