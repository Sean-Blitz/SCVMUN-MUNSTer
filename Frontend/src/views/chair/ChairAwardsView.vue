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
        class="toggle-btn" 
        @click="switchView('/chair/grading')"
      >
        Position Paper Grading
      </button>
      <button 
        class="toggle-btn active" 
        @click="switchView('/chair/awards')"
      >
        Awards
      </button>
    </div>

    <!-- HOW THIS VIEW WORKS -->
    <section class="page-guide">
      <h2>How this view works</h2>
      <p>
        Every delegation in your committee is a card below, showing the award it currently
        holds and its rubric points. Nothing on this page is visible to delegates.
      </p>
      <ol>
        <li>Click a delegate card to open their rubric full screen.</li>
        <li>Start by selecting countries for candidates. This will need to be done at a time specified by the Secretariat.</li>
        <li>
          Pick the award from the top dropdown:
          <strong>Candidate</strong> (shortlist), or one of the official awards.
        </li>
        <li>For each criteria, click the level that best describes the delegate's performance</li>
        <li>
          Press <strong>Save &amp; Submit</strong>. Closing the rubric without saving discards
          the changes.
        </li>
      </ol>
      <p>
        An official award needs <strong>every</strong> criterion scored before it will save;
        "Candidate" and "None" do not. All scores and awards can be changed before the deadline (see the Secretariat). Not every delegate needs to be marked here.
      </p>
    </section>

    <!-- SUMMARY PILE COUNTERS -->
    <div class="stats-bar">
      <div class="stat-pill">Candidates: <strong>{{ countByAward('Candidate') }}</strong></div>
      <div class="stat-pill pill-verbal">Verbal: <strong>{{ countByAward('Verbal Commendation') }}</strong></div>
      <div class="stat-pill pill-honorable">Honorable: <strong>{{ countByAward('Honorable Mention') }}</strong></div>
      <div class="stat-pill pill-outstanding">Outstanding: <strong>{{ countByAward('Outstanding Delegate') }}</strong></div>
      <div class="stat-pill pill-best">Best: <strong>{{ countByAward('Best Delegate') }}</strong></div>
    </div>

    <!-- ULTRA-COMPACT 5-COLUMN DELEGATE GRID -->
    <div class="grid-container">
      <div 
        v-for="delegate in delegates" 
        :key="delegate.id" 
        :class="['delegate-card', getAwardClass(delegate.assignedAward)]"
        @click="openRubricModal(delegate)"
      >
        <div class="card-info">
          <span class="country-name">{{ delegate.country }}</span>
          <span class="committee-tag">{{ delegate.committee }}</span>
        </div>

        <div class="card-status-badge">
          <span class="award-label">
            {{ delegate.assignedAward || 'None' }}
          </span>
          <span v-if="delegate.totalScore !== null" class="score-indicator">
            {{ delegate.totalScore }} pts
          </span>
        </div>
      </div>
    </div>

    <!-- FULL SCREEN INTERACTIVE RUBRIC MODAL -->
    <div v-if="activeDelegate" class="rubric-modal-overlay">
      <header class="top-rubric-bar">
        <div class="delegate-meta">
          <h2>{{ activeDelegate.country }}</h2>
          <span class="committee-sub">{{ activeDelegate.committee }}</span>
        </div>

        <!-- AWARD SELECTION DROPDOWN -->
        <div class="award-selector-box">
          <label for="award-select">Assign Award:</label>
          <select id="award-select" v-model="selectedAward">
            <option value="None">None</option>
            <option value="Candidate">Candidate (Shortlist)</option>
            <option v-for="award in awardsList" :key="award" :value="award">
              {{ award }}
            </option>
          </select>
        </div>

        <!-- LIVE SCORE DISPLAY -->
        <div class="score-summary-box">
          <span class="score-label">Rubric Score:</span>
          <span class="score-value">{{ calculatedTotalScore }} / {{ maxPossibleScore }}</span>
        </div>

        <!-- ACTION BUTTONS -->
        <div class="bar-actions">
          <button class="btn-submit" @click="submitAwardAndScore">
            Save & Submit
          </button>
          <button class="btn-close" @click="closeModal">✕ Close</button>
        </div>
      </header>

      <!-- VALIDATION ERROR ALERT -->
      <div v-if="validationError" class="validation-banner">
        <AppIcon name="warning" :size="17" />
        <span>{{ validationError }}</span>
      </div>

      <!-- RUBRIC MATRIX GRID -->
      <div class="rubric-matrix-container">
        <div 
          v-for="criterion in rubricMatrix" 
          :key="criterion.id" 
          class="rubric-row"
        >
          <div class="criterion-header">
            <h3>{{ criterion.label }}</h3>
            <span class="selected-pts">
              Score: <strong>{{ gradingScores[criterion.id] ?? 0 }}</strong> / {{ getCriterionMax(criterion) }}
            </span>
          </div>

          <div class="level-cells-grid">
            <div 
              v-for="level in criterion.levels" 
              :key="level.score"
              :class="[
                'rubric-cell', 
                { selected: gradingScores[criterion.id] === level.score }
              ]"
              @click="selectScore(criterion.id, level.score)"
            >
              <div class="cell-top">
                <span class="level-title">{{ level.label }}</span>
                <span class="level-pts">+{{ level.score }} pts</span>
              </div>
              <p class="cell-description">{{ level.description }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import AppIcon from '@/components/AppIcon.vue'
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useToastStore } from '@/stores/toast'
import apiClient from '@/api/client'

const router = useRouter()
const toastStore = useToastStore()

// Reactive State
const awardsList = ref([])
const rubricMatrix = ref([])
const delegates = ref([])

// True while the award is being saved, so the button can say so instead of looking dead.
const savingAward = ref(false)

// Modal Active State
const activeDelegate = ref(null)
const selectedAward = ref('None')
const gradingScores = ref({})
const validationError = ref('')

// Navigation Handler
const switchView = (path) => {
  router.push(path)
}

// Count delegates per pile
const countByAward = (awardName) => {
  return delegates.value.filter(d => d.assignedAward === awardName).length
}

// Color Styling for Delegate Cards based on Award Pile
const getAwardClass = (award) => {
  switch (award) {
    case 'Candidate':
      return 'award-candidate'
    case 'Verbal Commendation':
      return 'award-verbal'
    case 'Honorable Mention':
      return 'award-honorable'
    case 'Outstanding Delegate':
      return 'award-outstanding'
    case 'Best Delegate':
      return 'award-best'
    case 'None':
    default:
      return 'award-none'
  }
}

// Calculate total score dynamically from matrix inputs
const calculatedTotalScore = computed(() => {
  let total = 0
  for (const key in gradingScores.value) {
    total += Number(gradingScores.value[key]) || 0
  }
  return total
})

const maxPossibleScore = computed(() => {
  return rubricMatrix.value.reduce((sum, c) => sum + getCriterionMax(c), 0)
})

const getCriterionMax = (criterion) => {
  return Math.max(...criterion.levels.map(l => l.score))
}

// Rubric Cell Click Handler
const selectScore = (criterionId, scoreValue) => {
  gradingScores.value[criterionId] = scoreValue
  validationError.value = '' // Clear error on interaction
}

// Open Modal & Load Existing Delegate Rubric/Award State
const openRubricModal = (delegate) => {
  activeDelegate.value = delegate
  selectedAward.value = delegate.assignedAward || 'None'
  validationError.value = ''

  // Load existing rubric scores or initialize empty object
  gradingScores.value = delegate.scores ? { ...delegate.scores } : {}
}

const closeModal = () => {
  activeDelegate.value = null
  gradingScores.value = {}
  selectedAward.value = 'None'
  validationError.value = ''
}

// 1. Refactored Award Submission & Validation Logic
const submitAwardAndScore = async () => {
  if (!activeDelegate.value) return

  validationError.value = ''

  // Frontend Validation Check:
  const requiresRubric = [
    'Verbal Commendation',
    'Honorable Mention',
    'Outstanding Delegate',
    'Best Delegate'
  ].includes(selectedAward.value)

  if (requiresRubric) {
    const scoredCategoriesCount = Object.keys(gradingScores.value).length
    const totalRequiredCategories = rubricMatrix.value.length

    if (scoredCategoriesCount < totalRequiredCategories) {
      validationError.value = `You must score all ${totalRequiredCategories} rubric criteria before assigning an official award.`
      return
    }
  }

  const payload = {
    delegateId: activeDelegate.value.id,
    assignedAward: selectedAward.value,
    scores: { ...gradingScores.value },
    totalScore: calculatedTotalScore.value
  }

  savingAward.value = true
  try {
    // Send award assignment and scores to backend
    await apiClient.post(`/chair/awards/${activeDelegate.value.id}`, payload)

    // Update local view state upon success
    activeDelegate.value.assignedAward = selectedAward.value
    activeDelegate.value.scores = { ...gradingScores.value }
    activeDelegate.value.totalScore = calculatedTotalScore.value

    toastStore.showToast('Award saved successfully.', 'success')
    closeModal()
  } catch (error) {
    // A failed request is already described by the interceptor. A failure in this handler
    // itself has no such safety net, and used to vanish without a word - so say something
    // rather than leaving the button looking dead.
    if (!error?.response && !error?.request) {
      toastStore.showToast('Could not save the award. Please try again.', 'error')
    }
    console.error('Saving the award failed:', error)
  } finally {
    savingAward.value = false
  }
}

// 2. Refactored Fetch Initial State on Mount
onMounted(async () => {
  try {
    // Fetch available awards, evaluation rubric, and delegate list concurrently
    const [awardsRes, rubricRes, delegatesRes] = await Promise.all([
      apiClient.get('/chair/awards/options'),
      apiClient.get('/chair/awards/rubric'),
      apiClient.get('/chair/awards/delegates')
    ])

    awardsList.value = awardsRes.data
    rubricMatrix.value = rubricRes.data
    delegates.value = delegatesRes.data
  } catch (error) {
    // Automatic error notification handled globally
  }
})
</script>

<style scoped>
/* ============================================================ PAGE ====== */
/* Same white surface, navy ink and hairline rules as the delegate dashboard and the advisor
   views. Award piles keep their colour, but as soft tints read as status, not borders. */
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
  max-width: 1500px;
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

/* ============================================================ STATS ===== */
.stats-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-around;
  gap: 10px;
  padding: clamp(10px, 1.4vh, 14px) clamp(12px, 1.4vw, 20px);
  border: 1px solid var(--line);
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.99), rgba(255, 255, 255, 0.92));
  box-shadow:
    0 1px 2px rgba(3, 4, 94, 0.04),
    0 24px 48px -40px rgba(3, 4, 94, 0.45);
}

.stat-pill {
  font-size: 0.64em;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
}

.stat-pill strong {
  margin-left: 4px;
  font-size: 1.35em;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0;
  color: var(--ink);
}

.pill-verbal strong {
  color: var(--gold);
}

.pill-honorable strong {
  color: #0079ab;
}

.pill-outstanding strong {
  color: var(--green);
}

.pill-best strong {
  color: var(--gold);
}

/* ============================================================= GRID ===== */
/* Five across, because a committee's shortlist has to be readable at a glance. */
.grid-container {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
}

.delegate-card {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 8px;
  height: 68px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background-color: #ffffff;
  cursor: pointer;
  transition:
    border-color 0.3s ease,
    box-shadow 0.3s ease,
    transform 0.3s var(--ease);
}

.delegate-card:hover {
  border-color: rgba(3, 4, 94, 0.18);
  transform: translateY(-2px);
  box-shadow: 0 14px 28px -22px rgba(3, 4, 94, 0.5);
}

.card-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
}

.country-name {
  overflow: hidden;
  font-size: 0.86em;
  font-weight: 650;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--ink);
}

.committee-tag {
  flex: none;
  max-width: 50%;
  overflow: hidden;
  font-size: 0.6em;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--muted);
}

.card-status-badge {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  min-width: 0;
  font-size: 0.66em;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.award-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--muted);
}

.score-indicator {
  flex: none;
  padding: 2px 7px;
  border-radius: 999px;
  background-color: #f7fafd;
  font-size: 0.94em;
  font-variant-numeric: tabular-nums;
  color: var(--muted);
}

/* ===================================================== AWARD TINTS ====== */
/* Unassigned stays a plain card; each pile is a tint, so the wall of cards keeps its
   colour coding without a single saturated border. */
.award-none {
  border-color: var(--line);
}

.award-candidate {
  border-color: rgba(0, 157, 219, 0.35);
  background-color: rgba(0, 157, 219, 0.05);
}

.award-candidate .award-label {
  color: #0079ab;
}

.award-verbal {
  border-color: rgba(232, 198, 4, 0.45);
  background-color: rgba(232, 198, 4, 0.1);
}

.award-verbal .award-label {
  color: var(--gold);
}

.award-honorable {
  border-color: rgba(0, 157, 219, 0.3);
  background-color: rgba(0, 157, 219, 0.08);
}

.award-honorable .award-label {
  color: #0079ab;
}

.award-outstanding {
  border-color: rgba(22, 163, 74, 0.35);
  background-color: rgba(22, 163, 74, 0.07);
}

.award-outstanding .award-label {
  color: var(--green);
}

.award-best {
  border-color: rgba(180, 35, 24, 0.3);
  background-color: rgba(232, 198, 4, 0.16);
}

.award-best .award-label {
  color: var(--gold);
}

/* ========================================================== OVERLAY ===== */
.rubric-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  background-color: #f5fafd;
  animation: overlay-in 0.3s ease both;
}

@keyframes overlay-in {
  from {
    opacity: 0;
  }
}

.top-rubric-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px clamp(16px, 2.4vw, 34px);
  border-bottom: 1px solid var(--line);
  background-color: #ffffff;
}

.delegate-meta {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.delegate-meta h2 {
  margin: 0;
  font-size: 1.15em;
  font-weight: 650;
  line-height: 1.2;
  letter-spacing: -0.01em;
  color: var(--ink);
}

.committee-sub {
  font-size: 0.68em;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
}

.award-selector-box {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 0.66em;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
}

.award-selector-box select {
  padding: 8px 11px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background-color: #f7fafd;
  color: var(--ink);
  font-family: inherit;
  font-size: 1.2em;
  font-weight: 600;
  letter-spacing: 0.01em;
  text-transform: none;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    background-color 0.2s ease;
}

.award-selector-box select:focus {
  outline: none;
  border-color: rgba(0, 157, 219, 0.5);
  background-color: #ffffff;
}

.score-summary-box {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 14px;
  border-radius: 11px;
  background-color: #f7fafd;
}

.score-label {
  font-size: 0.66em;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
}

.score-value {
  font-size: 1.02em;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--green);
}

.bar-actions {
  display: flex;
  gap: 9px;
}

/* While the save is in flight the button says "Saving…" and stops accepting clicks, so a
   slow request cannot be mistaken for a dead button. */
.btn-submit:disabled {
  opacity: 0.7;
  cursor: progress;
}

.btn-submit {
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

.btn-submit:hover {
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

.validation-banner {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px clamp(16px, 2.4vw, 34px);
  border-bottom: 1px solid rgba(180, 35, 24, 0.2);
  background-color: rgba(180, 35, 24, 0.07);
  font-size: 0.85em;
  text-align: center;
  color: var(--red);
}

/* =========================================================== RUBRIC ===== */
.rubric-matrix-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--gap);
  padding: clamp(16px, 2.4vw, 30px);
  overflow-y: auto;
}

.rubric-row {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: clamp(14px, 1.9vh, 20px);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background-color: #ffffff;
}

.criterion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line);
}

.criterion-header h3 {
  margin: 0;
  font-size: 0.98em;
  font-weight: 650;
  color: var(--ink);
}

.selected-pts {
  font-size: 0.66em;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
}

.selected-pts strong {
  font-size: 1.5em;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0;
  color: var(--ink);
}

.level-cells-grid {
  display: flex;
  gap: 10px;
  /* More levels than fit scroll sideways rather than wrapping onto a second line: a level
     that drops below its neighbours stops reading as one scale. */
  overflow-x: auto;
  padding-bottom: 2px;
}

.rubric-cell {
  /* Share the row evenly, but never squeeze a description into a sliver. */
  flex: 1 1 0;
  min-width: 160px;
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 13px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background-color: #f7fafd;
  cursor: pointer;
  transition:
    border-color 0.25s ease,
    background-color 0.25s ease,
    transform 0.25s var(--ease);
}

.rubric-cell:hover {
  border-color: rgba(0, 157, 219, 0.35);
  background-color: #ffffff;
  transform: translateY(-1px);
}

/* Chosen level: accent edge on a pale wash, so the whole row still reads as one scale. */
.rubric-cell.selected {
  border-color: rgba(0, 157, 219, 0.55);
  background-color: rgba(0, 157, 219, 0.07);
}

.cell-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.level-title {
  font-size: 0.78em;
  font-weight: 650;
  color: var(--ink);
}

.level-pts {
  flex: none;
  padding: 2px 7px;
  border-radius: 999px;
  background-color: #ffffff;
  font-size: 0.64em;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--muted);
}

.rubric-cell.selected .level-pts {
  background-color: var(--ink);
  color: #ffffff;
}

.cell-description {
  margin: 0;
  font-size: 0.76em;
  line-height: 1.45;
  color: var(--muted);
}

/* ========================================================== RESPONSIVE === */
@media (max-width: 1200px) {
  .grid-container {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .grid-container {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .toggle-btn {
    flex: 1;
    min-width: 0;
  }

  .top-rubric-bar {
    align-items: stretch;
    flex-direction: column;
  }
}

@media (prefers-reduced-motion: reduce) {
  .rubric-modal-overlay {
    animation: none;
  }

  .delegate-card,
  .rubric-cell,
  .btn-submit,
  .btn-close {
    transition: none;
  }
}
</style>
