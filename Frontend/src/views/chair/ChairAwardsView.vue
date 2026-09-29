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
      apiClient.get('/chair/rubric'),
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
.chair-page {
  display: flex;
  flex-direction: column;
  gap: 15px;
  max-width: 1500px;
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

/* STATS COUNTER BAR */
.stats-bar {
  display: flex;
  justify-content: space-around;
  background-color: #2a2e35;
  border: 1px solid #3f444e;
  padding: 10px;
  border-radius: 6px;
  font-size: 0.85rem;
}

.stat-pill {
  color: #aaaaaa;
}

.stat-pill strong {
  color: #22d3ee;
}

.pill-verbal strong { color: #f59e0b; }
.pill-honorable strong { color: #a855f7; }
.pill-outstanding strong { color: #10b981; }
.pill-best strong { color: #eab308; }

/* ULTRA-COMPACT 5-COLUMN GRID */
.grid-container {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 10px;
}

.delegate-card {
  background-color: #2a2e35;
  border: 2px solid #3f444e;
  border-radius: 6px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  height: 65px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.delegate-card:hover {
  transform: translateY(-2px);
  filter: brightness(1.1);
}

.card-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.country-name {
  font-weight: bold;
  font-size: 0.9rem;
  color: #ffffff;
}

.committee-tag {
  font-size: 0.7rem;
  color: #888888;
}

.card-status-badge {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.75rem;
  font-weight: bold;
}

.score-indicator {
  background-color: #1a1d21;
  padding: 1px 5px;
  border-radius: 3px;
  color: #aaaaaa;
  border: 1px solid #3f444e;
}

/* CARD COLOR DIFFERENTIATION BASED ON PILE / AWARD */
.award-none {
  border-color: #3f444e;
}

.award-candidate {
  border-color: #22d3ee;
  background-color: #1e293b;
}

.award-candidate .award-label { color: #22d3ee; }

.award-verbal {
  border-color: #f59e0b;
  background-color: #312e81;
}

.award-verbal .award-label { color: #fcd34d; }

.award-honorable {
  border-color: #a855f7;
  background-color: #3b0764;
}

.award-honorable .award-label { color: #d8b4fe; }

.award-outstanding {
  border-color: #10b981;
  background-color: #064e3b;
}

.award-outstanding .award-label { color: #6ee7b7; }

.award-best {
  border-color: #eab308;
  background-color: #451a03;
}

.award-best .award-label { color: #fde047; }


/* FULL SCREEN RUBRIC MODAL */
.rubric-modal-overlay {
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

.top-rubric-bar {
  background-color: #2a2e35;
  border-bottom: 2px solid #3f444e;
  padding: 12px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}

.delegate-meta h2 {
  margin: 0;
  font-size: 1.2rem;
  color: #ffffff;
}

.committee-sub {
  font-size: 0.8rem;
  color: #22d3ee;
}

.award-selector-box {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.9rem;
}

.award-selector-box select {
  background-color: #1a1d21;
  color: #ffffff;
  border: 1px solid #3f444e;
  padding: 8px 12px;
  border-radius: 4px;
  font-weight: bold;
}

.score-summary-box {
  background-color: #1a1d21;
  border: 1px solid #3f444e;
  padding: 8px 16px;
  border-radius: 4px;
  display: flex;
  gap: 8px;
  align-items: center;
}

.score-label {
  color: #aaaaaa;
  font-size: 0.85rem;
}

.score-value {
  color: #22c55e;
  font-size: 1.1rem;
  font-weight: bold;
}

.bar-actions {
  display: flex;
  gap: 10px;
}

.btn-submit {
  background-color: #22c55e;
  color: #111111;
  border: none;
  padding: 8px 18px;
  border-radius: 4px;
  font-weight: bold;
  cursor: pointer;
}

.btn-submit:hover {
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

/* VALIDATION BANNER */
.validation-banner {
  background-color: #7f1d1d;
  color: #fca5a5;
  border-bottom: 1px solid #ef4444;
  padding: 10px 24px;
  font-size: 0.9rem;
  font-weight: bold;
  text-align: center;
}

/* RUBRIC MATRIX CONTAINER */
.rubric-matrix-container {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.rubric-row {
  background-color: #2a2e35;
  border: 1px solid #3f444e;
  border-radius: 8px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.criterion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #3f444e;
  padding-bottom: 8px;
}

.criterion-header h3 {
  margin: 0;
  font-size: 1rem;
  color: #ffffff;
}

.selected-pts {
  font-size: 0.85rem;
  color: #aaaaaa;
}

.selected-pts strong {
  color: #22d3ee;
}

/* CELL GRID WITHIN ROW */
.level-cells-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.rubric-cell {
  background-color: #1a1d21;
  border: 2px solid #3f444e;
  border-radius: 6px;
  padding: 14px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: all 0.2s ease;
}

.rubric-cell:hover {
  border-color: #6366f1;
}

.rubric-cell.selected {
  border-color: #22c55e;
  background-color: #064e3b;
}

.cell-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.level-title {
  font-weight: bold;
  font-size: 0.9rem;
  color: #ffffff;
}

.level-pts {
  font-size: 0.8rem;
  font-weight: bold;
  color: #22c55e;
  background-color: #1a1d21;
  padding: 2px 6px;
  border-radius: 3px;
}

.cell-description {
  margin: 0;
  font-size: 0.82rem;
  color: #cccccc;
  line-height: 1.4;
}

/* RESPONSIVE LAYOUT BREAKPOINTS */
@media (max-width: 1200px) {
  .grid-container {
    grid-template-columns: repeat(4, 1fr);
  }
  .level-cells-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .grid-container {
    grid-template-columns: repeat(2, 1fr);
  }
  .top-rubric-bar {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>