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
        ⚠️ {{ validationError }}
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
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useToastStore } from '@/stores/toast'
import apiClient from '@/api/client'

const router = useRouter()

// Reactive State
const awardsList = ref([])
const rubricMatrix = ref([])
const delegates = ref([])

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
    // Errors handle popup automatically via client.js
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
  --font:
    'Inter', -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto,
    'Helvetica Neue', Arial, sans-serif;

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
  padding: 10px clamp(16px, 2.4vw, 34px);
  border-bottom: 1px solid rgba(180, 35, 24, 0.2);
  background-color: rgba(180, 35, 24, 0.07);
  font-size: 0.82em;
  font-weight: 600;
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
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.rubric-cell {
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

  .level-cells-grid {
    grid-template-columns: minmax(0, 1fr);
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
