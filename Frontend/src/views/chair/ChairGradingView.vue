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

// Save / Submit Grade Handler
const saveGrade = async () => {
  if (!activeDelegate.value) return

  const gradePayload = {
    delegateId: activeDelegate.value.id,
    scores: { ...gradingScores.value },
    totalScore: `${calculatedTotalScore.value}/${maxPossibleScore.value}`,
    comments: gradingComments.value
  }

  console.log('Submitting grade to backend:', gradePayload)

  // Update local view state immediately
  activeDelegate.value.status = 'graded'
  activeDelegate.value.totalScore = gradePayload.totalScore
  activeDelegate.value.scores = { ...gradingScores.value }
  activeDelegate.value.comments = gradingComments.value

  closeGradingModal()
}

// Download Handler
const downloadPaper = (delegate) => {
  console.log(`Triggering direct PDF download for delegate: ${delegate.country}`)
}

// Fetch Initial Data on Mount
onMounted(async () => {
  // Mock Rubric Definition
  rubric.value = [
    { id: 'research', label: 'Research', maxScore: 25 },
    { id: 'policy', label: 'Policy', maxScore: 25 },
    { id: 'solutions', label: 'Solutions', maxScore: 25 },
    { id: 'formatting', label: 'Formatting', maxScore: 25 }
  ]

  // Mock Delegates Payload (Sample to demonstrate 12-15 layout density)
  delegates.value = [
    {
      id: 1,
      country: 'France',
      committee: 'DISEC',
      status: 'graded',
      submissionDate: 'Sep 1, 14:30',
      totalScore: '92/100',
      comments: 'Thorough research and realistic policy solutions.',
      scores: { research: 24, policy: 23, solutions: 22, formatting: 23 },
      pdfUrl: 'https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf'
    },
    {
      id: 2,
      country: 'Brazil',
      committee: 'DISEC',
      status: 'submitted',
      submissionDate: 'Sep 2, 09:15',
      totalScore: null,
      comments: '',
      scores: {},
      pdfUrl: 'https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf'
    },
    {
      id: 3,
      country: 'Japan',
      committee: 'DISEC',
      status: 'unsubmitted',
      submissionDate: null,
      totalScore: null,
      comments: '',
      scores: {},
      pdfUrl: null
    },
    {
      id: 4,
      country: 'Germany',
      committee: 'DISEC',
      status: 'submitted',
      submissionDate: 'Sep 2, 11:40',
      totalScore: null,
      comments: '',
      scores: {},
      pdfUrl: 'https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf'
    },
    {
      id: 5,
      country: 'United Kingdom',
      committee: 'DISEC',
      status: 'graded',
      submissionDate: 'Aug 30, 18:20',
      totalScore: '88/100',
      comments: 'Good policy focus.',
      scores: { research: 22, policy: 23, solutions: 21, formatting: 22 },
      pdfUrl: 'https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf'
    },
    {
      id: 6,
      country: 'Egypt',
      committee: 'DISEC',
      status: 'unsubmitted',
      submissionDate: null,
      totalScore: null,
      comments: '',
      scores: {},
      pdfUrl: null
    },
    {
      id: 7,
      country: 'India',
      committee: 'DISEC',
      status: 'submitted',
      submissionDate: 'Sep 1, 22:10',
      totalScore: null,
      comments: '',
      scores: {},
      pdfUrl: 'https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf'
    },
    {
      id: 8,
      country: 'Canada',
      committee: 'DISEC',
      status: 'graded',
      submissionDate: 'Sep 1, 10:05',
      totalScore: '95/100',
      comments: 'Exceptional position paper.',
      scores: { research: 24, policy: 25, solutions: 23, formatting: 23 },
      pdfUrl: 'https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf'
    },
    {
      id: 9,
      country: 'South Africa',
      committee: 'DISEC',
      status: 'unsubmitted',
      submissionDate: null,
      totalScore: null,
      comments: '',
      scores: {},
      pdfUrl: null
    },
    {
      id: 10,
      country: 'Mexico',
      committee: 'DISEC',
      status: 'submitted',
      submissionDate: 'Sep 2, 08:00',
      totalScore: null,
      comments: '',
      scores: {},
      pdfUrl: 'https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf'
    },
    {
      id: 11,
      country: 'Australia',
      committee: 'DISEC',
      status: 'graded',
      submissionDate: 'Aug 31, 14:15',
      totalScore: '85/100',
      comments: 'Solid work.',
      scores: { research: 21, policy: 22, solutions: 20, formatting: 22 },
      pdfUrl: 'https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf'
    },
    {
      id: 12,
      country: 'South Korea',
      committee: 'DISEC',
      status: 'submitted',
      submissionDate: 'Sep 1, 19:45',
      totalScore: null,
      comments: '',
      scores: {},
      pdfUrl: 'https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf'
    }
  ]
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
  width: 220px;
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

/* COMPACT DELEGATE GRID (4 COLUMNS) */
.grid-container {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.delegate-card {
  background-color: #2a2e35;
  border: 1px solid #3f444e;
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
  color: #ffffff;
}

.committee-tag {
  font-size: 0.75rem;
  color: #22d3ee;
  background-color: #1a1d21;
  padding: 2px 6px;
  border-radius: 3px;
  border: 1px solid #3f444e;
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
  color: #f59e0b;
  font-weight: bold;
}

.status-graded {
  color: #22c55e;
}

.graded-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: bold;
}

.score-badge {
  background-color: #14532d;
  color: #86efac;
  border: 1px solid #22c55e;
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 0.75rem;
}

.sub-date {
  font-size: 0.75rem;
  color: #888888;
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
  background-color: #6366f1;
  color: #ffffff;
}

.btn-view:hover:not(:disabled) {
  background-color: #4f46e5;
}

.btn-download {
  flex: 1;
  background-color: #1a1d21;
  color: #ffffff;
  border: 1px solid #3f444e;
}

.btn-download:hover:not(:disabled) {
  background-color: #3f444e;
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
  background-color: #1a1d21;
  z-index: 1000;
  display: flex;
  flex-direction: column;
}

/* TOP GRADING CONTROL BAR */
.top-grading-bar {
  background-color: #2a2e35;
  border-bottom: 2px solid #3f444e;
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
  color: #ffffff;
}

.committee-label {
  font-size: 0.8rem;
  color: #22d3ee;
}

.score-summary-box {
  background-color: #1a1d21;
  border: 1px solid #3f444e;
  padding: 6px 16px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.summary-label {
  font-size: 0.85rem;
  color: #aaaaaa;
}

.summary-score {
  font-size: 1.1rem;
  font-weight: bold;
  color: #22c55e;
}

.bar-actions {
  display: flex;
  gap: 10px;
}

.btn-save {
  background-color: #22c55e;
  color: #111111;
  border: none;
  padding: 8px 16px;
  border-radius: 4px;
  font-weight: bold;
  cursor: pointer;
}

.btn-save:hover {
  background-color: #16a34a;
  color: #ffffff;
}

.btn-close {
  background-color: #1a1d21;
  color: #ffffff;
  border: 1px solid #3f444e;
  padding: 8px 14px;
  border-radius: 4px;
  cursor: pointer;
  font-weight: bold;
}

.btn-close:hover {
  background-color: #ef4444;
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
  color: #aaaaaa;
}

.rubric-field input {
  width: 80px;
  background-color: #1a1d21;
  border: 1px solid #3f444e;
  color: #ffffff;
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
  color: #aaaaaa;
}

.comments-field textarea {
  height: 34px;
  background-color: #1a1d21;
  border: 1px solid #3f444e;
  color: #ffffff;
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
  background-color: #111111;
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
  color: #aaaaaa;
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