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

    <!-- HOW THIS VIEW WORKS -->
    <section class="page-guide">
      <h2>How position paper grading works</h2>
      <p>
        Every card is one delegation and displays the position paper's status:
        <strong>Not submitted</strong>, <strong>Submitted</strong> with the date, or
        <strong>Graded</strong> with the score it was given.
      </p>
      <ol>
        <li>
          <strong>View &amp; Grade</strong> opens the paper and grading view. Available once the delegate 
          submits their paper.
        </li>
        <li>Inside the grading view, mark each criterion out of its maximum. The total updates as you type.</li>
        <li>
          Comments are optional. They will be displayed to the delegate immediately, as will the score.
        </li>
        <li>
          Press <strong>Submit Grade</strong>. Grading can be repeated: the new marks replace
          the previous ones.
        </li>
      </ol>
      <p>
        Once a paper is graded, delegates cannot resubmit. <strong>PDF</strong>
        downloads the submitted paper as a file.
      </p>
    </section>

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
            <span class="sub-date">{{ formatSubmissionDate(delegate.submissionDate) }}</span>
          </div>

          <div v-else-if="delegate.status === 'graded'" class="status-line status-graded">
            <div class="graded-header">
              <span>• Graded</span>
              <span class="score-badge">{{ delegate.totalScore }}</span>
            </div>
            <span class="sub-date">{{ formatSubmissionDate(delegate.submissionDate) }}</span>
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

    <!-- FULL SCREEN: the paper on the left, the grading controls in a sidebar on the right -->
    <div v-if="activeDelegate" class="grading-modal-overlay">
      <!-- NATIVE PDF PREVIEW IFRAME (src is an in-memory blob URL; an iframe cannot
           send the Authorization header, so the PDF is fetched through the API client) -->
      <div class="pdf-viewer-container">
        <iframe
          v-if="previewUrl"
          :src="previewUrl"
          class="pdf-iframe"
          title="Position Paper PDF Preview"
        ></iframe>
        <div v-else class="pdf-error-fallback">
          {{ loadingPreview ? 'Loading the position paper…' : 'Unable to preview document.' }}
        </div>
      </div>

      <!-- GRADING SIDEBAR: identity, running total, one row per category, comments, actions.
           The sidebar owns the full height, so each category gets its own line instead of
           being squeezed into a strip above the paper. -->
      <aside class="grading-sidebar">
        <div class="sidebar-head">
          <div class="delegate-summary">
            <h2>{{ activeDelegate.country }}</h2>
            <span class="committee-label">{{ activeDelegate.committee }}</span>
          </div>

          <div class="score-summary-box">
            <span class="summary-label">Total Score</span>
            <span class="summary-score">{{ calculatedTotalScore }} / {{ maxPossibleScore }}</span>
          </div>
        </div>

        <div class="rubric-inputs">
          <div v-for="cat in rubric" :key="cat.id" class="rubric-field">
            <label :for="`score-${cat.id}`">{{ cat.label }}</label>
            <span class="rubric-max">max {{ cat.maxScore }}</span>
            <input
              :id="`score-${cat.id}`"
              type="number"
              min="0"
              :max="cat.maxScore"
              v-model.number="gradingScores[cat.id]"
            />
          </div>
        </div>

        <div class="comments-field">
          <label for="grading-comments">Chair Feedback / Comments</label>
          <textarea
            id="grading-comments"
            v-model="gradingComments"
            placeholder="Enter comments for delegate..."
          ></textarea>
        </div>

        <div class="bar-actions">
          <button class="btn-save" @click="saveGrade">Submit Grade</button>
          <button class="btn-close" @click="closeGradingModal">✕ Close</button>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
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
// Object URL for the PDF currently on screen; revoked whenever the modal closes, or the
// browser would hold every previewed paper in memory for the life of the page.
const previewUrl = ref('')
const loadingPreview = ref(false)

const releasePreview = () => {
  if (previewUrl.value) {
    window.URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = ''
  }
}

// The API sends an instant with a UTC offset; show it in the chair's own timezone.
const formatSubmissionDate = (timestamp) => {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit'
  })
}

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
const openGradingModal = async (delegate) => {
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

  // Fetch the paper through the API client (which sends the bearer token) and hand the
  // viewer a blob URL, since a plain iframe src would arrive unauthenticated.
  releasePreview()
  loadingPreview.value = true
  try {
    const response = await apiClient.get(`/chair/papers/${delegate.id}/download`, {
      responseType: 'blob'
    })
    previewUrl.value = window.URL.createObjectURL(
      new Blob([response.data], { type: 'application/pdf' })
    )
  } catch (error) {
    // A 404 (paper never uploaded, or the stored file is gone) also lands here
    toastStore.showToast('Could not load the position paper.', 'error')
  } finally {
    loadingPreview.value = false
  }
}

const closeGradingModal = () => {
  releasePreview()
  activeDelegate.value = null
  gradingScores.value = {}
  gradingComments.value = ''
}

onBeforeUnmount(releasePreview)

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
/* ============================================================ PAGE ====== */
/* Same white surface, navy ink and hairline rules as the delegate dashboard and the advisor
   views. The grading overlay borrows the same tokens, so the two pages read as one. */
.chair-page {
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
  --font: var(--font-theme);

  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: var(--gap);
  width: 100%;
  max-width: 1400px;
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

/* ============================================================ GUIDE ===== */
/* The "how this works" panel under the tab strip: reference text, so it sits on a pale wash
   with a hairline, quieter than the cards it explains. */
.page-guide {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background-color: #f7fafd;
  padding: clamp(12px, 1.6vh, 18px) clamp(14px, 1.8vw, 22px);
}

.page-guide h2 {
  margin: 0 0 6px;
  font-size: 1em;
  font-weight: 650;
  letter-spacing: 0.02em;
  color: var(--ink);
}

.page-guide p {
  margin: 0 0 8px;
  font-size: 0.86em;
  line-height: 1.55;
  color: var(--muted);
}

.page-guide p:last-child {
  margin-bottom: 0;
}

.page-guide ol {
  margin: 0 0 8px;
  padding-left: 1.2em;
  font-size: 0.86em;
  line-height: 1.55;
  color: var(--muted);
}

.page-guide li + li {
  margin-top: 3px;
}

.page-guide strong {
  color: var(--ink-2);
  font-weight: 650;
}

/* =========================================================== TOGGLE ===== */
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

/* ============================================================= GRID ===== */
.grid-container {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--gap);
}

/* One card per paper: white on white, hairline edge, one soft shadow. */
.delegate-card {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 10px;
  min-height: 132px;
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background-color: #ffffff;
  box-shadow:
    0 1px 2px rgba(3, 4, 94, 0.04),
    0 24px 48px -40px rgba(3, 4, 94, 0.45);
  transition:
    border-color 0.3s ease,
    box-shadow 0.3s ease,
    transform 0.3s var(--ease);
}

.delegate-card:hover {
  border-color: rgba(3, 4, 94, 0.16);
  transform: translateY(-2px);
}

.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
}

.country-name {
  font-size: 0.92em;
  font-weight: 650;
  line-height: 1.25;
  color: var(--ink);
}

.committee-tag {
  flex: none;
  max-width: 55%;
  overflow: hidden;
  padding: 3px 8px;
  border-radius: 999px;
  background-color: #f7fafd;
  font-size: 0.62em;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--muted);
}

/* =========================================================== STATUS ===== */
.status-container {
  font-size: 0.8em;
}

.status-line {
  display: flex;
  flex-direction: column;
  gap: 2px;
  /* The card's whole point is where the paper stands, so the status line carries more weight
     than it used to; the date and score inside it scale with it. */
  font-size: 0.82em;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

/* Nothing submitted is the resting state, not a problem. */
.status-unsubmitted {
  color: var(--muted);
}

.status-submitted {
  color: var(--gold);
}

.status-graded {
  color: var(--green);
}

.graded-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.score-badge {
  padding: 3px 10px;
  border-radius: 999px;
  background-color: rgba(22, 163, 74, 0.1);
  color: var(--green);
  font-size: 1.08em;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.sub-date {
  font-size: 0.95em;
  font-weight: 500;
  letter-spacing: 0.02em;
  text-transform: none;
  color: var(--muted);
}

/* ========================================================== ACTIONS ===== */
.card-actions {
  display: flex;
  gap: 7px;
}

.btn-action {
  padding: 7px 10px;
  border-radius: 9px;
  font-family: inherit;
  font-size: 0.72em;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  cursor: pointer;
  transition:
    background-color 0.25s ease,
    border-color 0.25s ease,
    color 0.25s ease,
    transform 0.25s var(--ease);
}

.btn-view {
  flex: 3;
  border: 1px solid var(--ink);
  background-color: var(--ink);
  color: #ffffff;
}

.btn-view:hover:not(:disabled) {
  background-color: #071f7a;
  border-color: #071f7a;
  transform: translateY(-1px);
}

.btn-download {
  flex: 1;
  border: 1px solid var(--line);
  background-color: #ffffff;
  color: var(--ink);
}

.btn-download:hover:not(:disabled) {
  border-color: rgba(0, 157, 219, 0.4);
  background-color: #f2f9fe;
  color: #0079ab;
  transform: translateY(-1px);
}

.btn-action:disabled {
  border-color: rgba(3, 4, 94, 0.1);
  background-color: #f2f4f8;
  color: #9aa5b1;
  cursor: not-allowed;
}

/* ========================================================== OVERLAY ===== */
/* Full screen grading: the paper on the left of the eye, the rubric on top. */
.grading-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  /* Paper left, grading controls right. It used to be a column with a control strip on top,
     which left the rubric inputs in a single cramped line above the document. */
  flex-direction: row;
  background-color: #f5fafd;
  animation: overlay-in 0.3s ease both;
}

@keyframes overlay-in {
  from {
    opacity: 0;
  }
}

/* The sidebar owns the full height of the screen, so every category gets its own row and the
   comments box can grow into whatever is left. */
.grading-sidebar {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 14px;
  width: clamp(340px, 27vw, 430px);
  /* `border-box`, height and min-height: 0 together keep the sidebar exactly one screen tall.
     Without border-box its vertical padding was added on top of `height: 100%`, making the
     column 36px taller than the viewport and pushing the action buttons below the fold. */
  box-sizing: border-box;
  height: 100%;
  min-height: 0;
  padding: 18px clamp(16px, 1.6vw, 22px);
  border-left: 1px solid var(--line);
  background-color: #ffffff;
  overflow-y: auto;
}

.sidebar-head {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.delegate-summary {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.delegate-summary h2 {
  margin: 0;
  font-size: 1.15em;
  font-weight: 650;
  line-height: 1.2;
  letter-spacing: -0.01em;
  color: var(--ink);
}

.committee-label {
  font-size: 0.68em;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
}

.score-summary-box {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 14px;
  border-radius: 11px;
  background-color: #f7fafd;
}

.summary-label {
  font-size: 0.66em;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
}

.summary-score {
  font-size: 1.02em;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--green);
}

.bar-actions {
  flex: none;
  display: flex;
  gap: 9px;
}

.btn-save {
  padding: 9px 18px;
  border: 1px solid var(--ink);
  border-radius: 9px;
  background-color: var(--ink);
  color: #ffffff;
  font-family: inherit;
  font-size: 0.78em;
  font-weight: 650;
  cursor: pointer;
  transition:
    background-color 0.25s ease,
    border-color 0.25s ease,
    transform 0.25s var(--ease);
}

.btn-save:hover {
  background-color: #071f7a;
  border-color: #071f7a;
  transform: translateY(-1px);
}

.btn-close {
  padding: 9px 15px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background-color: #ffffff;
  color: var(--ink-2);
  font-family: inherit;
  font-size: 0.78em;
  font-weight: 650;
  cursor: pointer;
  transition:
    background-color 0.25s ease,
    border-color 0.25s ease,
    color 0.25s ease;
}

.btn-close:hover {
  border-color: rgba(180, 35, 24, 0.35);
  background-color: rgba(180, 35, 24, 0.06);
  color: var(--red);
}

/* ===================================================== RUBRIC INPUTS ==== */
.rubric-inputs {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* Category name, its maximum, then the mark: one row each, full width of the sidebar. */
.rubric-field {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto 78px;
  align-items: center;
  gap: 10px;
  padding: 8px 11px;
  border-radius: 9px;
  background-color: #f7fafd;
}

.rubric-field label {
  /* Sentence case here, not the uppercase label style: a criterion name can be a sentence,
     and it is the thing the chair reads while typing the mark. */
  font-size: 0.8em;
  font-weight: 600;
  letter-spacing: 0;
  text-transform: none;
  color: var(--ink-2);
  overflow-wrap: break-word;
}

.rubric-max {
  font-size: 0.7em;
  font-variant-numeric: tabular-nums;
  color: var(--muted);
  white-space: nowrap;
}

.comments-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  /* The only flexible block in the sidebar: it takes the leftover height, but keeps enough
     room for a few lines before the sidebar starts scrolling. */
  flex: 1 1 auto;
  min-height: 104px;
}

.comments-field label {
  font-size: 0.62em;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
}

.rubric-field input,
.comments-field textarea {
  border: 1px solid var(--line);
  border-radius: 9px;
  background-color: #ffffff;
  color: var(--ink);
  font-family: inherit;
  font-size: 0.84em;
  transition:
    border-color 0.2s ease,
    background-color 0.2s ease;
}

.rubric-field input {
  width: 100%;
  padding: 7px 9px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}

.comments-field textarea {
  flex: 1;
  padding: 9px 11px;
  resize: vertical;
  line-height: 1.45;
}

.rubric-field input:focus,
.comments-field textarea:focus {
  outline: none;
  border-color: rgba(0, 157, 219, 0.5);
  background-color: #ffffff;
}

/* ========================================================== PDF VIEW ==== */
.pdf-viewer-container {
  /* Takes whatever the fixed-width sidebar does not: `min-width: 0` lets it shrink instead of
     forcing the row wider than the viewport. */
  flex: 1;
  min-width: 0;
  min-height: 0;
  background-color: #f2f4f8;
  color: var(--muted);
}

.pdf-iframe {
  width: 100%;
  height: 100%;
  border: none;
}

.pdf-error-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  font-size: 0.88em;
  color: var(--muted);
}

/* ========================================================== RESPONSIVE === */
@media (max-width: 1200px) {
  .grid-container {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 800px) {
  .grid-container {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .toggle-btn {
    flex: 1;
    min-width: 0;
  }

  /* Not enough width for a side-by-side paper and sidebar: stack them, with the grading
     controls on top so the marks are reachable without scrolling past the document. */
  .grading-modal-overlay {
    flex-direction: column;
  }

  .grading-sidebar {
    order: -1;
    width: 100%;
    height: auto;
    max-height: 52vh;
    /* Same reason as the desktop rule: padding must count inside the cap, or the buttons
       scroll out of reach again. */
    box-sizing: border-box;
    border-left: 0;
    border-bottom: 1px solid var(--line);
  }
}

@media (max-width: 500px) {
  .grid-container {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (prefers-reduced-motion: reduce) {
  .grading-modal-overlay {
    animation: none;
  }

  .delegate-card,
  .btn-action,
  .btn-save,
  .btn-close {
    transition: none;
  }
}
</style>
