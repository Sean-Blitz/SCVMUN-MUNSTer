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
      <span>Label - Description</span>
      <span>Max Points</span>
      <span></span>
    </div>
    <div v-for="(criterion, index) in paper" :key="index" class="rubric-paper-row">
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
        <div class="field-pair">
          <label class="field-label" :for="`awards-label-${cIndex}`">Criterion label</label>
          <input
            :id="`awards-label-${cIndex}`"
            v-model="criterion.label"
            class="text-input"
            type="text"
            placeholder="e.g. Speaking"
          />
        </div>
        <button class="btn-icon" title="Remove criterion" @click="awards.splice(cIndex, 1)">
          <AppIcon name="close" :size="14" />
        </button>
      </div>

      <div class="rubric-levels">
        <p class="field-label rubric-levels-title">Score levels</p>

        <div v-for="(level, lIndex) in criterion.levels" :key="lIndex" class="rubric-level-row">
          <div class="field-pair">
            <label class="field-label" :for="`level-score-${cIndex}-${lIndex}`">Score</label>
            <input
              :id="`level-score-${cIndex}-${lIndex}`"
              v-model.number="level.score"
              class="text-input"
              type="number"
              step="1"
              placeholder="4"
            />
          </div>
          <div class="field-pair">
            <label class="field-label" :for="`level-label-${cIndex}-${lIndex}`">Level label</label>
            <input
              :id="`level-label-${cIndex}-${lIndex}`"
              v-model="level.label"
              class="text-input"
              type="text"
              placeholder="e.g. Outstanding"
            />
          </div>
          <div class="field-pair">
            <label class="field-label" :for="`level-desc-${cIndex}-${lIndex}`">
              Description (optional)
            </label>
            <input
              :id="`level-desc-${cIndex}-${lIndex}`"
              v-model="level.description"
              class="text-input"
              type="text"
              placeholder="What this level means"
            />
          </div>
          <button
            class="btn-icon"
            title="Remove level"
            @click="criterion.levels.splice(lIndex, 1)"
          >
            <AppIcon name="close" :size="14" />
          </button>
        </div>
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

// ---------- Blank scaffolding ----------
// A rubric that has never been filled in comes back as `[]`, which used to render as a card
// with a sentence in it and nothing to aim at. Two criteria - and, for awards, two score
// levels each - show the shape of the document instead. These rows are drafts: `save()`
// drops the ones that were left blank, so nothing reaches the server and a half-filled
// rubric saves the part that was filled in.
const blankPaperCriterion = () => ({ id: '', label: '', maxScore: 10 })
const blankLevel = (score) => ({ score, label: '', description: '' })
const blankAwardsCriterion = () => ({
  id: '',
  label: '',
  levels: [blankLevel(4), blankLevel(2)]
})

const withPaperScaffold = (items) =>
  items.length ? items : [blankPaperCriterion(), blankPaperCriterion()]
const withAwardsScaffold = (items) =>
  items.length ? items : [blankAwardsCriterion(), blankAwardsCriterion()]

const applyRubrics = (data) => {
  paper.value = withPaperScaffold((data.paper || []).map((criterion) => ({ ...criterion })))
  awards.value = withAwardsScaffold(
    (data.awards || []).map((criterion) => ({
      ...criterion,
      levels: (criterion.levels || []).map((level) => ({ ...level }))
    }))
  )
}

// What actually gets sent.
//
// `id` is not a field any more - the label is the only name the admin types - but the
// server still needs one, because it is the key every recorded mark is filed under
// (`paper_rubric_grade`, `overall_rubric_scores`). So it is derived here instead:
//
//   * a criterion that was already saved keeps the id it has, which is what makes renaming
//     a label a pure rename rather than a 409 ("that id is already graded");
//   * a new one takes a slug of its label, made unique within the same save.
//
// A blank row is scaffolding, not content, so it is dropped rather than sent: the server
// would answer 400 for a criterion with no label.
const isBlank = (value) => !String(value ?? '').trim()

const slugify = (text) =>
  String(text)
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60)

const assignId = (criterion, used) => {
  const existing = typeof criterion.id === 'string' ? criterion.id.trim() : criterion.id
  if (!isBlank(existing)) {
    const key = String(existing)
    if (!used.has(key)) {
      used.add(key)
      return existing
    }
  }

  const base = slugify(criterion.label) || 'criterion'
  let candidate = base
  let suffix = 2
  while (used.has(candidate)) candidate = `${base}-${suffix++}`
  used.add(candidate)
  return candidate
}

const paperPayload = () => {
  const used = new Set()
  return paper.value
    .filter((criterion) => !isBlank(criterion.label))
    .map((criterion) => ({
      id: assignId(criterion, used),
      label: criterion.label.trim(),
      maxScore: criterion.maxScore
    }))
}

const awardsPayload = () => {
  const used = new Set()
  return awards.value
    .filter((criterion) => !isBlank(criterion.label))
    .map((criterion) => ({
      id: assignId(criterion, used),
      label: criterion.label.trim(),
      // A level with no label is a blank row too - an unlabelled cell has nothing to render
      // in the awards matrix, and the server rejects it.
      levels: (criterion.levels || [])
        .filter((level) => !isBlank(level.label))
        .map((level) => ({
          score: level.score,
          label: level.label.trim(),
          description: (level.description || '').trim()
        }))
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
  // Blank scaffolding rows are dropped here rather than rejected by the server.
  const body = kind === 'paper' ? { paper: paperPayload() } : { awards: awardsPayload() }

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
  paper.value.push(blankPaperCriterion())
}

const addAwardsCriterion = () => {
  awards.value.push(blankAwardsCriterion())
}

// Levels read as a descending scale (4, 2, 1), so a new one goes below the lowest rather
// than above the highest - adding a level used to suggest a score better than the top.
const addLevel = (criterion) => {
  criterion.levels = criterion.levels || []
  const scores = criterion.levels.map((level) => Number(level.score) || 0)
  const lowest = scores.length ? Math.min(...scores) : 2
  criterion.levels.push(blankLevel(Math.max(1, lowest - 1)))
}

onMounted(load)
</script>
