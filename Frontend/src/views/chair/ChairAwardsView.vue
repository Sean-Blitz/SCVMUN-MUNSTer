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
.chair-page {
  display: flex;
  flex-direction: column;
  gap: 15px;
  max-width: 1500px;
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

/* STATS COUNTER BAR */
.stats-bar {
  display: flex;
  justify-content: space-around;
  background-color: #ffffff;
  border: 1px solid #e8c604;
  padding: 10px;
  border-radius: 6px;
  font-size: 0.85rem;
}

.stat-pill {
  color: #5b6b7d;
}

.stat-pill strong {
  color: #00007e;
}

.pill-verbal strong { color: #e8c604; }
.pill-honorable strong { color: #00007e; }
.pill-outstanding strong { color: #16a34a; }
.pill-best strong { color: #e8c604; }

/* ULTRA-COMPACT 5-COLUMN GRID */
.grid-container {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 10px;
}

.delegate-card {
  background-color: #ffffff;
  border: 2px solid #e8c604;
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
  color: #00007e93;
}

.committee-tag {
  font-size: 0.7rem;
  color: #6b7c8d;
}

.card-status-badge {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.75rem;
  font-weight: bold;
}

.score-indicator {
  background-color: #f5fafd;
  padding: 1px 5px;
  border-radius: 3px;
  color: #5b6b7d;
  border: 1px solid #e8c604;
}

/* CARD COLOR DIFFERENTIATION BASED ON PILE / AWARD */
.award-none {
  border-color: #e8c604;
}

.award-candidate {
  border-color: #009ddb;
  background-color: #eaf6fd;
}

.award-candidate .award-label { color: #00007e; }

.award-verbal {
  border-color: #e8c604;
  background-color: #009ddbda;
  color: #00007e;
}

.award-verbal .award-label { color: #7a5c00; }

.award-honorable {
  border-color: #009ddb;
  background-color: #eaf6fd;
}

.award-honorable .award-label { color: #00007e; }

.award-outstanding {
  border-color: #16a34a;
  background-color: #dcfce7;
}

.award-outstanding .award-label { color: #166534; }

.award-best {
  border-color: #e8c604;
  background-color: #fdf6d3;
}

.award-best .award-label { color: #7a5c00; }


/* FULL SCREEN RUBRIC MODAL */
.rubric-modal-overlay {
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

.top-rubric-bar {
  background-color: #ffffff;
  border-bottom: 2px solid #e8c604;
  padding: 12px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}

.delegate-meta h2 {
  margin: 0;
  font-size: 1.2rem;
  color: #00007e;
}

.committee-sub {
  font-size: 0.8rem;
  color: #00007e;
}

.award-selector-box {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.9rem;
}

.award-selector-box select {
  background-color: #ffffff;
  color: #00007e93;
  border: 1px solid #e8c604;
  padding: 8px 12px;
  border-radius: 4px;
  font-weight: bold;
}

.score-summary-box {
  background-color: #f5fafd;
  border: 1px solid #e8c604;
  padding: 8px 16px;
  border-radius: 4px;
  display: flex;
  gap: 8px;
  align-items: center;
}

.score-label {
  color: #5b6b7d;
  font-size: 0.85rem;
}

.score-value {
  color: #16a34a;
  font-size: 1.1rem;
  font-weight: bold;
}

.bar-actions {
  display: flex;
  gap: 10px;
}

.btn-submit {
  background-color: #16a34a;
  color: #00007e;
  border: none;
  padding: 8px 18px;
  border-radius: 4px;
  font-weight: bold;
  cursor: pointer;
}

.btn-submit:hover {
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

/* VALIDATION BANNER */
.validation-banner {
  background-color: #fee2e2;
  color: #991b1b;
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
  background-color: #ffffff;
  border: 1px solid #e8c604;
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
  border-bottom: 1px solid #e8c604;
  padding-bottom: 8px;
}

.criterion-header h3 {
  margin: 0;
  font-size: 1rem;
  color: #00007e;
}

.selected-pts {
  font-size: 0.85rem;
  color: #5b6b7d;
}

.selected-pts strong {
  color: #00007e;
}

/* CELL GRID WITHIN ROW */
.level-cells-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.rubric-cell {
  background-color: #f5fafd;
  border: 2px solid #e8c604;
  border-radius: 6px;
  padding: 14px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: all 0.2s ease;
}

.rubric-cell:hover {
  border-color: #009ddb;
}

.rubric-cell.selected {
  border-color: #16a34a;
  background-color: #dcfce7;
}

.cell-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.level-title {
  font-weight: bold;
  font-size: 0.9rem;
  color: #00007e;
}

.level-pts {
  font-size: 0.8rem;
  font-weight: bold;
  color: #16a34a;
  background-color: #f5fafd;
  padding: 2px 6px;
  border-radius: 3px;
}

.cell-description {
  margin: 0;
  font-size: 0.82rem;
  color: #5b6b7d;
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