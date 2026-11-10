<template>
<!-- POSITION PAPER RUBRIC (flat: one maximum per criterion) -->
<div class="section-card">
  <div class="card-header-action">
    <h2>Position Paper Rubric</h2>
    <button class="btn-refresh" :disabled="savingPaper || loading" @click="save('paper')">
      {{ savingPaper ? 'Saving...' : 'Save paper rubric' }}
    </button>
  </div>
  <p class="section-desc">
    The criteria chairs grade a position paper against. The total is the sum of the maxima,
    and it is recomputed from this list every time a paper is graded — so changing a maximum
    changes the denominator of every paper graded afterwards. Try to avoid changing it after grading has begun.
  </p>

  <div v-if="conflict && conflict.kind === 'paper'" class="rubric-conflict">
    <p>{{ conflict.message }}</p>
    <button class="btn-danger" :disabled="savingPaper" @click="save('paper', true)">
      Save anyway
    </button>
    <button class="btn-secondary" @click="conflict = null">Cancel</button>
  </div>

  <div v-if="loading" class="empty-state">Loading the rubric…</div>
  <div v-else-if="!paper.length" class="empty-state">
    No criteria yet. Chairs cannot grade a paper until this has at least one.
  </div>

  <div v-else class="rubric-rows">
    <div class="rubric-paper-head">
      <span>Criterion id</span>
      <span>Label - Description</span>
      <span>Max Points</span>
      <span></span>
    </div>
    <div v-for="(criterion, index) in paper" :key="index" class="rubric-paper-row">
      <input
        v-model="criterion.id"
        class="text-input"
        type="text"
        aria-label="Criterion id"
        placeholder="e.g. clarity"
      />
      <input
        v-model="criterion.label"
        class="text-input"
        type="text"
        aria-label="Criterion label"
        placeholder="Clarity of Argument"
      />
      <input
        v-model.number="criterion.maxScore"
        class="text-input"
        type="number"
        min="1"
        step="1"
        aria-label="Maximum score"
      />
      <button class="btn-icon" title="Remove criterion" @click="paper.splice(index, 1)">
        <AppIcon name="close" :size="14" />
      </button>
    </div>
  </div>

  <div class="row-actions">
    <span class="rubric-total">Total: {{ paperTotal }} points</span>
    <button class="btn-secondary" @click="addPaperCriterion">+ Add criterion</button>
  </div>
</div>

<!-- AWARDS RUBRIC (levelled: each criterion offers a set of named scores) -->
<div class="section-card">
  <div class="card-header-action">
    <h2>Awards Rubric</h2>
    <button class="btn-refresh" :disabled="savingAwards || loading" @click="save('awards')">
      {{ savingAwards ? 'Saving...' : 'Save awards rubric' }}
    </button>
  </div>
  <p class="section-desc">
    What chairs score a delegate on when deciding a final conference award. Each criterion's maximum is the
    highest of that category, and the levels represent the score options.
  </p>

  <div v-if="conflict && conflict.kind === 'awards'" class="rubric-conflict">
    <p>{{ conflict.message }}</p>
    <button class="btn-danger" :disabled="savingAwards" @click="save('awards', true)">
      Save anyway
    </button>
    <button class="btn-secondary" @click="conflict = null">Cancel</button>
  </div>

  <div v-if="loading" class="empty-state">Loading the rubric…</div>
  <div v-else-if="!awards.length" class="empty-state">
    No criteria yet. Chairs cannot record award scores until this has at least one.
  </div>

  <div v-else class="rubric-criteria">
    <div v-for="(criterion, cIndex) in awards" :key="cIndex" class="rubric-criterion">
      <div class="rubric-criterion-head">
        <input
          v-model="criterion.id"
          class="text-input"
          type="text"
          aria-label="Criterion id"
          placeholder="e.g. speaking"
        />
        <input
          v-model="criterion.label"
          class="text-input"
          type="text"
          aria-label="Criterion label"
          placeholder="Speaking"
        />
        <button class="btn-icon" title="Remove criterion" @click="awards.splice(cIndex, 1)">
          <AppIcon name="close" :size="14" />
        </button>
      </div>

      <div v-for="(level, lIndex) in criterion.levels" :key="lIndex" class="rubric-level-row">
        <input
          v-model.number="level.score"
          class="text-input"
          type="number"
          step="1"
          aria-label="Level score"
          placeholder="4"
        />
        <input
          v-model="level.label"
          class="text-input"
          type="text"
          aria-label="Level label"
          placeholder="Outstanding"
        />
        <input
          v-model="level.description"
          class="text-input"
          type="text"
          aria-label="Level description"
          placeholder="Optional description"
        />
        <button
          class="btn-icon"
          title="Remove level"
          @click="criterion.levels.splice(lIndex, 1)"
        >
          <AppIcon name="close" :size="14" />
        </button>
      </div>

      <div class="row-actions">
        <span class="rubric-total">Max: {{ criterionMax(criterion) }}</span>
        <button class="btn-secondary" @click="addLevel(criterion)">+ Add level</button>
      </div>
    </div>
  </div>

  <div class="row-actions">
    <button class="btn-secondary" @click="addAwardsCriterion">+ Add criterion</button>
  </div>
</div>
</template>

<script setup>
import AppIcon from '@/components/AppIcon.vue'
import { computed, onMounted, ref } from 'vue'
import apiClient from '@/api/client'
import { useToastStore } from '@/stores/toast'

const toastStore = useToastStore()

// The two rubrics, exactly as /chair/rubric and /chair/awards/rubric publish them. Those
// read endpoints are already open to admins (the chair router allows the role), so the
// editor reads what the graders read and there is no second read route to keep in step.
const paper = ref([])
const awards = ref([])
const loading = ref(false)
const savingPaper = ref(false)
const savingAwards = ref(false)

// A 409 from the save: the rubric drops a criterion that already has recorded marks, so the
// server wants `force`. Held here so the message survives the toast and the admin gets a
// button rather than having to retry the request by hand.
const conflict = ref(null)

const paperTotal = computed(() =>
  paper.value.reduce((sum, criterion) => sum + (Number(criterion.maxScore) || 0), 0)
)

const criterionMax = (criterion) =>
  Math.max(0, ...(criterion.levels || []).map((level) => Number(level.score) || 0))

// A fresh id that does not collide with the ones already on screen. Ids key every recorded
// mark, so they have to be unique; the admin can rename one before saving, at which point
// the server refuses if that id is already graded (409 + force).
const nextId = (items, prefix) => {
  const taken = new Set(items.map((item) => String(item.id)))
  let number = items.length + 1
  while (taken.has(`${prefix}-${number}`)) number += 1
  return `${prefix}-${number}`
}

const applyRubrics = (data) => {
  paper.value = (data.paper || []).map((criterion) => ({ ...criterion }))
  awards.value = (data.awards || []).map((criterion) => ({
    ...criterion,
    levels: (criterion.levels || []).map((level) => ({ ...level }))
  }))
}

const load = async () => {
  loading.value = true
  try {
    const [paperResponse, awardsResponse] = await Promise.all([
      apiClient.get('/chair/rubric'),
      apiClient.get('/chair/awards/rubric')
    ])
    applyRubrics({ paper: paperResponse.data, awards: awardsResponse.data })
  } catch (error) {
    // Errors automatically pop up via the global toast interceptor
  } finally {
    loading.value = false
  }
}

// One key per rubric, so saving the paper rubric cannot overwrite the awards rubric (and a
// stale tab cannot resurrect a rubric the other editor has since changed).
const save = async (kind, force = false) => {
  const saving = kind === 'paper' ? savingPaper : savingAwards
  const body =
    kind === 'paper'
      ? { paper: paper.value.map(({ id, label, maxScore }) => ({ id, label, maxScore })) }
      : {
          awards: awards.value.map((criterion) => ({
            id: criterion.id,
            label: criterion.label,
            levels: (criterion.levels || []).map(({ score, label, description }) => ({
              score,
              label,
              description: description || ''
            }))
          }))
        }

  saving.value = true
  conflict.value = null
  try {
    const response = await apiClient.put('/admin/rubrics', body, {
      params: force ? { force: true } : {}
    })
    applyRubrics(response.data)
    toastStore.showToast(
      kind === 'paper' ? 'Paper rubric saved.' : 'Awards rubric saved.',
      'success'
    )
  } catch (error) {
    // 409 means "these criteria are already graded" - offer the forced save. Everything
    // else (400/422) is already described by the global toast interceptor.
    if (error.response?.status === 409) {
      conflict.value = { kind, message: error.response.data?.message || 'Save refused.' }
    }
  } finally {
    saving.value = false
  }
}

const addPaperCriterion = () => {
  paper.value.push({ id: nextId(paper.value, 'criterion'), label: '', maxScore: 10 })
}

const addAwardsCriterion = () => {
  awards.value.push({
    id: nextId(awards.value, 'criterion'),
    label: '',
    levels: [{ score: 4, label: '', description: '' }]
  })
}

const addLevel = (criterion) => {
  criterion.levels = criterion.levels || []
  const highest = criterionMax(criterion)
  criterion.levels.push({ score: highest + 1, label: '', description: '' })
}

onMounted(load)
</script>
